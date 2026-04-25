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
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
from auth import CurrentUser
from database import get_db, get_qdrant_client
from models import Conversation, Message
from services.reranker import get_reranker
from routers.settings_router import get_rag_runtime_config, get_kb_schema, get_chat_runtime_config

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
    doc_ids: Optional[list[str]] = None    # @mention 文件（單則訊息層級）
    kb_scope_id: Optional[str] = None      # 對話層級 KB scope（新對話時傳入）
    doc_scope_ids: Optional[list[str]] = None  # 對話層級 文件 scope（新對話時傳入）
    tag_scope_ids: Optional[list[str]] = []   # 對話層級 tag filter（與上方範圍同時生效）
    agent_type: Optional[str] = "chat"    # chat / page_agent:xxx / kb_agent
    mode: Optional[str] = "agent"          # agent / ask / plan


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: str
    kb_scope_id: Optional[str] = None
    doc_scope_ids: list = []
    tag_scope_ids: list = []
    agent_type: Optional[str] = "chat"
    agent_meta: Optional[dict] = {}
    summary: Optional[str] = None

    class Config:
        from_attributes = True


class ConversationRenameIn(BaseModel):
    title: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    sources: list
    created_at: str


# ── SSE 產生器 ────────────────────────────────────────────────

async def _embed_query(query: str, settings, model: str | None = None, provider: str | None = None,
                      base_url: str | None = None, api_key: str | None = None) -> list[float]:
    """查詢嵌入：預設走 Ollama bge-m3；可依 KB 設定覆寫為雲端 provider。"""
    if model and provider and provider != "ollama":
        url = (base_url or "https://api.openai.com").rstrip("/")
        if not url.endswith("/v1"):
            url = f"{url}/v1"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{url}/embeddings",
                headers={"Authorization": f"Bearer {api_key or ''}", "Content-Type": "application/json"},
                json={"model": model, "input": query},
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return data[0].get("embedding", []) if data else []
    use_model = model if (model and (not provider or provider == "ollama")) else settings.OLLAMA_EMBED_MODEL
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.OLLAMA_BASE_URL}/api/embed",
            json={"model": use_model, "input": [query]},
        )
        resp.raise_for_status()
        return resp.json().get("embeddings", [[]])[0]


# ── 對話摘要常數 ──────────────────────────────────────────────────
RECENT_ROUNDS       = 6   # 保留最近幾輪完整對話
SUMMARIZE_THRESHOLD = 20  # 超過幾筆訊息時觸發摘要


