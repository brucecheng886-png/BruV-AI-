"""
FIDO2 / WebAuthn 端點 — 真實實作

使用 webauthn==2.2.0 (py-webauthn) 完整實作 Register 與 Login 流程。
Challenge 存放於 Redis（TTL 30 秒），credential 存放於 fido_credentials 表。

開發測試：Chrome DevTools → Application → Sensors → Virtual Authenticator
"""
import base64
import json
import logging
import os
from typing import Any

import redis as redis_sync
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from auth import CurrentUser, create_access_token
from database import get_db
from models import FIDOCredential, User
from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Redis (同步) ─────────────────────────────────────────────
_redis: redis_sync.Redis | None = None

def _get_redis() -> redis_sync.Redis:
    global _redis
    if _redis is None:
        _redis = redis_sync.from_url(
            settings.REDIS_URL.replace("/0", "/4"),  # DB4 for FIDO2 challenges
            decode_responses=True,
        )
    return _redis

_CHALLENGE_TTL = 30  # seconds
_RP_ID = os.getenv("WEBAUTHN_RP_ID", "localhost")
_RP_NAME = os.getenv("WEBAUTHN_RP_NAME", "地端 AI 知識庫")
_ORIGIN = os.getenv("WEBAUTHN_ORIGIN", "http://localhost")

# ── Helpers ──────────────────────────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))

# ── Pydantic Schemas ──────────────────────────────────────────

class RegisterCompleteRequest(BaseModel):
    challenge_id: str
    credential: dict[str, Any]
    key_name: str = "我的安全金鑰"

class LoginBeginRequest(BaseModel):
    email: str

class LoginCompleteRequest(BaseModel):
    challenge_id: str
    credential: dict[str, Any]

class FIDOKeyInfo(BaseModel):
    id: int
    name: str
    created_at: str

# ── 端點 ──────────────────────────────────────────────────────

@router.post("/register/begin")
async def register_begin(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """開始 FIDO2 註冊。回傳 PublicKeyCredentialCreationOptions。"""
    try:
        import webauthn
        from webauthn.helpers.structs import (
            AuthenticatorSelectionCriteria,
            UserVerificationRequirement,
            ResidentKeyRequirement,
            PublicKeyCredentialDescriptor,
        )
    except ImportError:
        raise HTTPException(500, "webauthn 套件未安裝")

    result = await db.execute(
        select(FIDOCredential).where(FIDOCredential.user_id == current_user.id)
    )
    existing = result.scalars().all()
    exclude_credentials = [
        PublicKeyCredentialDescriptor(id=c.credential_id) for c in existing
    ]

    options = webauthn.generate_registration_options(
        rp_id=_RP_ID,
        rp_name=_RP_NAME,
        user_id=current_user.id.encode(),
        user_name=current_user.email,
        user_display_name=getattr(current_user, "display_name", None) or current_user.email,
        exclude_credentials=exclude_credentials,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.PREFERRED,
            resident_key=ResidentKeyRequirement.PREFERRED,
        ),
    )

    challenge_id = _b64url_encode(os.urandom(16))
    r = _get_redis()
    r.setex(
        f"fido2:reg:{challenge_id}",
        _CHALLENGE_TTL,
        json.dumps({"challenge": _b64url_encode(options.challenge), "user_id": current_user.id}),
    )

    options_dict = json.loads(webauthn.options_to_json(options))
    return {"challenge_id": challenge_id, "options": options_dict}


