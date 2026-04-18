"""
Chat Router — RAG 問答 + SSE 串流

端點：
  POST /api/chat/stream   — SSE 串流回答（query + conversation_id）
  GET  /api/chat/conversations      — 列出對話
  GET  /api/chat/conversations/{id} — 取得對話訊息
  DELETE /api/chat/conversations/{id}
"""
import json
import logging
import uuid
from typing import AsyncIterator, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser
from database import get_db, get_qdrant_client
from models import Conversation, Message
from services.reranker import get_reranker
from routers.settings_router import get_rag_runtime_config

logger = logging.getLogger(__name__)
router = APIRouter()

# 預設值（DB 無設定時使用）
QDRANT_SEARCH_TOP_K = 20
RERANK_TOP_K        = 5
MAX_CONTEXT_CHARS   = 4000


class ChatRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None
    model: Optional[str] = None            # 覆蓋預設 LLM


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: str

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    sources: list
    created_at: str


# ── SSE 產生器 ────────────────────────────────────────────────

async def _embed_query(query: str, settings) -> list[float]:
    """用 Ollama bge-m3 嵌入查詢"""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.OLLAMA_BASE_URL}/api/embed",
            json={"model": settings.OLLAMA_EMBED_MODEL, "input": [query]},
        )
        resp.raise_for_status()
        return resp.json().get("embeddings", [[]])[0]


async def _rag_stream(
    query: str,
    conv_id: str,
    model: str,
    settings,
    db: AsyncSession,
) -> AsyncIterator[str]:
    """核心 RAG pipeline：嵌入 → 搜索 → Rerank → 串流"""

    # 1. 嵌入查詢
    query_vec = await _embed_query(query, settings)

    # 讀取動態 RAG 設定
    rag_cfg = await get_rag_runtime_config(db)
    _top_k             = rag_cfg.get("top_k",             QDRANT_SEARCH_TOP_K)
    _rerank_top_k      = rag_cfg.get("rerank_top_k",      RERANK_TOP_K)
    _max_context_chars = rag_cfg.get("max_context_chars", MAX_CONTEXT_CHARS)
    _rerank_enabled    = rag_cfg.get("rerank_enabled",    True)

    # 2. Qdrant 向量搜索
    qdrant = get_qdrant_client()
    search_result_obj = await qdrant.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        query=query_vec,
        limit=_top_k,
        with_payload=True,
    )
    search_result = search_result_obj.points

    if not search_result:
        yield "data: " + json.dumps({"type": "error", "text": "知識庫中找不到相關資料。"}) + "\n\n"
        return

    # 3. BGE Re-ranker（可動態關閉）
    passages = [hit.payload.get("content", "") for hit in search_result]
    if _rerank_enabled:
        reranker = await get_reranker()
        top_idxs = reranker.rerank(query, passages, top_k=_rerank_top_k)
        top_hits = [search_result[i] for i in top_idxs]
    else:
        top_hits = search_result[:_rerank_top_k]

    # 4. 建構 context
    context_parts = []
    chars = 0
    sources = []
    for hit in top_hits:
        text = hit.payload.get("content", "")
        doc_id = hit.payload.get("doc_id", "")
        page   = hit.payload.get("page_number", "")
        title  = hit.payload.get("title", "")
        if chars + len(text) <= _max_context_chars:
            context_parts.append(f"[{title} p.{page}] {text}")
            chars += len(text)
            sources.append({"doc_id": doc_id, "title": title,
                            "page_number": page, "score": hit.score})

    context = "\n\n".join(context_parts)
    system_prompt = (
        "你是一個知識庫助理。請根據以下參考資料回答問題。"
        "若資料不足以回答，請如實說明。\n\n"
        f"參考資料：\n{context}"
    )

    # 5. 取先前對話紀錄（最多 10 輪）
    result = await db.execute(
        select(Message)
        .where(Message.conv_id == conv_id)
        .order_by(Message.created_at.desc())
        .limit(20)
    )
    history_msgs = list(reversed(result.scalars().all()))
    messages_payload = [{"role": "system", "content": system_prompt}]
    for m in history_msgs:
        messages_payload.append({"role": m.role, "content": m.content})
    messages_payload.append({"role": "user", "content": query})

    # 6. 儲存使用者訊息
    user_msg = Message(
        id=str(uuid.uuid4()),
        conv_id=conv_id,
        role="user",
        content=query,
        sources=[],
    )
    db.add(user_msg)
    await db.commit()

    # 7. 串流 LLM（統一適配層：Ollama / OpenAI / Groq / Gemini / OpenRouter）
    from llm_client import llm_stream
    from routers.settings_router import get_llm_runtime_config
    runtime_config = await get_llm_runtime_config(db)
    full_reply = ""
    try:
        async for token in llm_stream(
            messages_payload, settings,
            model_override=model,
            config_override=runtime_config,
        ):
            full_reply += token
            yield "data: " + json.dumps({"type": "token", "text": token}) + "\n\n"
    except httpx.HTTPStatusError as e:
        logger.error("LLM stream error: %s", e)
        yield "data: " + json.dumps({"type": "error", "text": "LLM 服務暫時無法使用"}) + "\n\n"
        return
    except Exception as e:
        logger.error("LLM unexpected error: %s", e)
        yield "data: " + json.dumps({"type": "error", "text": str(e)}) + "\n\n"
        return

    # 8. 儲存助理回覆
    assistant_msg = Message(
        id=str(uuid.uuid4()),
        conv_id=conv_id,
        role="assistant",
        content=full_reply,
        sources=sources,
    )
    db.add(assistant_msg)
    await db.commit()

    # 9. 傳送 sources 事件
    yield "data: " + json.dumps({"type": "sources", "sources": sources}) + "\n\n"
    yield "data: [DONE]\n\n"


# ── 端點 ──────────────────────────────────────────────────────

@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """RAG SSE 串流端點"""
    from config import settings

    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能為空")

    llm_model = req.model or settings.OLLAMA_LLM_MODEL

    # 確保 conversation 存在
    conv_id = req.conversation_id
    if conv_id:
        result = await db.execute(
            select(Conversation).where(Conversation.id == conv_id))
        conv = result.scalar_one_or_none()
        if conv is None:
            raise HTTPException(status_code=404, detail="對話不存在")
    else:
        conv_id = str(uuid.uuid4())
        first_words = req.query[:30] + ("…" if len(req.query) > 30 else "")
        new_conv = Conversation(
            id=conv_id,
            title=first_words,
            user_id=current_user.id if current_user else None,
        )
        db.add(new_conv)
        await db.commit()

    return StreamingResponse(
        _rag_stream(req.query, conv_id, llm_model, settings, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": conv_id,
        },
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    q = (select(Conversation)
         .order_by(Conversation.updated_at.desc())
         .limit(limit).offset(offset))
    if current_user:
        q = q.where(Conversation.user_id == current_user.id)
    result = await db.execute(q)
    convs = result.scalars().all()
    return [ConversationOut(
        id=c.id, title=c.title,
        created_at=c.created_at.isoformat()) for c in convs]


@router.get("/conversations/{conv_id}", response_model=list[MessageOut])
async def get_conversation_messages(
    conv_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conv_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="對話不存在")

    result = await db.execute(
        select(Message).where(Message.conv_id == conv_id)
        .order_by(Message.created_at))
    msgs = result.scalars().all()
    return [MessageOut(
        id=m.id, role=m.role, content=m.content,
        sources=m.sources or [],
        created_at=m.created_at.isoformat()) for m in msgs]


@router.delete("/conversations/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conv_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conv_id))
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="對話不存在")
    await db.delete(conv)
    await db.commit()