async def _summarize_history(
    conv_id: str,
    messages: list,
    settings,
    db: AsyncSession,
) -> str:
    """用 LLM 把舊的對話歷史壓縮成摘要並存回 DB"""
    if not messages:
        return ""

    history_text = "\n".join([
        f"{m.role}: {m.content[:500]}"
        for m in messages
    ])

    prompt = (
        "請將以下對話歷史摘要成一段簡潔的文字（200字以內），"
        "保留重要的決策、操作結果和關鍵資訊：\n\n"
        f"{history_text}\n\n摘要："
    )

    summary = ""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_CHAT_MODEL,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            summary = resp.json().get("response", "").strip()
    except Exception as e:
        logger.warning("摘要生成失敗，略過：%s", e)
        return ""

    if summary:
        last_msg_id = messages[-1].id
        await db.execute(
            sa_update(Conversation)
            .where(Conversation.id == conv_id)
            .values(
                summary=summary,
                summarized_up_to=last_msg_id,
                summary_updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    return summary


# page_agent 對應的角色說明
_PAGE_AGENT_PROMPTS: dict[str, str] = {
    "docs": """你是文件管理頁面的 AI 助理。

## 可執行操作
當使用者要求執行操作時，在回應末尾加上 __action__:{...}（單行 JSON）：

建立知識庫：
__action__:{"type":"create_kb","name":"KB名稱","description":"描述"}

刪除文件：
__action__:{"type":"delete_doc","doc_id":"uuid"}

搜尋文件（查詢狀態、標題、內容）：
__action__:{"type":"search_docs","query":"關鍵字","top_k":20}

列出所有知識庫（建議分類前先知道現有 KB）：
__action__:{"type":"list_kbs"}

列出所有文件（取得 doc_id 和 kb_id，執行 move_to_kb / edit_doc 前必須先呼叫）：
__action__:{"type":"list_all_docs"}

將文件移入知識庫（單一文件）：
__action__:{"type":"move_to_kb","doc_id":"uuid","kb_id":"uuid"}

批次將多篇文件移入同一知識庫：
__action__:{"type":"batch_move_to_kb","doc_ids":["uuid1","uuid2"],"kb_id":"uuid"}

編輯文件 metadata（標題、描述）：
__action__:{"type":"edit_doc","doc_id":"uuid","title":"新標題","description":"描述"}

## 限制
- 只能操作文件管理頁面的功能
- 不能執行其他頁面的操作
- 刪除操作前必須先確認使用者意圖
- **執行 edit_doc 前，必須先告知使用者：「我將要修改文件《{title}》的{欄位}，從「{舊值}」改為「{新值}」，請確認是否執行？」，收到確認（確認/好/是/ok）後才輸出 __action__**
- **執行 batch_move_to_kb 或任何影響多個文件的操作前，必須先列出計畫（哪些文件移入哪個 KB）並請使用者回覆「確認」或「好」後才輸出 __action__**

## 回應格式
- 使用繁體中文
- 回應簡潔，不超過 200 字
- 執行操作前先說明要做什麼
- 操作完成後必須回報結果摘要（成功幾個、失敗幾個）""",

    "chat": """你是對話管理頁面的 AI 助理。

## 可執行操作
刪除對話：
__action__:{"type":"delete_conv","conv_id":"uuid"}

搜尋對話：
__action__:{"type":"search_convs","query":"關鍵字"}

## 限制
- 只能操作對話管理頁面的功能
- 刪除操作前必須先確認使用者意圖

## 回應格式
- 使用繁體中文
- 回應簡潔，不超過 200 字""",

    "ontology": """你是知識圖譜頁面的 AI 助理。

## 可執行操作
批次核准所有待審核實體：
__action__:{"type":"batch_approve_all"}

批次拒絕所有待審核實體：
__action__:{"type":"batch_reject_all"}

## 限制
- 只能操作知識圖譜頁面的功能
- 批次操作前必須明確確認使用者意圖
- 批次拒絕會將實體加入封鎖清單，請謹慎執行

## 回應格式
- 使用繁體中文
- 回應簡潔，不超過 200 字
- 執行批次操作前先說明影響範圍""",

    "plugins": """你是插件管理頁面的 AI 助理。

## 可執行操作
啟用或停用插件：
__action__:{"type":"toggle_plugin","plugin_id":"uuid","enabled":true}

## 限制
- 只能操作插件管理頁面的功能
- 修改插件狀態前先說明影響

## 回應格式
- 使用繁體中文
- 回應簡潔，不超過 200 字""",

    "settings": """你是系統設定頁面的 AI 助理。

## 可執行操作
新增模型：
__action__:{"type":"add_model","name":"模型名稱","provider":"ollama"}

## 限制
- 只能操作系統設定頁面的功能
- 修改系統設定前必須說明影響
- 不能刪除現有模型

## 回應格式
- 使用繁體中文
- 回應簡潔，不超過 200 字
- 涉及技術參數時附上說明""",

    "protein": """你是蛋白質圖譜頁面的 AI 助理。

## 功能範圍
- 解釋蛋白質相互作用圖譜的節點和邊
- 查詢特定蛋白質的相關資訊
- 協助分析蛋白質關係網絡

## 限制
- 只能回答蛋白質圖譜相關問題
- 不執行操作，純問答模式

## 回應格式
- 使用繁體中文，專業術語附英文原文
- 回應簡潔，不超過 300 字""",

    "kb": """你是知識庫管理 AI 助理。

## 可執行操作
當使用者要求執行操作時，在回應末尾加上 __action__:{...}（單行 JSON）：

搜尋相關文件：
__action__:{"type":"search_docs","query":"關鍵字","top_k":20}

列出所有知識庫（建議分類前先知道現有 KB）：
__action__:{"type":"list_kbs"}

列出所有文件（取得 doc_id 和 kb_id，執行移動操作前必須先呼叫）：
__action__:{"type":"list_all_docs"}

將文件移入知識庫（單一文件）：
__action__:{"type":"move_to_kb","doc_id":"uuid","kb_id":"uuid"}

批次將多篇文件移入同一知識庫：
__action__:{"type":"batch_move_to_kb","doc_ids":["uuid1","uuid2"],"kb_id":"uuid"}

建立知識庫：
__action__:{"type":"create_kb","name":"KB名稱","description":"描述"}

## 重要規則
- **執行 move_to_kb 或 batch_move_to_kb 前，必須先呼叫 list_all_docs 取得正確的 doc_id 和 kb_id，不得猜測 ID**
- **執行 batch_move_to_kb 或任何影響多個文件的操作前，必須先列出計畫（哪些文件移入哪個 KB）並請使用者回覆「確認」或「好」後才輸出 __action__**
- 建立知識庫前先確認名稱和描述

## 回應格式
- 使用繁體中文
- 回應簡潔，不超過 200 字
- 執行操作前先說明要做什麼
- 操作完成後必須回報結果摘要（成功幾個、失敗幾個）""",
}


async def _rag_stream(
    query: str,
    conv_id: str,
    model: str,
    settings,
    db: AsyncSession,
    message_doc_ids: list[str] | None = None,
    conv_doc_scope_ids: list[str] | None = None,
    conv_kb_scope_id: str | None = None,
    conv_tag_scope_ids: list[str] | None = None,
    conv_title: str = "",
    agent_type: str = "chat",
    file_context: str | None = None,
    mode: str = "agent",
) -> AsyncIterator[str]:
    """核心 RAG pipeline：嵌入 → 搜索 → Rerank → 串流

    Scope 優先級：message_doc_ids > conv_doc_scope_ids > conv_kb_scope_id > 全域
    tag_scope_ids 為正交附加條件，與上方任一 scope 同時生效
    """

    # 1. 讀取 KB 級設定（若有 conv_kb_scope_id）
    kb_embedding_model: str | None = None
    kb_embedding_provider: str | None = None
    kb_embedding_base_url: str | None = None
    kb_embedding_api_key: str | None = None
    kb_default_top_k: int | None = None
    kb_rerank_enabled: bool | None = None
    if conv_kb_scope_id:
        from sqlalchemy import text as _text
        kb_row = await db.execute(
            _text(
                "SELECT embedding_model, embedding_provider, default_top_k, rerank_enabled "
                "FROM knowledge_bases WHERE id=:kid"
            ),
            {"kid": conv_kb_scope_id},
        )
        r = kb_row.fetchone()
        if r:
            kb_embedding_model    = r[0]
            kb_embedding_provider = r[1]
            kb_default_top_k      = r[2]
            kb_rerank_enabled     = r[3]
        if kb_embedding_model and kb_embedding_provider and kb_embedding_provider != "ollama":
            mdl_row = await db.execute(
                _text(
                    "SELECT base_url, api_key FROM llm_models "
                    "WHERE name=:n AND provider=:p LIMIT 1"
                ),
                {"n": kb_embedding_model, "p": kb_embedding_provider},
            )
            mr = mdl_row.fetchone()
            if mr:
                kb_embedding_base_url = mr[0]
                if mr[1]:
                    try:
                        from utils.crypto import decrypt_secret
                        kb_embedding_api_key = decrypt_secret(mr[1])
                    except Exception:
                        kb_embedding_api_key = None

    # 1. 嵌入查詢（依 KB 設定路由）
    query_vec = await _embed_query(
        query, settings,
        model=kb_embedding_model, provider=kb_embedding_provider,
        base_url=kb_embedding_base_url, api_key=kb_embedding_api_key,
    )

    # 讀取動態 RAG 設定 & 對話行為設定
    rag_cfg  = await get_rag_runtime_config(db)
    chat_cfg = await get_chat_runtime_config(db)
    _top_k             = rag_cfg.get("top_k",             QDRANT_SEARCH_TOP_K)
    _rerank_top_k      = rag_cfg.get("rerank_top_k",      RERANK_TOP_K)
    _max_context_chars = rag_cfg.get("max_context_chars", MAX_CONTEXT_CHARS)
    _rerank_enabled    = rag_cfg.get("rerank_enabled",    True)
    # KB 級覆寫
    if kb_default_top_k is not None:
        _top_k = kb_default_top_k
    if kb_rerank_enabled is not None:
        _rerank_enabled = kb_rerank_enabled
    _history_rounds    = chat_cfg.get("history_rounds",   10)
    _temperature       = chat_cfg.get("temperature",      0.7)
    _max_tokens        = chat_cfg.get("max_tokens",       2048)
    _extra_system      = chat_cfg.get("system_prompt",    "")

    # 2. 若有 tag_scope_ids，先從 PG 查出符合的 doc_ids
    tag_doc_ids: list[str] | None = None
    if conv_tag_scope_ids:
        from sqlalchemy import text as _text
        tag_rows = await db.execute(
            _text(
                "SELECT DISTINCT doc_id::text FROM document_tags "
                "WHERE tag_id = ANY(:tag_ids)"
            ),
            {"tag_ids": conv_tag_scope_ids},
        )
        tag_doc_ids = [r[0] for r in tag_rows.fetchall()]
        if not tag_doc_ids:
            # tag filter 有值但無文件符合 → 提早結束
            yield "data: " + json.dumps({"type": "error", "text": "沒有符合指定標籤的文件。"}) + "\n\n"
            yield "data: [DONE]\n\n"
            return

    # 3. 建構 Qdrant filter（優先級：message_doc_ids > conv_doc_scope_ids > kb_scope_id > 全域）
    qdrant_filter: Filter | None = None
    _effective_doc_ids = message_doc_ids or conv_doc_scope_ids or None

    if _effective_doc_ids and tag_doc_ids is not None:
        # doc scope + tag filter → 取交集
        intersection = list(set(_effective_doc_ids) & set(tag_doc_ids))
        if not intersection:
            yield "data: " + json.dumps({"type": "error", "text": "指定文件與標籤篩選無交集。"}) + "\n\n"
            yield "data: [DONE]\n\n"
            return
        qdrant_filter = Filter(
            must=[FieldCondition(key="doc_id", match=MatchAny(any=intersection))]
        )
    elif _effective_doc_ids:
        qdrant_filter = Filter(
            must=[FieldCondition(key="doc_id", match=MatchAny(any=_effective_doc_ids))]
        )
    elif conv_kb_scope_id and tag_doc_ids is not None:
        # kb scope + tag filter → kb AND doc_id IN tag_doc_ids
        qdrant_filter = Filter(
            must=[
                FieldCondition(key="kb_id", match=MatchValue(value=conv_kb_scope_id)),
                FieldCondition(key="doc_id", match=MatchAny(any=tag_doc_ids)),
            ]
        )
    elif conv_kb_scope_id:
        qdrant_filter = Filter(
            must=[FieldCondition(key="kb_id", match=MatchValue(value=conv_kb_scope_id))]
        )
    elif tag_doc_ids is not None:
        # 全域 + tag filter
        qdrant_filter = Filter(
            must=[FieldCondition(key="doc_id", match=MatchAny(any=tag_doc_ids))]
        )

    # 3. Qdrant 向量搜索
    qdrant = get_qdrant_client()
    search_result_obj = await qdrant.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        query=query_vec,
        limit=_top_k,
        with_payload=True,
        query_filter=qdrant_filter,
    )
    search_result = search_result_obj.points

    if not search_result:
        if file_context:
            # 純附件問題，無需 RAG 知識庫結果，由 file_context 驅動 LLM
            pass
        else:
            yield "data: " + json.dumps({"type": "error", "text": "知識庫中找不到相關資料。"}) + "\n\n"
            yield "data: [DONE]\n\n"
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
    # 讀取知識庫 Schema（優點3：架構注入）
    kb_schema = await get_kb_schema(db)
    schema_section = f"\n\n知識庫架構說明：\n{kb_schema}" if kb_schema.strip() else ""
    extra_section = f"\n\n{_extra_system}" if _extra_system and _extra_system.strip() else ""
    file_context_section = f"\n\n{file_context}" if file_context and file_context.strip() else ""
    # 根據 agent_type 注入角色前置說明
    _agent_prefix = ""
    _page_for_skill: str | None = None
    if agent_type and agent_type.startswith("page_agent:"):
        _page = agent_type.split(":", 1)[1]
        _role = _PAGE_AGENT_PROMPTS.get(_page, "你是頁面助理。")
        _agent_prefix = _role + "\n\n"
        _page_for_skill = _page
    elif agent_type == "kb_agent":
        _agent_prefix = _PAGE_AGENT_PROMPTS.get("kb", "你是知識庫助理。") + "\n\n"
        _page_for_skill = "kb"

    if _page_for_skill:
        # 從 DB 讀取使用者自訂 prompt
        try:
            _skill_row = (await db.execute(
                __import__("sqlalchemy").text(
                    "SELECT user_prompt, is_enabled FROM agent_skills WHERE page_key = :pk"
                ),
                {"pk": _page_for_skill},
            )).fetchone()
            if _skill_row and _skill_row.is_enabled and _skill_row.user_prompt:
                _agent_prefix += f"使用者自訂指令：\n{_skill_row.user_prompt}\n\n"
        except Exception:
            pass  # DB 無此表或查詢失敗時靜默忽略

    # 根據 mode 附加操作行為說明
    _mode_suffix = ""
    if mode == "ask":
        _mode_suffix = "\n\n【模式：純問答】只回答使用者的問題，不執行任何操作，不輸出 __action__ 標記。"
    elif mode == "plan":
        _mode_suffix = (
            "\n\n【模式：規劃後確認】先列出執行計劃（用編號步驟說明），"
            "詢問使用者是否確認（例如：「請回覆『確認』以執行」），"
            "待使用者明確回覆確認後才輸出 __action__ 標記執行操作。"
        )

    system_prompt = (
        _agent_prefix
        + "你是一個知識庫助理。請根據以下參考資料回答問題。"
        "若資料不足以回答，請如實說明。"
        f"{schema_section}"
        f"{extra_section}"
        f"{_mode_suffix}"
        f"{file_context_section}\n\n"
        f"參考資料：\n{context}"
    )

    # 5. 取先前對話紀錄（摘要 + 近期完整輪次）
    # 5a. 取總訊息數
    total_count_res = await db.execute(
        select(func.count(Message.id)).where(Message.conv_id == conv_id)
    )
    total_msg_count = total_count_res.scalar() or 0

    # 5b. 取對話現有摘要
    conv_row = await db.execute(
        select(Conversation.summary, Conversation.summarized_up_to)
        .where(Conversation.id == conv_id)
    )
    conv_info = conv_row.first()
    existing_summary = conv_info.summary if conv_info else None

    # 5c. 取最近 RECENT_ROUNDS * 2 筆完整對話
    recent_result = await db.execute(
        select(Message)
        .where(Message.conv_id == conv_id)
        .order_by(Message.created_at.desc())
        .limit(RECENT_ROUNDS * 2)
    )
    recent_msgs = list(reversed(recent_result.scalars().all()))

    # 5d. 超過門檻且尚無摘要時，對更舊的訊息做摘要
    if total_msg_count > SUMMARIZE_THRESHOLD and not existing_summary:
        old_limit = total_msg_count - RECENT_ROUNDS * 2
        if old_limit > 0:
            old_result = await db.execute(
                select(Message)
                .where(Message.conv_id == conv_id)
                .order_by(Message.created_at.asc())
                .limit(old_limit)
            )
            old_msgs = old_result.scalars().all()
            if old_msgs:
                existing_summary = await _summarize_history(
                    conv_id, list(old_msgs), settings, db
                )

    # 5e. 組裝 messages_payload
    messages_payload = [{"role": "system", "content": system_prompt}]
    if existing_summary:
        messages_payload.append({
            "role": "assistant",
            "content": f"以下是先前對話的摘要：\n{existing_summary}",
        })
    for m in recent_msgs:
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

    # 7. 串流 LLM（統一適配層：Ollama / OpenAI / Groq / Gemini / OpenRouter / Anthropic）
    from llm_client import llm_stream
    from routers.settings_router import get_llm_runtime_config
    runtime_config = await get_llm_runtime_config(db)

    # 根據模型名稱自動判斷 provider，覆寫 runtime_config 中的 provider
    if model:
        _m = model.lower()
        if "claude" in _m:
            runtime_config = {**runtime_config, "provider": "anthropic"}
        elif "gpt" in _m or _m.startswith("o1") or _m.startswith("o3"):
            runtime_config = {**runtime_config, "provider": "openai"}
        elif "gemini" in _m:
            runtime_config = {**runtime_config, "provider": "gemini"}

        # 從 llm_models 查詢 model-level api_key（優先於 system_settings fallback）
        _detected_provider = runtime_config.get("provider")
        if _detected_provider and _detected_provider != "ollama":
            from sqlalchemy import text as _sql_text
            from utils.crypto import decrypt_secret as _decrypt
            _mdl_row = await db.execute(
                _sql_text("SELECT api_key FROM llm_models WHERE name=:n AND provider=:p LIMIT 1"),
                {"n": model, "p": _detected_provider},
            )
            _mr = _mdl_row.fetchone()
            if _mr and _mr[0]:
                try:
                    runtime_config = {**runtime_config, "api_key": _decrypt(_mr[0])}
                except Exception:
                    pass

    full_reply = ""
    try:
        async for token in llm_stream(
            messages_payload, settings,
            model_override=model,
            config_override=runtime_config,
            temperature=_temperature,
            max_tokens=_max_tokens,
        ):
            full_reply += token
            yield "data: " + json.dumps({"type": "token", "text": token}) + "\n\n"
    except httpx.HTTPStatusError as e:
        logger.error("LLM stream error: %s", e)
        err_text = "LLM 服務暫時無法使用"
        db.add(Message(
            id=str(uuid.uuid4()), conv_id=conv_id, role="assistant",
            content=err_text, sources=[],
        ))
        await db.commit()
        yield "data: " + json.dumps({"type": "error", "text": err_text}) + "\n\n"
        yield "data: [DONE]\n\n"
        return
    except Exception as e:
        logger.error("LLM unexpected error: %s", e)
        err_text = f"發生錯誤：{e}"
        db.add(Message(
            id=str(uuid.uuid4()), conv_id=conv_id, role="assistant",
            content=err_text, sources=[],
        ))
        await db.commit()
        yield "data: " + json.dumps({"type": "error", "text": str(e)}) + "\n\n"
        yield "data: [DONE]\n\n"
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

    # 10. 自動命名（conv_title == "新對話" 時觸發）
    if conv_title == "新對話":
        try:
            title_messages = [
                {"role": "user", "content": (
                    f"根據以下對話的第一則使用者訊息，用繁體中文生成一個 8 到 15 字的對話標題。"
                    f"只回傳標題文字，不要加引號、符號或任何說明。\n\n使用者訊息：{query}"
                )}
            ]
            new_title = ""
            async for token in llm_stream(
                title_messages, settings,
                model_override=model,
                config_override=runtime_config,
                temperature=0.3,
                max_tokens=30,
            ):
                new_title += token
            new_title = new_title.strip().strip('"\'「\u300d『\u300f').strip()[:100]
            if new_title:
                await db.execute(
                    sa_update(Conversation)
                    .where(Conversation.id == conv_id)
                    .values(title=new_title)
                )
                await db.commit()
                yield "data: " + json.dumps({"type": "title", "title": new_title}, ensure_ascii=False) + "\n\n"
        except Exception as _e:
            logger.warning("Auto-rename failed: %s", _e)

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

    # 若使用者未指定 model，傳 None → llm_stream 會從 DB runtime_config 或 env 自動解析
    # 不可用 settings.OLLAMA_LLM_MODEL 作 fallback，否則會將 Ollama 模型名傳給 OpenAI
    llm_model = req.model or None

    # 確保 conversation 存在
    conv_id = req.conversation_id
    if conv_id:
        result = await db.execute(
            select(Conversation).where(Conversation.id == conv_id))
        conv = result.scalar_one_or_none()
        if conv is None:
            raise HTTPException(status_code=404, detail="對話不存在")
        conv_kb_scope_id   = conv.kb_scope_id
        conv_doc_scope_ids = conv.doc_scope_ids or []
        conv_tag_scope_ids = conv.tag_scope_ids or []
    else:
        conv_id = str(uuid.uuid4())
        first_words = req.query[:30] + ("…" if len(req.query) > 30 else "")
        new_conv = Conversation(
            id=conv_id,
            title=first_words,
            user_id=current_user.id if current_user else None,
            kb_scope_id=req.kb_scope_id or None,
            doc_scope_ids=req.doc_scope_ids or [],
            tag_scope_ids=req.tag_scope_ids or [],
            agent_type=req.agent_type or "chat",
        )
        db.add(new_conv)
        await db.commit()
        conv_kb_scope_id   = req.kb_scope_id or None
        conv_doc_scope_ids = req.doc_scope_ids or []
        conv_tag_scope_ids = req.tag_scope_ids or []

    # 取得 conv_title 供自動命名判斷
    if req.conversation_id:
        _conv_title = conv.title  # conv 在上方 if conv_id: 分支中已定義
    else:
        _conv_title = first_words  # 非「新對話」，不觸發命名

    # 已存在對話時，從 conv 物件取出 agent_type
    _agent_type = req.agent_type or "chat"
    if req.conversation_id and conv is not None:
        _agent_type = conv.agent_type or "chat"

    return StreamingResponse(
        _rag_stream(
            req.query, conv_id, llm_model, settings, db,
            message_doc_ids=req.doc_ids or None,
            conv_doc_scope_ids=conv_doc_scope_ids or None,
            conv_kb_scope_id=conv_kb_scope_id,
            conv_tag_scope_ids=conv_tag_scope_ids or None,
            conv_title=_conv_title,
            agent_type=_agent_type,
            mode=req.mode or "agent",
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": conv_id,
        },
    )


# ── 附件串流端點 ───────────────────────────────────────────────

_EXCEL_EXTENSIONS = {".xlsx", ".xls", ".csv"}
_DOC_EXTENSIONS   = {".pdf", ".docx", ".txt", ".md"}

@router.post("/stream-with-file")
async def chat_stream_with_file(
    query: str = Form(""),
    conversation_id: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    agent_type: Optional[str] = Form("chat"),
    mode: Optional[str] = Form("agent"),
    doc_ids: Optional[str] = Form(None),       # JSON 字串
    kb_scope_id: Optional[str] = Form(None),
    doc_scope_ids: Optional[str] = Form(None), # JSON 字串
    tag_scope_ids: Optional[str] = Form(None), # JSON 字串
    file: Optional[UploadFile] = File(None),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """帶附件的 RAG SSE 串流端點（不影響現有 /stream）"""
    import json as _json
    import os
    from config import settings

    # 解析 JSON 字串欄位
    def _parse_list(s: Optional[str]) -> list:
        if not s:
            return []
        try:
            return _json.loads(s)
        except Exception:
            return []

    _doc_ids      = _parse_list(doc_ids)
    _doc_scope_ids = _parse_list(doc_scope_ids)
    _tag_scope_ids = _parse_list(tag_scope_ids)

    # 分析附件，建立 file_context
    file_context: Optional[str] = None
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        fname = file.filename
        if ext in _EXCEL_EXTENSIONS:
            file_context = (
                f"【使用者上傳了一份 Excel/CSV 檔案：{fname}】\n"
                "請先詢問使用者的意圖：是要匯入連結清單、進行資料分析、還是其他用途？"
                "不要直接執行任何操作，等待使用者確認。\n"
                "若使用者明確說要「匯入」或「匯入連結」，請在回應中加入以下 JSON 標記（獨立一行）：\n"
                '{"__action__": "import_excel"}'
            )
        elif ext in _DOC_EXTENSIONS:
            file_context = (
                f"【使用者上傳了一份文件：{fname}】\n"
                "請先詢問使用者：是要將此文件加入知識庫，還是只想讓你閱讀並回答問題？"
                "不要直接執行任何操作，等待使用者確認。"
            )
        else:
            file_context = f"【使用者上傳了一個檔案：{fname}，格式暫不支援自動處理】"

    llm_model = model or None

    # 確保 conversation 存在
    conv_id = conversation_id
    if conv_id:
        result = await db.execute(
            select(Conversation).where(Conversation.id == conv_id))
        conv = result.scalar_one_or_none()
        if conv is None:
            raise HTTPException(status_code=404, detail="對話不存在")
        conv_kb_scope_id   = conv.kb_scope_id
        conv_doc_scope_ids = conv.doc_scope_ids or []
        conv_tag_scope_ids = conv.tag_scope_ids or []
        _conv_title = conv.title
    else:
        conv_id = str(uuid.uuid4())
        _title_src = query.strip() or (file.filename if file and file.filename else "附件對話")
        first_words = _title_src[:30] + ("…" if len(_title_src) > 30 else "")
        new_conv = Conversation(
            id=conv_id,
            title=first_words,
            user_id=current_user.id if current_user else None,
            kb_scope_id=kb_scope_id or None,
            doc_scope_ids=_doc_scope_ids,
            tag_scope_ids=_tag_scope_ids,
            agent_type=agent_type or "chat",
        )
        db.add(new_conv)
        await db.commit()
        conv_kb_scope_id   = kb_scope_id or None
        conv_doc_scope_ids = _doc_scope_ids
        conv_tag_scope_ids = _tag_scope_ids
        _conv_title = first_words

    _agent_type = agent_type or "chat"
    # 空 query 時以檔名作為 embedding 依據，讓 RAG 仍可運作
    _effective_query = query.strip() or (
        f"請分析這份附件：{file.filename}" if file and file.filename else "你好"
    )

    async def _stream_wrapper():
        async for chunk in _rag_stream(
            _effective_query, conv_id, llm_model, settings, db,
            message_doc_ids=_doc_ids or None,
            conv_doc_scope_ids=conv_doc_scope_ids or None,
            conv_kb_scope_id=conv_kb_scope_id,
            conv_tag_scope_ids=conv_tag_scope_ids or None,
            conv_title=_conv_title,
            agent_type=_agent_type,
            file_context=file_context,
            mode=mode or "agent",
        ):
            # 檢查 __action__ 標記，轉換為 SSE action 事件
            if '__action__": "import_excel"' in chunk:
                # 把這段替換為 action 事件
                yield "data: " + _json.dumps({"type": "action", "action": "import_excel", "filename": file.filename if file else ""}) + "\n\n"
            else:
                yield chunk

    return StreamingResponse(
        _stream_wrapper(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": conv_id,
        },
    )


class ConversationCreateIn(BaseModel):
    kb_scope_id: Optional[str] = None
    doc_scope_ids: Optional[list[str]] = []
    tag_scope_ids: Optional[list[str]] = []
    agent_type: Optional[str] = "chat"
    agent_meta: Optional[dict] = {}


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreateIn,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """建立空對話（選擇範圍後立即建立，不需要第一則訊息）"""
    conv_id = str(uuid.uuid4())
    new_conv = Conversation(
        id=conv_id,
        title="新對話",
        user_id=current_user.id if current_user else None,
        kb_scope_id=body.kb_scope_id or None,
        doc_scope_ids=body.doc_scope_ids or [],
        tag_scope_ids=body.tag_scope_ids or [],
        agent_type=body.agent_type or "chat",
        agent_meta=body.agent_meta or {},
    )
    db.add(new_conv)
    await db.commit()
    await db.refresh(new_conv)
    return ConversationOut(
        id=new_conv.id,
        title=new_conv.title,
        created_at=new_conv.created_at.isoformat(),
        kb_scope_id=new_conv.kb_scope_id,
        doc_scope_ids=new_conv.doc_scope_ids or [],
        tag_scope_ids=new_conv.tag_scope_ids or [],
        agent_type=new_conv.agent_type or "chat",
        agent_meta=new_conv.agent_meta or {},
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    agent_type: Optional[str] = Query(default=None),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    q = (select(Conversation)
         .order_by(Conversation.updated_at.desc())
         .limit(limit).offset(offset))
    if current_user:
        q = q.where(Conversation.user_id == current_user.id)
    if agent_type:
        q = q.where(Conversation.agent_type == agent_type)
    result = await db.execute(q)
    convs = result.scalars().all()
    return [ConversationOut(
        id=c.id, title=c.title,
        created_at=c.created_at.isoformat(),
        kb_scope_id=c.kb_scope_id,
        doc_scope_ids=c.doc_scope_ids or [],
        tag_scope_ids=c.tag_scope_ids or [],
        agent_type=c.agent_type or "chat",
        agent_meta=c.agent_meta or {},
    ) for c in convs]


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


@router.patch("/conversations/{conv_id}", response_model=ConversationOut)
async def rename_conversation(
    conv_id: str,
    body: ConversationRenameIn,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conv_id))
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="對話不存在")
    conv.title = body.title[:100]
    await db.commit()
    await db.refresh(conv)
    return ConversationOut(
        id=conv.id, title=conv.title,
        created_at=conv.created_at.isoformat(),
        kb_scope_id=conv.kb_scope_id,
        doc_scope_ids=conv.doc_scope_ids or [],
        tag_scope_ids=conv.tag_scope_ids or [],
        agent_type=conv.agent_type or "chat",
        agent_meta=conv.agent_meta or {},
    )


# ── 存入知識庫（優點4：問答結果回存）──────────────────────────────────────────

@router.post("/messages/{msg_id}/save_to_kb", status_code=status.HTTP_202_ACCEPTED)
async def save_message_to_kb(
    msg_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """將 AI 回答訊息存入知識庫（建立 Document 並觸發 ingest）"""
    import uuid as _uuid_mod
    from models import Document
    from services.storage import upload_file
    from tasks.document_tasks import ingest_document

    # 1. 查找訊息
    result = await db.execute(select(Message).where(Message.id == msg_id))
    msg = result.scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail="訊息不存在")
    if msg.role != "assistant":
        raise HTTPException(status_code=400, detail="只能儲存 AI 回答訊息")

    # 2. 組合 Markdown 文字（回答 + 來源附錄）
    sources_md = ""
    if msg.sources:
        lines = ["\n\n---\n## 來源文件\n"]
        for s in msg.sources:
            title = s.get("title", s.get("doc_id", "unknown"))
            page = s.get("page_number", "")
            score = s.get("score", "")
            lines.append(f"- **{title}**"
                         + (f" p.{page}" if page else "")
                         + (f" (相關度 {score:.2f})" if isinstance(score, float) else ""))
        sources_md = "\n".join(lines)

    # 從對話取得標題
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == msg.conv_id))
    conv = conv_result.scalar_one_or_none()
    conv_title = conv.title if conv else "AI 回答"
    doc_title = f"[知識] {conv_title[:60]}"

    md_content = f"# {doc_title}\n\n{msg.content}{sources_md}"
    md_bytes = md_content.encode("utf-8")

    # 3. 上傳到 MinIO（同步函式，用 asyncio executor 執行）
    doc_id = str(_uuid_mod.uuid4())
    file_path = f"uploads/{doc_id}.md"
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, upload_file, file_path, md_bytes, "text/markdown")

    # 4. 建立 Document 記錄
    doc = Document(
        id=doc_id,
        title=doc_title,
        file_path=file_path,
        file_type="md",
        status="pending",
        created_by=current_user.id if current_user else None,
    )
    db.add(doc)
    await db.commit()

    # 5. 觸發 ingest 任務
    ingest_document.delay(doc_id)

    return {"ok": True, "doc_id": doc_id, "title": doc_title}

