"""
Prompt Engine Router — prompt_templates CRUD + 語意搜尋
"""
import logging
import re
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from qdrant_client.models import Distance, PointStruct, VectorParams
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser
from config import settings
from database import get_db, get_qdrant_client
from models import PromptTemplate

logger = logging.getLogger(__name__)
router = APIRouter()

PROMPT_COLLECTION = "prompt_templates"
VECTOR_DIM = 1024


# ── Schemas ──────────────────────────────────────────────────

class PromptTemplateIn(BaseModel):
    category: str
    title: str
    template: str
    required_vars: list[str] = []
    optional_vars: list[str] = []
    example_triggers: list[str] = []
    pit_warnings: list[str] = []


class PromptTemplateOut(BaseModel):
    template_id: str
    category: str
    title: str
    template: str
    required_vars: list
    optional_vars: list
    example_triggers: list
    pit_warnings: list
    usage_count: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class SearchResult(BaseModel):
    template_id: str
    category: str
    title: str
    template: str
    score: float


class MatchRequest(BaseModel):
    intent: str
    context: dict[str, str] = {}


class MatchResponse(BaseModel):
    matched_template_id: str
    category: str
    title: str
    confidence: float
    filled_prompt: str
    pit_warnings: list[str]
    missing_vars: list[str]


# ── 輔助：取得 embedding ──────────────────────────────────────

