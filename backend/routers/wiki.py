"""
Wiki Router ??LLM 璅∪?鞈? CRUD + ?拇芋?蒂??頛?"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser
from database import get_db
from models import LLMModel
from utils.crypto import encrypt_secret, decrypt_secret

logger = logging.getLogger(__name__)
router = APIRouter()


# ?? Pydantic Schemas ??????????????????????????????????????????????????????????

class LLMModelIn(BaseModel):
    name: str
    family: Optional[str] = None
    developer: Optional[str] = None
    params_b: Optional[float] = None
    context_length: Optional[int] = None
    license: Optional[str] = None
    tags: list[str] = []
    benchmarks: dict = {}
    quantizations: dict = {}
    ollama_id: Optional[str] = None
    hf_id: Optional[str] = None
    # RAGFlow-aligned
    model_type: Optional[str] = "chat"
    max_tokens: Optional[int] = None
    vision_support: Optional[bool] = False
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None     # 明文，儲入時加密；None 表示不變更
    # 治理欄位（Phase A2）
    enabled: Optional[bool] = True
    is_default: Optional[bool] = False
    monthly_quota_usd: Optional[float] = None


class LLMModelGovernanceIn(BaseModel):
    """模型治理欄位的局部更新（enable / default / quota 三欄）"""
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    monthly_quota_usd: Optional[float] = None


class LLMModelOut(BaseModel):
    id: str
    name: str
    family: Optional[str]
    developer: Optional[str]
    params_b: Optional[float]
    context_length: Optional[int]
    license: Optional[str]
    tags: list[str]
    benchmarks: dict
    quantizations: dict
    ollama_id: Optional[str]
    hf_id: Optional[str]
    model_type: str
    max_tokens: Optional[int]
    vision_support: bool
    provider: Optional[str]
    base_url: Optional[str]
    has_api_key: bool         # 是否已儲存 API Key（不暴露原文）
    enabled: bool
    is_default: bool
    monthly_quota_usd: Optional[float]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class VerifyModelIn(BaseModel):
    provider: str
    model_name: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_id: Optional[str] = None    # 提供則從 DB 讀取儲存的 key


def _to_out(m: LLMModel) -> LLMModelOut:
    return LLMModelOut(
        id=m.id,
        name=m.name,
        family=m.family,
        developer=m.developer,
        params_b=m.params_b,
        context_length=m.context_length,
        license=m.license,
        tags=m.tags or [],
        benchmarks=m.benchmarks or {},
        quantizations=m.quantizations or {},
        ollama_id=m.ollama_id,
        hf_id=m.hf_id,
        model_type=m.model_type or "chat",
        max_tokens=m.max_tokens,
        vision_support=m.vision_support or False,
        provider=m.provider,
        base_url=m.base_url,
        has_api_key=bool(getattr(m, "api_key", None)),
        enabled=bool(getattr(m, "enabled", True)),
        is_default=bool(getattr(m, "is_default", False)),
        monthly_quota_usd=float(m.monthly_quota_usd) if getattr(m, "monthly_quota_usd", None) is not None else None,
        created_at=m.created_at.isoformat(),
        updated_at=m.updated_at.isoformat(),
    )


# ?? CRUD ??????????????????????????????????????????????????????????????????????

@router.get("/models", response_model=list[LLMModelOut])
async def list_models(
    q: Optional[str] = Query(None, description="?迂璅∠???"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    stmt = select(LLMModel).order_by(LLMModel.name).limit(limit).offset(offset)
    if q:
        stmt = stmt.where(LLMModel.name.ilike(f"%{q}%"))
    result = await db.execute(stmt)
    return [_to_out(m) for m in result.scalars().all()]


@router.post("/models", response_model=LLMModelOut, status_code=201)
async def create_model(
    body: LLMModelIn,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    data = body.model_dump()
    raw_key = data.pop("api_key", None)
    # is_default 互斥（同 model_type 只能有一個）
    if data.get("is_default"):
        from sqlalchemy import update as _sa_update
        await db.execute(
            _sa_update(LLMModel)
            .where(LLMModel.model_type == (data.get("model_type") or "chat"))
            .values(is_default=False)
        )
    m = LLMModel(**data)
    if raw_key:
        m.api_key = encrypt_secret(raw_key)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return _to_out(m)


@router.get("/models/{model_id}", response_model=LLMModelOut)
async def get_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Model not found")
    return _to_out(m)


@router.put("/models/{model_id}", response_model=LLMModelOut)
async def update_model(
    model_id: str,
    body: LLMModelIn,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Model not found")
    data = body.model_dump(exclude_unset=True)
    raw_key = data.pop("api_key", None)  # None 表示未傳入，不變更
    # is_default 互斥（同 model_type 只能有一個）
    if data.get("is_default") is True:
        from sqlalchemy import update as _sa_update
        target_type = data.get("model_type") or m.model_type or "chat"
        await db.execute(
            _sa_update(LLMModel)
            .where(LLMModel.model_type == target_type, LLMModel.id != m.id)
            .values(is_default=False)
        )
    for k, v in data.items():
        setattr(m, k, v)
    if raw_key is not None:              # 空字串 '' 表示清除；非空則重新加密
        m.api_key = encrypt_secret(raw_key) if raw_key else None
    await db.commit()
    await db.refresh(m)
    return _to_out(m)


@router.delete("/models/{model_id}", status_code=200)
async def delete_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Model not found")
    await db.delete(m)
    await db.commit()
    return {"deleted": model_id}


@router.patch("/models/{model_id}/governance", response_model=LLMModelOut)
async def update_model_governance(
    model_id: str,
    body: LLMModelGovernanceIn,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    """局部更新治理欄位（enabled / is_default / monthly_quota_usd）。
    is_default=True 時，自動將同 model_type 的其他模型 is_default 清為 False（互斥）。"""
    m = (await db.execute(select(LLMModel).where(LLMModel.id == model_id))).scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Model not found")

    data = body.model_dump(exclude_unset=True)
    if "is_default" in data and data["is_default"] is True:
        from sqlalchemy import update as _sa_update
        await db.execute(
            _sa_update(LLMModel)
            .where(LLMModel.model_type == (m.model_type or "chat"), LLMModel.id != m.id)
            .values(is_default=False)
        )
    for k, v in data.items():
        setattr(m, k, v)
    await db.commit()
    await db.refresh(m)
    return _to_out(m)


@router.post("/models/verify")
async def verify_model(
    body: VerifyModelIn,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    """Test connection to a provider/model（依 first-principles-api-key §三：model-level key 優先，system_settings fallback）"""
    import httpx
    from sqlalchemy import text as _sql_text

    # 1. 解析 effective_key：
    #    優先級：body.api_key（前端輸入）→ llm_models.api_key（DB 已存）→ system_settings 同 provider fallback
    effective_key = body.api_key
    if not effective_key:
        # 1a. 透過 model_id 查 llm_models
        if body.model_id:
            m = (await db.execute(
                select(LLMModel).where(LLMModel.id == body.model_id)
            )).scalar_one_or_none()
            if m and getattr(m, "api_key", None):
                try:
                    effective_key = decrypt_secret(m.api_key)
                except Exception:
                    pass
        # 1b. 透過 model_name + provider 查 llm_models
        if not effective_key and body.model_name and body.provider and body.provider != "ollama":
            m = (await db.execute(
                select(LLMModel).where(
                    LLMModel.name == body.model_name,
                    LLMModel.provider == body.provider,
                ).limit(1)
            )).scalar_one_or_none()
            if m and getattr(m, "api_key", None):
                try:
                    effective_key = decrypt_secret(m.api_key)
                except Exception:
                    pass
        # 1c. system_settings fallback（同 provider 全域 key）
        if not effective_key and body.provider and body.provider != "ollama":
            try:
                row = (await db.execute(
                    _sql_text("SELECT value FROM system_settings WHERE key=:k"),
                    {"k": f"{body.provider}_api_key"},
                )).first()
                if row and row[0]:
                    effective_key = row[0].strip() or None
            except Exception:
                pass

    _TEST_URLS = {
        "openai":     "https://api.openai.com/v1/models",
        "groq":       "https://api.groq.com/openai/v1/models",
        "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai/models",
        "openrouter": "https://openrouter.ai/api/v1/models",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if body.provider == "ollama":
                url = (body.base_url or "http://ollama:11434").rstrip("/")
                r = await client.get(f"{url}/api/tags")
                if r.status_code != 200:
                    return {"ok": False, "message": f"Ollama 回傳 HTTP {r.status_code}"}
                available = [m["name"] for m in r.json().get("models", [])]
                if body.model_name and body.model_name not in available:
                    avail_str = ", ".join(available[:5]) or "（無）"
                    return {"ok": False, "message": f"模型 '{body.model_name}' 未找到\n可用: {avail_str}"}
                return {"ok": True, "message": f"✓ {body.model_name or 'Ollama'} 連線成功"}
            elif body.provider == "anthropic":
                if not effective_key:
                    return {"ok": False, "message": "需要 API Key"}
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": effective_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                if resp.status_code == 200:
                    return {"ok": True, "message": "✓ Anthropic 連線成功"}
                return {"ok": False, "message": f"Anthropic 驗證失敗：HTTP {resp.status_code}: {resp.text[:200]}"}
            elif body.provider in _TEST_URLS:
                if not effective_key:
                    return {"ok": False, "message": "需要 API Key"}
                headers = {"Authorization": f"Bearer {effective_key}"}
                if body.provider == "openrouter":
                    headers["HTTP-Referer"] = "http://localhost"
                r = await client.get(_TEST_URLS[body.provider], headers=headers)
                if r.status_code != 200:
                    detail = r.text[:200]
                    return {"ok": False, "message": f"HTTP {r.status_code}: {detail}"}
                return {"ok": True, "message": f"✓ {body.provider} API 連線成功"}
            else:
                return {"ok": False, "message": f"未知的 provider: {body.provider}"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@router.get("/models/compare/two")
async def compare_models(
    id_a: str = Query(..., description="蝚砌??芋??ID"),
    id_b: str = Query(..., description="蝚砌??芋??ID"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    """銝行?瘥??拙?LLM 璅∪?閬"""
    result = await db.execute(
        select(LLMModel).where(LLMModel.id.in_([id_a, id_b]))
    )
    items = {m.id: _to_out(m) for m in result.scalars().all()}
    if id_a not in items or id_b not in items:
        raise HTTPException(status_code=404, detail="One or both models not found")
    return {"model_a": items[id_a], "model_b": items[id_b]}


