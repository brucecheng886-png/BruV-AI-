"""
Auth Router — 登入/登出/取得目前使用者/帳號管理
"""
import hashlib
import logging
import secrets
import smtplib
import ssl as _ssl
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText

from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_access_token, hash_password, verify_password, CurrentUser, CurrentAdmin, create_stepup_token, verify_stepup_token
from database import get_db
from models import User, PasswordResetToken, SystemSetting
from rate_limit import limiter, LOGIN_RATE_LIMIT

router = APIRouter()
logger = logging.getLogger(__name__)



# ── 登入 ──────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    role: str


@router.post("/login", response_model=LoginResponse)
@limiter.limit(LOGIN_RATE_LIMIT)
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="帳號或密碼錯誤")

    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="此帳號已停用，請聯絡管理員")

    token = create_access_token(user.id, user.email, user.role)
    return LoginResponse(access_token=token, user_id=user.id, email=user.email, role=user.role)


# ── 取得目前使用者 ────────────────────────────────────────────
@router.get("/me")
async def get_me(user: CurrentUser):
    return {
        "user_id": user.id,
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "display_name": getattr(user, "display_name", None),
        "is_active": getattr(user, "is_active", True),
        "must_change_password": getattr(user, "must_change_password", False),
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


# ── 更新個人資料 ──────────────────────────────────────────────
class UpdateMeRequest(BaseModel):
    email: str | None = None
    display_name: str | None = None


@router.patch("/me")
async def update_me(
    body: UpdateMeRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    if body.email is not None and body.email != user.email:
        dup = await db.execute(
            select(User).where(User.email == body.email, User.id != user.id)
        )
        if dup.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="此 Email 已被其他使用者使用")
        user.email = body.email

    if body.display_name is not None:
        name = body.display_name.strip()
        user.display_name = name if name else None

    await db.commit()
    await db.refresh(user)
    return {
        "user_id": user.id,
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "display_name": getattr(user, "display_name", None),        "is_active": getattr(user, "is_active", True),
        "must_change_password": getattr(user, "must_change_password", False),        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


# ── 修改密碼 ──────────────────────────────────────────────────
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, user.password):
        raise HTTPException(status_code=400, detail="目前密碼不正確")
    user.password = hash_password(body.new_password)
    await db.commit()
    return {"success": True}


# ── 初始化管理員（無需 JWT；僅在尚未初始化時可用）────────────
class InitAdminRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)


@router.post("/init-admin")
async def init_admin(body: InitAdminRequest, db: AsyncSession = Depends(get_db)):
    logger.info("[init-admin] 開始執行，email=%s", body.email)
    try:
        # 找預設 admin 列（email='admin@local'，密碼為 placeholder）
        result = await db.execute(select(User).where(User.email == "admin@local"))
        admin = result.scalar_one_or_none()
        logger.info("[init-admin] admin@local 查詢結果: %s", admin)
    except Exception as e:
        logger.error("[init-admin] DB 查詢失敗: %s", e, exc_info=True)
        raise

    if admin is None or "placeholder" not in (admin.password or ""):
        logger.info("[init-admin] 管理員已初始化或不存在，回傳 403")
        raise HTTPException(status_code=403, detail="管理員已初始化")

    if body.email != "admin@local":
        try:
            dup = await db.execute(
                select(User).where(User.email == body.email, User.id != admin.id)
            )
            if dup.scalar_one_or_none() is not None:
                raise HTTPException(status_code=409, detail="此 Email 已被使用")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("[init-admin] 重複 email 查詢失敗: %s", e, exc_info=True)
            raise

    try:
        admin.email = body.email
        admin.password = hash_password(body.password)
        admin.role = "admin"
        await db.commit()
        logger.info("[init-admin] 成功設定管理員 email=%s", body.email)
    except Exception as e:
        logger.error("[init-admin] commit 失敗: %s", e, exc_info=True)
        raise
    return {"success": True, "user_id": admin.id, "email": admin.email}


# ── 忘記密碼 / 重設密碼 ──────────────────────────────────────

_RESET_EXPIRE_MINUTES = 15

_SMTP_DEFAULTS = {
    "smtp_host":      "",
    "smtp_port":      "587",
    "smtp_user":      "",
    "smtp_password":  "",
    "smtp_from_name": "BruV AI",
    "smtp_tls":       "true",
}
_SMTP_KEYS = list(_SMTP_DEFAULTS.keys())


