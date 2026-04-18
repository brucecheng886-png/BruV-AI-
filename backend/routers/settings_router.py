"""
Settings Router — LLM Provider 雲端 API 設定 + RAG 參數 + 備份 + 使用者密碼
GET  /api/settings/llm            讀取 LLM 設定
POST /api/settings/llm            儲存 LLM 設定
POST /api/settings/llm/test       測試連線
GET  /api/settings/rag            讀取 RAG 參數
POST /api/settings/rag            儲存 RAG 參數
POST /api/settings/backup/trigger 手動觸發備份
GET  /api/settings/backup/list    列出備份檔案
POST /api/settings/user/change-password 修改密碼
"""
import gzip
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, hash_password, verify_password
from database import get_db
from models import SystemSetting, User

logger = logging.getLogger(__name__)
router = APIRouter()

_LLM_KEYS = [
    "llm_provider",
    "cloud_llm_model",
    "openai_api_key",
    "groq_api_key",
    "gemini_api_key",
    "openrouter_api_key",
]

_PROVIDER_TEST_URLS = {
    "openai":     "https://api.openai.com/v1/models",
    "groq":       "https://api.groq.com/openai/v1/models",
    "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
}


def _mask(key: str) -> str:
    """只顯示尾 4 碼"""
    if not key or len(key) <= 4:
        return "****" if key else ""
    return "*" * (len(key) - 4) + key[-4:]


# ── 共用：讀取 DB 設定（供 chat.py 呼叫）──────────────────────────────────────

async def get_llm_runtime_config(db: AsyncSession) -> dict:
    """
    從 system_settings 讀取 LLM 執行時設定。
    回傳 {provider, model, api_key}，若 DB 無設定回傳空 dict。
    """
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key.in_(_LLM_KEYS))
    )
    rows = {r.key: r.value for r in result.scalars()}

    provider = rows.get("llm_provider", "").strip()
    if not provider or provider == "ollama":
        return {}  # 沿用 env 設定

    model    = rows.get("cloud_llm_model", "").strip()
    api_key  = rows.get(f"{provider}_api_key", "").strip()

    return {"provider": provider, "model": model or None, "api_key": api_key or None}


# ── Schemas ───────────────────────────────────────────────────────────────────

class LlmSettingsOut(BaseModel):
    llm_provider: str
    cloud_llm_model: str
    openai_api_key_masked: str
    groq_api_key_masked: str
    gemini_api_key_masked: str
    openrouter_api_key_masked: str


class LlmSettingsIn(BaseModel):
    llm_provider: str = "ollama"
    cloud_llm_model: Optional[str] = ""
    openai_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None


class TestBody(BaseModel):
    provider: str
    api_key: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/llm", response_model=LlmSettingsOut)
async def get_llm_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key.in_(_LLM_KEYS))
    )
    rows = {r.key: r.value for r in result.scalars()}
    return LlmSettingsOut(
        llm_provider=rows.get("llm_provider", "ollama"),
        cloud_llm_model=rows.get("cloud_llm_model", ""),
        openai_api_key_masked=_mask(rows.get("openai_api_key", "")),
        groq_api_key_masked=_mask(rows.get("groq_api_key", "")),
        gemini_api_key_masked=_mask(rows.get("gemini_api_key", "")),
        openrouter_api_key_masked=_mask(rows.get("openrouter_api_key", "")),
    )


@router.post("/llm")
async def save_llm_settings(
    body: LlmSettingsIn,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    updates = {
        "llm_provider":      body.llm_provider,
        "cloud_llm_model":   body.cloud_llm_model or "",
    }
    # 只有明確傳入才更新 API key（None = 不動，""= 清空）
    for field, key in [
        ("openai_api_key",     "openai_api_key"),
        ("groq_api_key",       "groq_api_key"),
        ("gemini_api_key",     "gemini_api_key"),
        ("openrouter_api_key", "openrouter_api_key"),
    ]:
        val = getattr(body, field)
        if val is not None:
            updates[key] = val

    for k, v in updates.items():
        existing = await db.get(SystemSetting, k)
        if existing:
            existing.value = v
        else:
            db.add(SystemSetting(key=k, value=v))
    await db.commit()
    return {"ok": True}


@router.post("/llm/test")
async def test_llm_connection(
    body: TestBody,
    current_user: CurrentUser = None,
):
    url = _PROVIDER_TEST_URLS.get(body.provider)
    if not url:
        raise HTTPException(status_code=400, detail=f"不支援的 provider: {body.provider}")
    if not body.api_key:
        raise HTTPException(status_code=400, detail="api_key 不能為空")

    headers = {"Authorization": f"Bearer {body.api_key}"}
    if body.provider == "openrouter":
        headers["HTTP-Referer"] = "http://localhost"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return {"ok": True, "message": "連線成功"}
        return {"ok": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# RAG 參數設定
# ═══════════════════════════════════════════════════════════════════════════════

_RAG_DEFAULTS = {
    "rag_top_k":             "20",
    "rag_rerank_top_k":      "5",
    "rag_max_context_chars": "4000",
    "rag_rerank_enabled":    "true",
}
_RAG_KEYS = list(_RAG_DEFAULTS.keys())


class RagSettingsOut(BaseModel):
    rag_top_k: int
    rag_rerank_top_k: int
    rag_max_context_chars: int
    rag_rerank_enabled: bool


class RagSettingsIn(BaseModel):
    rag_top_k: int = 20
    rag_rerank_top_k: int = 5
    rag_max_context_chars: int = 4000
    rag_rerank_enabled: bool = True


async def get_rag_runtime_config(db: AsyncSession) -> dict:
    """供 chat.py 呼叫：讀取 RAG 動態設定"""
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key.in_(_RAG_KEYS))
    )
    rows = {r.key: r.value for r in result.scalars()}
    return {
        "top_k":             int(rows.get("rag_top_k",             _RAG_DEFAULTS["rag_top_k"])),
        "rerank_top_k":      int(rows.get("rag_rerank_top_k",      _RAG_DEFAULTS["rag_rerank_top_k"])),
        "max_context_chars": int(rows.get("rag_max_context_chars", _RAG_DEFAULTS["rag_max_context_chars"])),
        "rerank_enabled":    rows.get("rag_rerank_enabled",        _RAG_DEFAULTS["rag_rerank_enabled"]) == "true",
    }