async def _embed(text: str) -> list[float]:
    """呼叫 Ollama bge-m3 取得 1024d 向量"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.OLLAMA_BASE_URL}/api/embed",
            json={"model": settings.OLLAMA_EMBED_MODEL, "input": [text]},
        )
        resp.raise_for_status()
        embeddings = resp.json().get("embeddings", [[]])
        if not embeddings or len(embeddings[0]) == 0:
            raise HTTPException(status_code=500, detail="Embedding 模型回傳空向量")
        return embeddings[0]


# ── 輔助：關鍵詞重疊分數 ─────────────────────────────────────────

def _keyword_overlap(intent: str, triggers: list[str]) -> float:
    """計算 intent 與 example_triggers 的最佳匹配分數 (0~1)

    策略（優先順序）：
    1. 任一 trigger 是 intent 的子串 → 直接回傳 1.0（完整命中）
    2. 否則用 bigram 重疊率（對中文短語更精準，避免單字雜訊）
    """
    if not triggers:
        return 0.0
    intent_lower = intent.lower()
    best = 0.0
    for trigger in triggers:
        if not trigger:
            continue
        t = trigger.lower().strip()
        if not t:
            continue
        # 1. 子串完整命中
        if t in intent_lower:
            return 1.0
        # 2. Bigram 重疊率（只對長度 >= 2 的 trigger 有效）
        if len(t) >= 2:
            t_bigrams = {t[i:i+2] for i in range(len(t) - 1)}
            i_bigrams = {intent_lower[i:i+2] for i in range(len(intent_lower) - 1)}
            if t_bigrams:
                score = len(t_bigrams & i_bigrams) / len(t_bigrams)
                best = max(best, score)
    return best


# ── 輔助：LLM 填充變數 ──────────────────────────────────────────

async def _llm_fill(template: str, context: dict[str, str], intent: str) -> str:
    """呼叫 Ollama LLM 將 context 填充進 template 中的 {var} 佔位符"""
    system_msg = (
        "你是 Prompt 填充助手。"
        "請依據Context將Template中的{var}佔位符填入對應的實際內容。"
        "不要修改模板結構，不要新增或刪除任何內容，只將{}中的占位符替換為實際文字。"
        "如果Context沒有提供某個變數，保留原佔位符不動。只回傳填充後的Prompt，不要加任何說明文字。"
    )
    user_msg = (
        f"Intent：{intent}\n\n"
        f"Context：{context}\n\n"
        f"Template：\n{template}"
    )
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": settings.OLLAMA_LLM_MODEL,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


# ── 輔助：確保 Qdrant collection 存在 ────────────────────────

async def _ensure_collection():
    client = get_qdrant_client()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    if PROMPT_COLLECTION not in names:
        await client.create_collection(
            collection_name=PROMPT_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        logger.info("已建立 Qdrant collection: %s", PROMPT_COLLECTION)


# ── 新增 ──────────────────────────────────────────────────────

@router.post("/", response_model=PromptTemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: PromptTemplateIn,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """新增一筆 Prompt 模板並寫入 Qdrant 向量索引"""
    await _ensure_collection()

    # 重複檢查：同 category + title 不可重複
    dup_stmt = select(PromptTemplate).where(
        PromptTemplate.category == body.category,
        PromptTemplate.title == body.title,
    )
    dup_result = await db.execute(dup_stmt)
    if dup_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="模板已存在")

    template_id = str(uuid.uuid4())
    record = PromptTemplate(
        template_id=template_id,
        **body.model_dump(),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    # 寫向量（title + example_triggers 合併嵌入，用於意圖匹配）
    try:
        embed_text = f"{body.title} {' '.join(body.example_triggers)}"
        vec = await _embed(embed_text)
        qdrant = get_qdrant_client()
        await qdrant.upsert(
            collection_name=PROMPT_COLLECTION,
            points=[
                PointStruct(
                    id=template_id,
                    vector=vec,
                    payload={
                        "category": body.category,
                        "title": body.title,
                    },
                )
            ],
        )
    except Exception:
        logger.exception("寫入 Qdrant 失敗，template_id=%s", template_id)

    return _to_out(record)


# ── 列表 ──────────────────────────────────────────────────────

@router.get("/", response_model=list[PromptTemplateOut])
async def list_templates(
    category: str | None = Query(None, description="依類別篩選"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """列出所有 Prompt 模板（可依類別篩選）"""
    stmt = select(PromptTemplate).order_by(PromptTemplate.category, PromptTemplate.title)
    if category:
        stmt = stmt.where(PromptTemplate.category == category)
    result = await db.execute(stmt)
    records = result.scalars().all()
    return [_to_out(r) for r in records]


# ── 意圖匹配（語意搜尋 + LLM 填充）───────────────────────────────

@router.post("/match", response_model=MatchResponse)
async def match_template(
    body: MatchRequest,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """接收使用者意圖 → 語意匹配最相關模板 → LLM 填充變數 → 回傳完整 prompt"""
    await _ensure_collection()

    # ── 第一道防線：全庫關鍵詞掃描 ──────────────────────────────
    # 從 DB 取所有模板，逐一計算 keyword_overlap
    # 若最高分 >= 0.5 → 直接採用，完全繞過向量搜尋
    all_stmt = select(PromptTemplate)
    all_result = await db.execute(all_stmt)
    all_templates = all_result.scalars().all()

    best_kw_score = 0.0
    best_kw_record: PromptTemplate | None = None
    for tpl in all_templates:
        kw = _keyword_overlap(body.intent, tpl.example_triggers or [])
        if kw > best_kw_score:
            best_kw_score = kw
            best_kw_record = tpl

    if best_kw_score >= 0.5 and best_kw_record is not None:
        # 強關鍵詞命中，直接取此模板
        record = best_kw_record
        combined_score = best_kw_score
        tid = str(record.template_id)
    else:
        # ── 第二道防線：向量搜尋 + 混合重排 ────────────────────────
        vec = await _embed(body.intent)
        qdrant = get_qdrant_client()
        result = await qdrant.query_points(
            collection_name=PROMPT_COLLECTION,
            query=vec,
            limit=5,
            with_payload=True,
        )
        if not result.points:
            raise HTTPException(status_code=404, detail="找不到相關模板，請先匯入種子資料")

        candidates: list[tuple[float, object, PromptTemplate]] = []
        for hit in result.points:
            hit_id = str(hit.id)
            rec = await db.get(PromptTemplate, hit_id)
            if rec:
                kw = _keyword_overlap(body.intent, rec.example_triggers or [])
                combined = hit.score * 0.4 + kw * 0.6
                candidates.append((combined, hit, rec))

        if not candidates:
            raise HTTPException(status_code=404, detail="找不到相關模板，請先匯入種子資料")

        candidates.sort(key=lambda x: x[0], reverse=True)
        combined_score, top_hit, record = candidates[0]
        tid = str(top_hit.id)

    # 4. 計算 missing_vars
    required = record.required_vars or []
    missing_vars = [v for v in required if v not in body.context]

    # 4. LLM 填充變數（失敗時降級為原始模板）
    try:
        filled_prompt = await _llm_fill(record.template, body.context, body.intent)
    except Exception:
        logger.exception("LLM 填充失敗，降級回傳原始模板，template_id=%s", tid)
        filled_prompt = record.template

    return MatchResponse(
        matched_template_id=tid,
        category=record.category,
        title=record.title,
        confidence=round(combined_score, 6),
        filled_prompt=filled_prompt,
        pit_warnings=record.pit_warnings or [],
        missing_vars=missing_vars,
    )


# ── 語意搜尋 ──────────────────────────────────────────────────

@router.post("/search", response_model=list[SearchResult])
async def search_templates(
    query: str = Query(..., description="自然語言搜尋詞"),
    top_k: int = Query(5, ge=1, le=20),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """以自然語言語意搜尋最相關的 Prompt 模板"""
    await _ensure_collection()
    vec = await _embed(query)
    qdrant = get_qdrant_client()
    result = await qdrant.query_points(
        collection_name=PROMPT_COLLECTION,
        query=vec,
        limit=top_k,
        with_payload=True,
    )
    results = []
    for hit in result.points:
        tid = str(hit.id)
        record = await db.get(PromptTemplate, tid)
        if record:
            results.append(
                SearchResult(
                    template_id=tid,
                    category=record.category,
                    title=record.title,
                    template=record.template,
                    score=hit.score,
                )
            )
    return results


# ── 取單筆 ─────────────────────────────────────────────────────

@router.get("/{template_id}", response_model=PromptTemplateOut)
async def get_template(
    template_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    record = await _get_or_404(template_id, db)
    return _to_out(record)


# ── 更新 ──────────────────────────────────────────────────────

@router.put("/{template_id}", response_model=PromptTemplateOut)
async def update_template(
    template_id: str,
    body: PromptTemplateIn,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    record = await _get_or_404(template_id, db)
    for field, value in body.model_dump().items():
        setattr(record, field, value)
    await db.commit()
    await db.refresh(record)

    # 更新向量（title + example_triggers 合併嵌入，用於意圖匹配）
    try:
        embed_text = f"{body.title} {' '.join(body.example_triggers)}"
        vec = await _embed(embed_text)
        qdrant = get_qdrant_client()
        await qdrant.upsert(
            collection_name=PROMPT_COLLECTION,
            points=[
                PointStruct(
                    id=template_id,
                    vector=vec,
                    payload={
                        "category": body.category,
                        "title": body.title,
                        "template": body.template,
                    },
                )
            ],
        )
    except Exception:
        logger.exception("更新 Qdrant 向量失敗，template_id=%s", template_id)

    return _to_out(record)


# ── 刪除 ──────────────────────────────────────────────────────

@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    record = await _get_or_404(template_id, db)
    await db.delete(record)
    await db.commit()

    try:
        qdrant = get_qdrant_client()
        await qdrant.delete(
            collection_name=PROMPT_COLLECTION,
            points_selector=[template_id],
        )
    except Exception:
        logger.exception("刪除 Qdrant 向量失敗，template_id=%s", template_id)


# ── 增加使用次數 ──────────────────────────────────────────────

@router.post("/{template_id}/use", response_model=PromptTemplateOut)
async def use_template(
    template_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """回傳模板內容並將 usage_count +1"""
    record = await _get_or_404(template_id, db)
    record.usage_count = (record.usage_count or 0) + 1
    await db.commit()
    await db.refresh(record)
    return _to_out(record)


# ── 私有輔助 ──────────────────────────────────────────────────

async def _get_or_404(template_id: str, db: AsyncSession) -> PromptTemplate:
    record = await db.get(PromptTemplate, template_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"找不到模板：{template_id}")
    return record


def _to_out(r: PromptTemplate) -> PromptTemplateOut:
    return PromptTemplateOut(
        template_id=r.template_id,
        category=r.category,
        title=r.title,
        template=r.template,
        required_vars=r.required_vars or [],
        optional_vars=r.optional_vars or [],
        example_triggers=r.example_triggers or [],
        pit_warnings=r.pit_warnings or [],
        usage_count=r.usage_count,
        created_at=r.created_at.isoformat(),
        updated_at=r.updated_at.isoformat(),
    )
