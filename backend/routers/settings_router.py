"""
Settings Router — LLM Provider 雲端 API 設定 + RAG 參數 + 備份 + 使用者密碼
GET  /api/settings/llm            讀取 LLM 設定
POST /api/settings/llm            儲存 LLM 設定
POST /api/settings/llm/test       測試連線
GET  /api/settings/models         取得可用模型列表（帶即時檢測）
GET  /api/settings/rag            讀取 RAG 參數
POST /api/settings/rag            儲存 RAG 參數GET  /api/settings/chat           讀取對話行為設定
POST /api/settings/chat           儲存對話行為設定
GET  /api/settings/schema         讀取知識庫 Schema
PUT  /api/settings/schema         儲存知識庫 SchemaPOST /api/settings/backup/trigger 手動觸發備份
GET  /api/settings/backup/list    列出備份檔案
POST /api/settings/user/change-password 修改密碼
"""
import gzip
import json
import logging
import re
import smtplib
import ssl as _ssl
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, CurrentAdmin, hash_password, verify_password
from config import settings as app_settings
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
    "anthropic_api_key",
]

_PROVIDER_TEST_URLS = {
    "openai":     "https://api.openai.com/v1/models",
    "groq":       "https://api.groq.com/openai/v1/models",
    "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
    "anthropic":  "https://api.anthropic.com/v1/models",
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
    回傳 {provider, model, model_id, api_key}，若 DB 無設定回傳空 dict。

    `model_id` 為 system_settings 指定的 cloud_llm_model 在 llm_models 表中的 ID（若存在），
    供呼叫端二次 lookup model-level 的 base_url / api_key / 治理欄位。
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

    # 二次查詢 llm_models 取得 model_id（不影響原 fallback key 行為）
    model_id: str | None = None
    if model:
        from models import LLMModel as _LLMModel
        try:
            row = (await db.execute(
                select(_LLMModel.id).where(
                    _LLMModel.name == model,
                    _LLMModel.provider == provider,
                ).limit(1)
            )).first()
            if row:
                model_id = row[0]
        except Exception:
            pass

    return {
        "provider": provider,
        "model": model or None,
        "model_id": model_id,
        "api_key": api_key or None,
    }


# ── Schemas ───────────────────────────────────────────────────────────────────

class LlmSettingsOut(BaseModel):
    llm_provider: str
    cloud_llm_model: str
    openai_api_key_masked: str
    groq_api_key_masked: str
    gemini_api_key_masked: str
    openrouter_api_key_masked: str
    anthropic_api_key_masked: str


class LlmSettingsIn(BaseModel):
    llm_provider: str = "ollama"
    cloud_llm_model: Optional[str] = ""
    openai_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None


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
        anthropic_api_key_masked=_mask(rows.get("anthropic_api_key", "")),
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
        ("anthropic_api_key",  "anthropic_api_key"),
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
    if not body.api_key:
        raise HTTPException(status_code=400, detail="api_key 不能為空")

    # Anthropic 用自己的 header 格式
    if body.provider == "anthropic":
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": body.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
            if resp.status_code == 200:
                return {"ok": True, "message": "連線成功"}
            return {"ok": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    url = _PROVIDER_TEST_URLS.get(body.provider)
    if not url:
        raise HTTPException(status_code=400, detail=f"不支援的 provider: {body.provider}")

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


# ── 可用模型列表（含即時 Ollama / 雲端 API 檢測）──────────────────────────────

_EMBED_KEYWORDS = ("embed", "bge", "nomic", "rerank", "e5-")

_CLOUD_DEFAULTS = {
    "openai":     "gpt-4o-mini",
    "groq":       "llama-3.3-70b-versatile",
    "gemini":     "gemini-2.0-flash",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
    "anthropic":  "claude-sonnet-4-6",
}

_OPENAI_SKIP = ("embed", "audio", "tts", "whisper", "dall-e", "realtime", "vision-preview")


@router.get("/models")
async def get_available_models(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    """即時檢測並回傳當前 provider 的可用模型清單（含地端/雲端分組）"""
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key.in_(_LLM_KEYS))
    )
    rows = {r.key: r.value for r in result.scalars()}

    provider = rows.get("llm_provider", "").strip() or app_settings.LLM_PROVIDER
    db_default = rows.get("cloud_llm_model", "").strip() or None

    # ── 地端：一律嘗試抓 Ollama 模型 ─────────────────────────────────
    local_models: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{app_settings.OLLAMA_BASE_URL}/api/tags")
        if resp.status_code == 200:
            local_models = [
                m["name"] for m in resp.json().get("models", [])
                if not any(k in m["name"].lower() for k in _EMBED_KEYWORDS)
            ]
    except Exception:
        pass
    if not local_models:
        local_models = [app_settings.OLLAMA_LLM_MODEL]

    # ── 雲端：依設定的 cloud provider 抓清單 ────────────────────────
    cloud_models: list[str] = []
    cloud_provider = provider if provider != "ollama" else None
    if cloud_provider:
        api_key = rows.get(f"{cloud_provider}_api_key", "").strip()
        url = _PROVIDER_TEST_URLS.get(cloud_provider, "")
        if api_key and url:
            try:
                # Anthropic 用自己的 header 格式
                if cloud_provider == "anthropic":
                    headers: dict = {
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    }
                else:
                    headers = {"Authorization": f"Bearer {api_key}"}
                    if cloud_provider == "openrouter":
                        headers["HTTP-Referer"] = "http://localhost"
                async with httpx.AsyncClient(timeout=8) as client:
                    resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data_key = "data" if cloud_provider != "anthropic" else "models"
                    all_ids = [m.get("id", m) for m in resp.json().get(data_key, [])]
                    if cloud_provider == "anthropic":
                        # Anthropic 固定提供三個推薦模型（不過濾 API 回傳）
                        cloud_models = ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"]
                    else:
                        cloud_models = [
                            m for m in all_ids
                            if not any(k in m.lower() for k in _OPENAI_SKIP)
                        ]
            except Exception:
                pass
        if not cloud_models:
            if cloud_provider == "anthropic":
                cloud_models = ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"]
            else:
                cloud_default = db_default or _CLOUD_DEFAULTS.get(cloud_provider, "")
                if cloud_default:
                    cloud_models = [cloud_default]

    # ── 預設模型 ─────────────────────────────────────────────────────
    if provider == "ollama" or not cloud_provider:
        default_model = db_default or app_settings.OLLAMA_LLM_MODEL
    else:
        default_model = db_default or _CLOUD_DEFAULTS.get(provider, "")

    all_models = local_models + [m for m in cloud_models if m not in local_models]

    return {
        "models": all_models,
        "local": local_models,
        "cloud": cloud_models,
        "default": default_model,
        "provider": provider,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# RAG 參數設定
# ═══════════════════════════════════════════════════════════════════════════════

_RAG_DEFAULTS = {
    "rag_top_k":             "20",
    "rag_rerank_top_k":      "5",
    "rag_max_context_chars": "4000",
    "rag_rerank_enabled":    "true",
    "doc_chunk_size":        "400",
}
_RAG_KEYS = list(_RAG_DEFAULTS.keys())


class RagSettingsOut(BaseModel):
    rag_top_k: int
    rag_rerank_top_k: int
    rag_max_context_chars: int
    rag_rerank_enabled: bool
    doc_chunk_size: int


class RagSettingsIn(BaseModel):
    rag_top_k: int = 20
    rag_rerank_top_k: int = 5
    rag_max_context_chars: int = 4000
    rag_rerank_enabled: bool = True
    doc_chunk_size: int = 400


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
        "chunk_size":        int(rows.get("doc_chunk_size",        _RAG_DEFAULTS["doc_chunk_size"])),
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
        doc_chunk_size=int(rows.get("doc_chunk_size", _RAG_DEFAULTS["doc_chunk_size"])),
    )


@router.post("/rag")
async def save_rag_settings(
    body: RagSettingsIn,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    if not (1 <= body.rag_top_k <= 100):
        raise HTTPException(status_code=400, detail="top_k 需介於 1 ~ 100")
    if not (1 <= body.rag_rerank_top_k <= body.rag_top_k):
        raise HTTPException(status_code=400, detail="rerank_top_k 需介於 1 ~ top_k")
    if not (500 <= body.rag_max_context_chars <= 32000):
        raise HTTPException(status_code=400, detail="max_context_chars 需介於 500 ~ 32000")
    if not (100 <= body.doc_chunk_size <= 2000):
        raise HTTPException(status_code=400, detail="Chunk 大小需介於 100 ~ 2000")
    updates = {
        "rag_top_k":             str(body.rag_top_k),
        "rag_rerank_top_k":      str(body.rag_rerank_top_k),
        "rag_max_context_chars": str(body.rag_max_context_chars),
        "rag_rerank_enabled":    "true" if body.rag_rerank_enabled else "false",
        "doc_chunk_size":        str(body.doc_chunk_size),
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


# ═══════════════════════════════════════════════════════════════════════════════
# 知識庫 Schema（注入 RAG System Prompt 的結構定義）
# ═══════════════════════════════════════════════════════════════════════════════

_SCHEMA_KEY = "kb_schema"
_SCHEMA_DEFAULT = """\
# 知識庫結構說明

## 用途
本知識庫為地端 AI 問答系統，收錄組織內部文件、研究報告與知識。

## 回答準則
- 優先引用知識庫中的文件作為依據
- 若知識庫資料不足，應如實說明，不得臆測
- 回答時標明來源文件名稱

## 領域範疇
（請在此填寫本知識庫的主要領域，例如：生物資訊、法規文件、技術手冊…）
"""


class SchemaOut(BaseModel):
    schema_text: str


class SchemaIn(BaseModel):
    schema_text: str


async def get_kb_schema(db: AsyncSession) -> str:
    """供 chat.py 呼叫：讀取 KB Schema 文字"""
    row = await db.get(SystemSetting, _SCHEMA_KEY)
    return row.value if row else ""


@router.get("/schema", response_model=SchemaOut)
async def get_schema(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    row = await db.get(SystemSetting, _SCHEMA_KEY)
    return SchemaOut(schema_text=row.value if row else _SCHEMA_DEFAULT)


@router.put("/schema")
async def save_schema(
    body: SchemaIn,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    existing = await db.get(SystemSetting, _SCHEMA_KEY)
    if existing:
        existing.value = body.schema_text
    else:
        db.add(SystemSetting(key=_SCHEMA_KEY, value=body.schema_text))
    await db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# 對話行為設定（Temperature / Max Tokens / 歷史輪數 / System Prompt / Chunk Size）
# ═══════════════════════════════════════════════════════════════════════════════

_CHAT_DEFAULTS = {
    "chat_temperature":    "0.7",
    "chat_max_tokens":     "2048",
    "chat_history_rounds": "10",
    "chat_system_prompt":  "",
    "doc_analysis_model":  "",
    "chat_reflection_enabled": "false",
    "prompt_template_auto_match": "false",
}
_CHAT_KEYS = list(_CHAT_DEFAULTS.keys())


class ChatSettingsOut(BaseModel):
    chat_temperature: float
    chat_max_tokens: int
    chat_history_rounds: int
    chat_system_prompt: str
    doc_analysis_model: str = ""
    chat_reflection_enabled: bool = False
    prompt_template_auto_match: bool = False


class ChatSettingsIn(BaseModel):
    chat_temperature: float = 0.7
    chat_max_tokens: int = 2048
    chat_history_rounds: int = 10
    chat_system_prompt: str = ""
    doc_analysis_model: str = ""
    chat_reflection_enabled: bool = False
    prompt_template_auto_match: bool = False


async def get_chat_runtime_config(db: AsyncSession) -> dict:
    """供 chat.py / document_tasks.py 呼叫：讀取對話行為動態設定"""
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key.in_(_CHAT_KEYS))
    )
    rows = {r.key: r.value for r in result.scalars()}
    return {
        "temperature":    float(rows.get("chat_temperature",    _CHAT_DEFAULTS["chat_temperature"])),
        "max_tokens":     int(rows.get("chat_max_tokens",       _CHAT_DEFAULTS["chat_max_tokens"])),
        "history_rounds": int(rows.get("chat_history_rounds",   _CHAT_DEFAULTS["chat_history_rounds"])),
        "system_prompt":  rows.get("chat_system_prompt",        _CHAT_DEFAULTS["chat_system_prompt"]),
        "prompt_template_auto_match": str(rows.get("prompt_template_auto_match", _CHAT_DEFAULTS["prompt_template_auto_match"])).strip().lower() in ("1", "true", "on", "yes"),
    }


@router.get("/chat", response_model=ChatSettingsOut)
async def get_chat_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key.in_(_CHAT_KEYS))
    )
    rows = {r.key: r.value for r in result.scalars()}
    return ChatSettingsOut(
        chat_temperature=float(rows.get("chat_temperature",     _CHAT_DEFAULTS["chat_temperature"])),
        chat_max_tokens=int(rows.get("chat_max_tokens",         _CHAT_DEFAULTS["chat_max_tokens"])),
        chat_history_rounds=int(rows.get("chat_history_rounds", _CHAT_DEFAULTS["chat_history_rounds"])),
        chat_system_prompt=rows.get("chat_system_prompt",       _CHAT_DEFAULTS["chat_system_prompt"]),
        doc_analysis_model=rows.get("doc_analysis_model",       _CHAT_DEFAULTS["doc_analysis_model"]),
        chat_reflection_enabled=str(rows.get("chat_reflection_enabled", _CHAT_DEFAULTS["chat_reflection_enabled"])).strip().lower() in ("1", "true", "on", "yes"),
        prompt_template_auto_match=str(rows.get("prompt_template_auto_match", _CHAT_DEFAULTS["prompt_template_auto_match"])).strip().lower() in ("1", "true", "on", "yes"),
    )


@router.post("/chat")
async def save_chat_settings(
    body: ChatSettingsIn,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    if not (0.0 <= body.chat_temperature <= 2.0):
        raise HTTPException(status_code=400, detail="Temperature 需介於 0.0 ~ 2.0")
    if not (256 <= body.chat_max_tokens <= 16384):
        raise HTTPException(status_code=400, detail="Max tokens 需介於 256 ~ 16384")
    if not (1 <= body.chat_history_rounds <= 50):
        raise HTTPException(status_code=400, detail="歷史輪數需介於 1 ~ 50")

    updates = {
        "chat_temperature":    str(body.chat_temperature),
        "chat_max_tokens":     str(body.chat_max_tokens),
        "chat_history_rounds": str(body.chat_history_rounds),
        "chat_system_prompt":  body.chat_system_prompt,
        "doc_analysis_model":  body.doc_analysis_model,
        "chat_reflection_enabled": "true" if body.chat_reflection_enabled else "false",
        "prompt_template_auto_match": "true" if body.prompt_template_auto_match else "false",
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
# SMTP 郵件設定（管理員專用）
# GET  /api/settings/smtp         讀取 SMTP 設定（密碼遮蔽）
# PUT  /api/settings/smtp         儲存 SMTP 設定
# POST /api/settings/smtp/test    傳送測試郵件
# ═══════════════════════════════════════════════════════════════════════════════

_SMTP_KEYS = ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from_name", "smtp_tls"]
_SMTP_DEFAULTS: dict[str, str] = {
    "smtp_host":      "",
    "smtp_port":      "587",
    "smtp_user":      "",
    "smtp_password":  "",
    "smtp_from_name": "BruV AI",
    "smtp_tls":       "true",
}


class SmtpSettingsOut(BaseModel):
    smtp_host:      str = ""
    smtp_port:      int = 587
    smtp_user:      str = ""
    smtp_password:  str = ""
    smtp_from_name: str = "BruV AI"
    smtp_tls:       bool = True


class SmtpSettingsIn(BaseModel):
    smtp_host:      str
    smtp_port:      int = 587
    smtp_user:      str = ""
    smtp_password:  str = ""
    smtp_from_name: str = "BruV AI"
    smtp_tls:       bool = True


async def _read_smtp(db: AsyncSession) -> dict:
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key.in_(_SMTP_KEYS))
    )
    rows = {r.key: r.value for r in result.scalars()}
    return {k: rows.get(k, v) for k, v in _SMTP_DEFAULTS.items()}


@router.get("/smtp", response_model=SmtpSettingsOut)
async def get_smtp_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentAdmin = None,
):
    cfg = await _read_smtp(db)
    return SmtpSettingsOut(
        smtp_host=cfg["smtp_host"],
        smtp_port=int(cfg["smtp_port"]),
        smtp_user=cfg["smtp_user"],
        smtp_password="***" if cfg["smtp_password"] else "",
        smtp_from_name=cfg["smtp_from_name"],
        smtp_tls=cfg["smtp_tls"].lower() in ("1", "true", "on", "yes"),
    )