@router.get("/rag", response_model=RagSettingsOut)
async def get_rag_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key.in_(_RAG_KEYS))
    )
    rows = {r.key: r.value for r in result.scalars()}
    return RagSettingsOut(
        rag_top_k=int(rows.get("rag_top_k", _RAG_DEFAULTS["rag_top_k"])),
        rag_rerank_top_k=int(rows.get("rag_rerank_top_k", _RAG_DEFAULTS["rag_rerank_top_k"])),
        rag_max_context_chars=int(rows.get("rag_max_context_chars", _RAG_DEFAULTS["rag_max_context_chars"])),
        rag_rerank_enabled=(rows.get("rag_rerank_enabled", _RAG_DEFAULTS["rag_rerank_enabled"]) == "true"),
    )


@router.post("/rag")
async def save_rag_settings(
    body: RagSettingsIn,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    updates = {
        "rag_top_k":             str(body.rag_top_k),
        "rag_rerank_top_k":      str(body.rag_rerank_top_k),
        "rag_max_context_chars": str(body.rag_max_context_chars),
        "rag_rerank_enabled":    "true" if body.rag_rerank_enabled else "false",
    }
    for k, v in updates.items():
        existing = await db.get(SystemSetting, k)
        if existing:
            existing.value = v
        else:
            db.add(SystemSetting(key=k, value=v))
    await db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# 備份管理
# ═══════════════════════════════════════════════════════════════════════════════

_BACKUP_PREFIX = "backups/"


@router.post("/backup/trigger")
async def trigger_backup(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    """手動觸發備份：匯出 system_settings + llm_models + Qdrant snapshot → MinIO"""
    from config import settings as app_settings
    from services.storage import get_minio_client

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results = []

    # 1. 匯出 PostgreSQL system_settings + llm_models 為 JSON
    try:
        s_result = await db.execute(select(SystemSetting))
        ss_rows = [{"key": r.key, "value": r.value} for r in s_result.scalars()]

        from models import LLMModel
        m_result = await db.execute(select(LLMModel))
        lm_rows = [
            {c.key: getattr(row, c.key) for c in row.__table__.columns}
            for row in m_result.scalars()
        ]

        payload = json.dumps({"system_settings": ss_rows, "llm_models": lm_rows},
                             ensure_ascii=False, default=str)
        compressed = gzip.compress(payload.encode())
        obj_name = f"{_BACKUP_PREFIX}pg_{ts}.json.gz"
        client = get_minio_client()
        from io import BytesIO
        client.put_object(
            app_settings.MINIO_BUCKET, obj_name,
            BytesIO(compressed), length=len(compressed),
            content_type="application/gzip",
        )
        results.append({"type": "postgres", "file": obj_name, "ok": True})
    except Exception as e:
        results.append({"type": "postgres", "ok": False, "error": str(e)})

    # 2. Qdrant snapshot
    try:
        async with httpx.AsyncClient(timeout=30) as hc:
            resp = await hc.post(
                f"http://{app_settings.QDRANT_HOST}:{app_settings.QDRANT_PORT}"
                f"/collections/{app_settings.QDRANT_COLLECTION}/snapshots"
            )
        snap = resp.json().get("result", {})
        results.append({"type": "qdrant", "snapshot": snap.get("name", ""), "ok": resp.status_code == 200})
    except Exception as e:
        results.append({"type": "qdrant", "ok": False, "error": str(e)})

    any_ok = any(r["ok"] for r in results)
    return {"ok": any_ok, "timestamp": ts, "results": results}


@router.get("/backup/list")
async def list_backups(
    current_user: CurrentUser = None,
):
    """列出 MinIO 中的備份檔案"""
    from config import settings as app_settings
    from services.storage import get_minio_client

    try:
        client = get_minio_client()
        objects = client.list_objects(app_settings.MINIO_BUCKET, prefix=_BACKUP_PREFIX, recursive=True)
        files = []
        for obj in objects:
            files.append({
                "name": obj.object_name.replace(_BACKUP_PREFIX, ""),
                "size": obj.size,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
            })
        files.sort(key=lambda x: x["last_modified"] or "", reverse=True)
        return {"files": files}
    except Exception as e:
        return {"files": [], "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 使用者密碼修改
# ═══════════════════════════════════════════════════════════════════════════════

class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/user/change-password")
async def change_password(
    body: ChangePasswordIn,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="新密碼至少需要 8 個字元")

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="使用者不存在")

    if not verify_password(body.current_password, user.password):
        raise HTTPException(status_code=400, detail="目前密碼錯誤")

    user.password = hash_password(body.new_password)
    await db.commit()
    return {"ok": True, "message": "密碼已更新"}