@router.post("/register/complete")
async def register_complete(
    body: RegisterCompleteRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """完成 FIDO2 註冊，驗證 attestation 並儲存 credential。"""
    try:
        import webauthn
    except ImportError:
        raise HTTPException(500, "webauthn 套件未安裝")

    r = _get_redis()
    raw = r.get(f"fido2:reg:{body.challenge_id}")
    if not raw:
        raise HTTPException(400, "challenge 不存在或已過期")
    stored = json.loads(raw)
    if stored["user_id"] != current_user.id:
        raise HTTPException(400, "challenge 使用者不符")
    r.delete(f"fido2:reg:{body.challenge_id}")

    try:
        verification = webauthn.verify_registration_response(
            credential=body.credential,
            expected_challenge=_b64url_decode(stored["challenge"]),
            expected_rp_id=_RP_ID,
            expected_origin=_ORIGIN,
        )
    except Exception as e:
        logger.warning("FIDO2 register_complete failed: %s", e)
        raise HTTPException(400, f"FIDO2 驗證失敗：{e}")

    credential = FIDOCredential(
        user_id=current_user.id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        name=body.key_name,
    )
    db.add(credential)
    await db.commit()

    return {
        "status": "ok",
        "credential_id": _b64url_encode(verification.credential_id),
        "key_name": body.key_name,
    }


@router.post("/login/begin")
async def login_begin(
    body: LoginBeginRequest,
    db: AsyncSession = Depends(get_db),
):
    """開始 FIDO2 登入（不需 JWT）。回傳 PublicKeyCredentialRequestOptions。"""
    try:
        import webauthn
        from webauthn.helpers.structs import UserVerificationRequirement, PublicKeyCredentialDescriptor
    except ImportError:
        raise HTTPException(500, "webauthn 套件未安裝")

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "使用者不存在")

    cred_result = await db.execute(
        select(FIDOCredential).where(FIDOCredential.user_id == user.id)
    )
    credentials = cred_result.scalars().all()
    if not credentials:
        raise HTTPException(400, "此帳號尚未綁定任何安全金鑰")

    allow_credentials = [
        PublicKeyCredentialDescriptor(id=c.credential_id) for c in credentials
    ]
    options = webauthn.generate_authentication_options(
        rp_id=_RP_ID,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    challenge_id = _b64url_encode(os.urandom(16))
    r = _get_redis()
    r.setex(
        f"fido2:auth:{challenge_id}",
        _CHALLENGE_TTL,
        json.dumps({"challenge": _b64url_encode(options.challenge), "user_id": user.id}),
    )
    options_dict = json.loads(webauthn.options_to_json(options))
    return {"challenge_id": challenge_id, "options": options_dict}


@router.post("/login/complete")
async def login_complete(
    body: LoginCompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """完成 FIDO2 登入，驗證 assertion 並回傳 JWT。"""
    try:
        import webauthn
    except ImportError:
        raise HTTPException(500, "webauthn 套件未安裝")

    r = _get_redis()
    raw = r.get(f"fido2:auth:{body.challenge_id}")
    if not raw:
        raise HTTPException(400, "challenge 不存在或已過期")
    stored = json.loads(raw)
    r.delete(f"fido2:auth:{body.challenge_id}")

    user_id = stored["user_id"]
    raw_id_str = body.credential.get("rawId") or body.credential.get("id", "")
    try:
        raw_id_bytes = _b64url_decode(raw_id_str)
    except Exception:
        raise HTTPException(400, "credential id 格式錯誤")

    cred_result = await db.execute(
        select(FIDOCredential).where(
            FIDOCredential.user_id == user_id,
            FIDOCredential.credential_id == raw_id_bytes,
        )
    )
    cred = cred_result.scalar_one_or_none()
    if cred is None:
        raise HTTPException(400, "找不到對應的安全金鑰")

    try:
        verification = webauthn.verify_authentication_response(
            credential=body.credential,
            expected_challenge=_b64url_decode(stored["challenge"]),
            expected_rp_id=_RP_ID,
            expected_origin=_ORIGIN,
            credential_public_key=cred.public_key,
            credential_current_sign_count=cred.sign_count,
        )
    except Exception as e:
        logger.warning("FIDO2 login_complete failed: %s", e)
        raise HTTPException(400, f"FIDO2 驗證失敗：{e}")

    # 更新 sign_count（防重放攻擊）
    cred.sign_count = verification.new_sign_count
    await db.commit()

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(403, "帳號不存在或已停用")

    access_token = create_access_token(user.id, user.email, user.role)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/keys", response_model=list[FIDOKeyInfo])
async def list_keys(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """列出目前使用者已註冊的所有 FIDO2 金鑰。"""
    result = await db.execute(
        select(FIDOCredential).where(FIDOCredential.user_id == current_user.id)
    )
    credentials = result.scalars().all()
    return [
        FIDOKeyInfo(id=c.id, name=c.name, created_at=c.created_at.isoformat())
        for c in credentials
    ]


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(
    key_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """刪除指定的 FIDO2 金鑰（只能刪除自己的金鑰）。"""
    result = await db.execute(
        select(FIDOCredential).where(
            FIDOCredential.id == key_id,
            FIDOCredential.user_id == current_user.id,
        )
    )
    credential = result.scalar_one_or_none()
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="金鑰不存在")
    await db.delete(credential)
    await db.commit()