@router.put("/smtp")
async def save_smtp_settings(
    body: SmtpSettingsIn,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentAdmin = None,
):
    if not (1 <= body.smtp_port <= 65535):
        raise HTTPException(status_code=400, detail="Port 需介於 1 ~ 65535")

    smtp_updates: dict[str, str] = {
        "smtp_host":      body.smtp_host,
        "smtp_port":      str(body.smtp_port),
        "smtp_user":      body.smtp_user,
        "smtp_from_name": body.smtp_from_name,
        "smtp_tls":       "true" if body.smtp_tls else "false",
    }
    if body.smtp_password and body.smtp_password != "***":
        smtp_updates["smtp_password"] = body.smtp_password

    for k, v in smtp_updates.items():
        existing = await db.get(SystemSetting, k)
        if existing:
            existing.value = v
        else:
            db.add(SystemSetting(key=k, value=v))
    await db.commit()
    return {"ok": True}


@router.post("/smtp/test")
async def test_smtp(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentAdmin = None,
):
    cfg = await _read_smtp(db)
    host = cfg["smtp_host"]
    port = int(cfg["smtp_port"])
    user = cfg["smtp_user"]
    password = cfg["smtp_password"]
    from_name = cfg["smtp_from_name"]
    use_tls = cfg["smtp_tls"].lower() in ("1", "true", "on", "yes")

    if not host:
        raise HTTPException(status_code=400, detail="SMTP 主機尚未設定")

    to_email = current_user.email
    msg = MIMEText("這是 BruV AI 的 SMTP 測試信，設定正確！", "plain", "utf-8")
    msg["Subject"] = "BruV AI SMTP 測試"
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
        raise HTTPException(status_code=502, detail=f"SMTP 發送失敗：{e}")

    return {"ok": True, "message": f"測試郵件已寄送至 {to_email}"}