async def _send_reset_email(db: AsyncSession, to_email: str, reset_url: str) -> None:
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key.in_(_SMTP_KEYS))
    )
    rows = {r.key: r.value for r in result.scalars()}
    cfg = {k: rows.get(k, v) for k, v in _SMTP_DEFAULTS.items()}

    host = cfg["smtp_host"]
    if not host:
        raise HTTPException(status_code=503, detail="SMTP 尚未設定，請先在設定頁面完成郵件設定")

    port = int(cfg["smtp_port"])
    user = cfg["smtp_user"]
    password = cfg["smtp_password"]
    from_name = cfg["smtp_from_name"]
    use_tls = cfg["smtp_tls"].lower() in ("1", "true", "on", "yes")

    body_text = (
        f"您好，\n\n"
        f"請點擊以下連結重設您的 BruV AI 密碼（連結 {_RESET_EXPIRE_MINUTES} 分鐘內有效）：\n\n"
        f"{reset_url}\n\n"
        f"若您沒有請求重設密碼，請忽略此信。\n"
    )
    msg = MIMEText(body_text, "plain", "utf-8")
    msg["Subject"] = "BruV AI 密碼重設"
    msg["From"] = f"{from_name} <{user}>" if user else from_name
    msg["To"] = to_email

    try:
        if use_tls:
            context = _ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                smtp.starttls(context=context)
                if user and password:
                    smtp.login(user, password)
                smtp.sendmail(user or from_name, [to_email], msg.as_bytes())
        else:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                if user and password:
                    smtp.login(user, password)
                smtp.sendmail(user or from_name, [to_email], msg.as_bytes())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"郵件發送失敗：{e}")


class ForgotPasswordRequest(BaseModel):
    email: str


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """送出密碼重設郵件。不論帳號是否存在，皆回傳相同訊息（防枚舉攻擊）。"""
    generic_msg = {"message": "若帳號存在，密碼重設連結已寄出"}

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None:
        return generic_msg

    # 產生安全亂數 token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    # 清除同帳號的舊 token（避免資料庫累積）
    old_tokens = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    for t in old_tokens.scalars():
        await db.delete(t)

    expires = datetime.now(timezone.utc) + timedelta(minutes=_RESET_EXPIRE_MINUTES)
    db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires))
    await db.commit()

    reset_url = f"http://localhost/#/reset-password?token={raw_token}"
    await _send_reset_email(db, user.email, reset_url)
    return generic_msg


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()

    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    record = result.scalar_one_or_none()

    if record is None or record.used:
        raise HTTPException(status_code=400, detail="重設連結無效或已使用")

    if datetime.now(timezone.utc) > record.expires_at:
        raise HTTPException(status_code=400, detail="重設連結已過期，請重新申請")

    user = await db.get(User, record.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="使用者不存在")

    user.password = hash_password(body.new_password)
    record.used = True
    await db.commit()
    return {"message": "密碼已重設，請重新登入"}


# ── 管理員使用者管理 CRUD ─────────────────────────────────────

VALID_ROLES = {"admin", "editor", "user", "readonly", "auditor"}


def _user_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "display_name": getattr(u, "display_name", None),
        "role": u.role,
        "is_active": getattr(u, "is_active", True),
        "must_change_password": getattr(u, "must_change_password", False),
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.get("/users")
async def list_users(
    current_admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
):
    """列出所有使用者（admin only）。"""
    result = await db.execute(select(User).order_by(User.created_at))
    users = result.scalars().all()
    return [_user_dict(u) for u in users]


class CreateUserRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str | None = None
    role: str = "user"


@router.post("/users", status_code=201)
async def create_user(
    body: CreateUserRequest,
    current_admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
):
    """管理員建立新使用者。新帳號預設 must_change_password=True。"""
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"無效角色，允許值：{', '.join(sorted(VALID_ROLES))}")

    dup = await db.execute(select(User).where(User.email == body.email))
    if dup.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="此 Email 已被使用")

    new_user = User(
        email=body.email,
        password=hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
        is_active=True,
        must_change_password=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return _user_dict(new_user)


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    current_admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
):
    """修改使用者角色、display_name 或停用狀態（admin only）。"""
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="使用者不存在")

    if body.role is not None:
        if body.role not in VALID_ROLES:
            raise HTTPException(status_code=422, detail=f"無效角色，允許值：{', '.join(sorted(VALID_ROLES))}")
        # 不得降級自己的 admin 角色，避免鎖死
        if target.id == current_admin.id and body.role != "admin":
            raise HTTPException(status_code=400, detail="不可降級自己的管理員角色")
        target.role = body.role

    if body.display_name is not None:
        target.display_name = body.display_name.strip() or None

    if body.is_active is not None:
        if target.id == current_admin.id and not body.is_active:
            raise HTTPException(status_code=400, detail="不可停用自己的帳號")
        target.is_active = body.is_active

    await db.commit()
    await db.refresh(target)
    return _user_dict(target)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    current_admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
):
    """刪除使用者（admin only）。不得刪除自己。"""
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="不可刪除自己的帳號")

    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="使用者不存在")

    await db.delete(target)
    await db.commit()


# ── Step-up 驗證 ──────────────────────────────────────────────
class StepUpRequest(BaseModel):
    password: str


@router.post("/step-up")
async def step_up(
    body: StepUpRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """二次身份驗證：輸入密碼後取得 5 分鐘有效的 step-up token。
    
    高風險操作（如刪除所有文件、匯出所有資料）前呼叫此端點，
    取得 step-up token 後以 X-Step-Up-Token header 傳入。
    """
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password):
        raise HTTPException(status_code=400, detail="密碼錯誤，step-up 驗證失敗")

    token = create_stepup_token(current_user.id)
    return {"step_up_token": token, "expires_in_seconds": 300}
