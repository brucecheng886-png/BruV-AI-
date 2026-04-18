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
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class VerifyModelIn(BaseModel):
    provider: str
    model_name: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None


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
    m = LLMModel(**body.model_dump())
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
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
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


@router.post("/models/verify")
async def verify_model(
    body: VerifyModelIn,
    current_user: CurrentUser = None,
):
    """Test connection to a provider/model (不需 DB)"""
    import httpx
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
            elif body.provider in _TEST_URLS:
                if not body.api_key:
                    return {"ok": False, "message": "需要 API Key"}
                r = await client.get(
                    _TEST_URLS[body.provider],
                    headers={"Authorization": f"Bearer {body.api_key}"}
                )
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