# ═══════════════════════════════════════════════════════════════════════════════
# Ollama 模型下載（SSE 串流進度）
# ═══════════════════════════════════════════════════════════════════════════════

class OllamaPullBody(BaseModel):
    model: str


class OllamaDeleteBody(BaseModel):
    model: str


@router.get("/ollama/installed")
async def get_installed_ollama_models(
    current_user: CurrentAdmin = None,
):
    """回傳目前 Ollama 已安裝的模型名稱列表。"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{app_settings.OLLAMA_BASE_URL}/api/tags")
        if resp.status_code == 200:
            names = [m["name"] for m in resp.json().get("models", [])]
            return {"models": names}
    except Exception as e:
        logger.warning("get_installed_ollama_models failed: %s", e)
    return {"models": []}


@router.delete("/ollama/delete")
async def delete_ollama_model(
    body: OllamaDeleteBody,
    current_user: CurrentAdmin = None,
):
    """刪除 Ollama 已安裝的模型。"""
    model_name = body.model.strip()
    if not model_name or '..' in model_name or not re.match(r'^[\w./:@-]+$', model_name):
        raise HTTPException(status_code=400, detail="無效的模型名稱")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(
                f"{app_settings.OLLAMA_BASE_URL}/api/delete",
                json={"name": model_name},
            )
        if resp.status_code not in (200, 204):
            raise HTTPException(status_code=502, detail=f"Ollama 回傳 {resp.status_code}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_ollama_model failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
    return {"ok": True}


@router.post("/ollama/pull")
async def pull_ollama_model(
    body: OllamaPullBody,
    current_user: CurrentAdmin = None,
):
    """透過 Ollama 下載模型，以 SSE 串流回傳進度。"""
    model_name = body.model.strip()
    if not model_name or '..' in model_name or not re.match(r'^[\w./:@-]+$', model_name):
        raise HTTPException(status_code=400, detail="無效的模型名稱")

    async def event_stream():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{app_settings.OLLAMA_BASE_URL}/api/pull",
                    json={"name": model_name, "stream": True},
                ) as resp:
                    if resp.status_code != 200:
                        err_body = await resp.aread()
                        err_text = err_body[:200].decode("utf-8", errors="replace")
                        payload = json.dumps({"error": f"Ollama 回傳 {resp.status_code}: {err_text}"})
                        yield f"data: {payload}\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            logger.error("Ollama pull error: %s", e)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

