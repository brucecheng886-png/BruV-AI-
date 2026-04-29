"""
Auth Router — 登入/登出/取得目前使用者/帳號管理
"""
import re
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_access_token, hash_password, verify_password, CurrentUser
from database import get_db
from models import User

router = APIRouter()

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+(\.[^\s@]+)?$")


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
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="帳號或密碼錯誤")

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
        if not EMAIL_RE.match(body.email):
            raise HTTPException(status_code=400, detail="Email 格式不正確")
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
        "display_name": getattr(user, "display_name", None),
        "created_at": user.created_at.isoformat() if user.created_at else None,
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
    if not EMAIL_RE.match(body.email):
        raise HTTPException(status_code=400, detail="Email 格式不正確")

    # 找預設 admin 列（email='admin@local'，密碼為 placeholder）
    result = await db.execute(select(User).where(User.email == "admin@local"))
    admin = result.scalar_one_or_none()

    if admin is None or "placeholder" not in (admin.password or ""):
        raise HTTPException(status_code=403, detail="管理員已初始化")

    if body.email != "admin@local":
        dup = await db.execute(
            select(User).where(User.email == body.email, User.id != admin.id)
        )
        if dup.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="此 Email 已被使用")

    admin.email = body.email
    admin.password = hash_password(body.password)
    admin.role = "admin"
    await db.commit()
    return {"success": True, "user_id": admin.id, "email": admin.email}
