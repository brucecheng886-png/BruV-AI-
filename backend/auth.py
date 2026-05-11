"""
JWT 認證工具與依賴注入
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt as _bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from database import get_db
from models import User

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    sub: str        # user_id
    email: str
    role: str
    exp: datetime


# ── 密碼工具 ──────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Token 工具 ────────────────────────────────────────────────
def create_access_token(user_id: str, email: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "email": email, "role": role, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> TokenPayload:
    try:
        raw = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return TokenPayload(**raw)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無效或過期的 Token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


# ── FastAPI 依賴注入 ───────────────────────────────────────────
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要登入")

    payload = decode_token(credentials.credentials)
    result = await db.execute(select(User).where(User.id == payload.sub))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="使用者不存在")
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理員權限")
    return user


def require_role(roles: list[str]):
    """工廠函式：回傳一個只允許指定角色清單的 FastAPI dependency。"""
    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"此操作需要以下角色之一：{', '.join(roles)}",
            )
        return user
    return _check


CurrentUser  = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(get_current_admin)]


# ── Step-up Token ─────────────────────────────────────────────
_STEPUP_EXPIRE_MINUTES = 5
_STEPUP_CLAIM = "stepup"


def create_stepup_token(user_id: str) -> str:
    """建立 5 分鐘有效的 step-up JWT（含特殊 claim）"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=_STEPUP_EXPIRE_MINUTES)
    payload = {"sub": user_id, _STEPUP_CLAIM: True, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_stepup_token(token: str, user_id: str) -> bool:
    """驗證 step-up token 是否有效且屬於指定 user_id"""
    try:
        raw = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return raw.get("sub") == user_id and raw.get(_STEPUP_CLAIM) is True
    except JWTError:
        return False


def require_stepup():
    """FastAPI dependency：要求 X-Step-Up-Token header 且驗證通過"""
    async def _check(
        request,
        current_user: User = Depends(get_current_user),
    ) -> User:
        from fastapi import Request as _Request
        stepup_token = request.headers.get("X-Step-Up-Token", "")
        if not stepup_token or not verify_stepup_token(stepup_token, current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="此操作需要二次身份驗證，請先取得 step-up token（POST /api/auth/step-up）",
            )
        return current_user
    return _check


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> "User | None":
    """有 Token → 驗證並傳回 User；無 Token → 傳回 None（不強制登入）"""
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
    except HTTPException:
        return None
    result = await db.execute(select(User).where(User.id == payload.sub))
    return result.scalar_one_or_none()


OptionalCurrentUser = Annotated["User | None", Depends(get_optional_user)]
