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
import re
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, update as sa_update, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
from auth import CurrentUser
from database import get_db, get_qdrant_client
from models import Conversation, Message, KnowledgeBase, Document
from services.reranker import get_reranker
from routers.settings_router import get_rag_runtime_config, get_kb_schema, get_chat_runtime_config
from prompts import RAG_SYSTEM_PROMPT, TITLE_GEN_PROMPT, REFLECTION_JUDGE_PROMPT, REFLECTION_TOTAL_THRESHOLD
from prompts.page_agents import get_page_agent_prompt

logger = logging.getLogger(__name__)
router = APIRouter()

# ── 後端 Action 執行器 ────────────────────────────────────────

_ACTION_RE_BACKEND = re.compile(r'__action__:(\{[^\n]+\})')
# Write operations that backend handles (read ops list_kbs/list_all_docs handled by frontend)
_BACKEND_WRITE_TYPES = frozenset({
    "delete_kb", "batch_delete_kb", "create_kb",
    "delete_doc", "batch_delete_doc",
    "move_to_kb", "batch_move_to_kb", "edit_doc",
    "delete_conv",
    "batch_approve_all", "batch_reject_all",
    "toggle_plugin",
})


async def _execute_action_backend(action: dict, db) -> tuple[str, str | None]:
    """Execute a write action directly on the backend.
    Returns (result_text, dispatch_event_type | None)"""
    from sqlalchemy import select, text as _sqlt, update as _sqlu, delete as _sqld
    from models import KnowledgeBase as _KB, Document as _Doc, DocumentKnowledgeBase as _DKB, Conversation as _Conv
    from datetime import datetime, timezone

    atype = action.get("type", "")
    try:
        if atype == "delete_kb":
            kid = action.get("kb_id", "")
            row = (await db.execute(select(_KB).where(_KB.id == kid))).scalar_one_or_none()
            if not row:
                return f"❌ 找不到知識庫 {kid}", None
            await db.delete(row)
            await db.commit()
            return "✅ 已刪除知識庫", "reload_kbs"

        elif atype == "batch_delete_kb":
            kb_ids = action.get("kb_ids", [])
            ok = fail = 0
            for kid in kb_ids:
                row = (await db.execute(select(_KB).where(_KB.id == kid))).scalar_one_or_none()
                if row:
                    await db.delete(row); ok += 1
                else:
                    fail += 1
            await db.commit()
            return f"✅ 已刪除 {ok} 個知識庫{f'，失敗 {fail} 個' if fail else ''}", "reload_kbs"

        elif atype == "create_kb":
            name = action.get("name", "新知識庫")
            desc = action.get("description", "")
            new_kb = _KB(id=str(uuid.uuid4()), name=name, description=desc)
            db.add(new_kb)
            await db.commit()
            return f"✅ 已建立知識庫「{name}」", "reload_kbs"

        elif atype == "delete_doc":
            did = action.get("doc_id", "")
            row = (await db.execute(select(_Doc).where(_Doc.id == did))).scalar_one_or_none()
            if not row:
                return f"❌ 找不到文件 {did}", None
            row.deleted_at = datetime.now(timezone.utc)
            await db.commit()
            return "✅ 已刪除文件", "reload_docs"

        elif atype == "batch_delete_doc":
            doc_ids = action.get("doc_ids", [])
            ok = fail = 0
            now = datetime.now(timezone.utc)
            for did in doc_ids:
                row = (await db.execute(select(_Doc).where(_Doc.id == did))).scalar_one_or_none()
                if row:
                    row.deleted_at = now; ok += 1
                else:
                    fail += 1
            await db.commit()
            return f"✅ 已刪除 {ok} 篇文件{f'，失敗 {fail} 篇' if fail else ''}", "reload_docs"

        elif atype == "move_to_kb":
            did, kid = action.get("doc_id", ""), action.get("kb_id", "")
            row = (await db.execute(select(_Doc).where(_Doc.id == did))).scalar_one_or_none()
            if not row:
                return f"❌ 找不到文件 {did}", None
            row.knowledge_base_id = kid
            await db.execute(_sqld(_DKB).where(_DKB.doc_id == did))
            if kid:
                db.add(_DKB(doc_id=did, kb_id=kid, source="manual"))
            await db.commit()
            return "✅ 已移入知識庫", "reload_docs"

        elif atype == "batch_move_to_kb":
            doc_ids = action.get("doc_ids", [])
            kid = action.get("kb_id", "")
            ok = fail = 0
            for did in doc_ids:
                row = (await db.execute(select(_Doc).where(_Doc.id == did))).scalar_one_or_none()
                if row:
                    row.knowledge_base_id = kid
                    await db.execute(_sqld(_DKB).where(_DKB.doc_id == did))
                    if kid:
                        db.add(_DKB(doc_id=did, kb_id=kid, source="manual"))
                    ok += 1
                else:
                    fail += 1
            await db.commit()
            return f"✅ 已移入知識庫：{ok} 篇{f'，找不到 {fail} 篇' if fail else ''}", "reload_docs"

        elif atype == "edit_doc":
            did = action.get("doc_id", "")
            row = (await db.execute(select(_Doc).where(_Doc.id == did))).scalar_one_or_none()
            if not row:
                return f"❌ 找不到文件 {did}", None
            if action.get("title"):
                row.title = action["title"]
            if action.get("description") is not None:
                row.description = action.get("description")
            await db.commit()
            return "✅ 已更新文件 metadata", "reload_docs"

        elif atype == "delete_conv":
            cid = action.get("conv_id", "")
            row = (await db.execute(select(_Conv).where(_Conv.id == cid))).scalar_one_or_none()
            if not row:
                return f"❌ 找不到對話 {cid}", None
            await db.delete(row)
            await db.commit()
            return "✅ 已刪除對話", None

        elif atype == "batch_approve_all":
            res = await db.execute(
                _sqlt("UPDATE ontology_review_queue SET status='approved' WHERE status='pending' RETURNING id")
            )
            count = len(res.fetchall())
            await db.commit()
            return f"✅ 已批次核准 {count} 筆實體", None

        elif atype == "batch_reject_all":
            res = await db.execute(
                _sqlt("UPDATE ontology_review_queue SET status='rejected' WHERE status='pending' RETURNING id")
            )
            count = len(res.fetchall())
            await db.commit()
            return f"✅ 已批次拒絕 {count} 筆實體", None

        elif atype == "toggle_plugin":
            from models import Plugin as _Plugin
            pid = action.get("plugin_id", "")
            enabled = bool(action.get("enabled", True))
            await db.execute(
                _sqlu(_Plugin).where(_Plugin.id == pid).values(enabled=enabled)
            )
            await db.commit()
            return f"✅ 已{'啟用' if enabled else '停用'}插件", None

        else:
            return f"⚠️ 後端不支援操作類型：{atype}", None

    except Exception as _e:
        logger.warning("_execute_action_backend [%s] error: %s", atype, _e)
        return f"❌ 操作失敗：{_e}", None

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
    regenerated_from: str | None = None


# ── SSE 產生器 ────────────────────────────────────────────────

async def _embed_query(query: str, settings, model: str | None = None, provider: str | None = None,
                      base_url: str | None = None, api_key: str | None = None) -> list[float]:
    """查詢嵌入：預設走 Ollama bge-m3；可依 KB 設定覆寫為雲端 provider。
    任何失敗均回傳 [] 並記錄警告，避免讓上層 SSE 連線崩斷（退化為無 RAG 模式）。"""
    try:
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
    except Exception as e:
        logger.warning("embed_query failed (provider=%s, model=%s): %s — fallback to no-RAG", provider, model, e)
        return []


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


# page_agent prompts 已搬移至 backend/prompts/page_agents.py（E6）
# 透過 get_page_agent_prompt(page) 取用，含共用 footer 與危險操作規範


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
    user_id: str | None = None,
    regenerated_from: str | None = None,
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
    try:
        rag_cfg  = await get_rag_runtime_config(db)
        chat_cfg = await get_chat_runtime_config(db)
    except Exception as _cfg_err:
        logger.warning("get_runtime_config failed: %s — using defaults", _cfg_err)
        rag_cfg  = {}
        chat_cfg = {}
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
    try:
        search_result_obj = await qdrant.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=query_vec,
            limit=_top_k,
            with_payload=True,
            query_filter=qdrant_filter,
        )
        search_result = search_result_obj.points
    except Exception as _qe:
        logger.error("Qdrant search failed: %s", _qe)
        yield "data: " + json.dumps({"type": "error", "text": f"向量資料庫連線失敗：{_qe}"}) + "\n\n"
        yield "data: [DONE]\n\n"
        return

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
        chunk_id = hit.payload.get("chunk_id") or str(getattr(hit, "id", "") or "")
        if chars + len(text) <= _max_context_chars:
            context_parts.append(f"[{title} p.{page}] {text}")
            chars += len(text)
            sources.append({
                "doc_id": doc_id,
                "title": title,
                "page_number": page,
                "score": hit.score,
                "chunk_id": chunk_id,
                "content_preview": text[:200],
            })

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
        _agent_prefix = get_page_agent_prompt(_page) + "\n\n"
        _page_for_skill = _page
    elif agent_type == "global_agent":
        _agent_prefix = get_page_agent_prompt("global") + "\n\n"
        _page_for_skill = "global"
    elif agent_type == "kb_agent":
        _agent_prefix = get_page_agent_prompt("kb") + "\n\n"
        _page_for_skill = "kb"
        # 若該 KB 有自訂 agent_prompt，優先採用
        if conv_kb_scope_id:
            try:
                from sqlalchemy import text as _kbt
                _kb_row = (await db.execute(
                    _kbt("SELECT agent_prompt FROM knowledge_bases WHERE id = :kid"),
                    {"kid": conv_kb_scope_id},
                )).fetchone()
                if _kb_row and _kb_row.agent_prompt and _kb_row.agent_prompt.strip():
                    _agent_prefix = _kb_row.agent_prompt.strip() + "\n\n"
            except Exception:
                pass

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
        + RAG_SYSTEM_PROMPT
        + f"{schema_section}"
        f"{extra_section}"
        f"{_mode_suffix}"
        f"{file_context_section}\n\n"
        f"參考資料：\n{context}"
    )

    # Phase D：prompt_template_auto_match 開啟時，取最佳模板注入 system prompt 結尾
    _matched_template_id: str | None = None
    if chat_cfg.get("prompt_template_auto_match"):
        try:
            from routers.prompt_engine import match_template as _match_template_fn, MatchRequest as _MatchRequest
            _match_resp = await _match_template_fn(
                _MatchRequest(intent=query, context={}),
                current_user=None,
                db=db,
            )
            if _match_resp and _match_resp.confidence >= 0.7:
                _matched_template_id = _match_resp.matched_template_id
                system_prompt += (
                    f"\n\n【已自動套用模板：{_match_resp.title}】\n"
                    f"{_match_resp.filled_prompt}"
                )
                logger.info("prompt_template auto-matched id=%s confidence=%.3f", _matched_template_id, _match_resp.confidence)
        except HTTPException as _he:
            logger.info("prompt_template auto-match no result: %s", _he.detail)
        except Exception as _me:
            logger.warning("prompt_template auto-match failed: %s", _me)

    # 5. 取先前對話紀錄（摘要 + 近期完整輪次）
    try:
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
    except Exception as _hist_err:
        logger.warning("history load failed: %s — starting fresh", _hist_err)
        total_msg_count = 0
        existing_summary = None
        recent_msgs = []

    # 重生成：排除指定的舊 assistant 訊息，避免它出現在 history 中
    if regenerated_from:
        recent_msgs = [m for m in recent_msgs if m.id != regenerated_from]

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

    # 6. 儲存使用者訊息（重生成模式跳過，避免重覆）
    if not regenerated_from:
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
    from services.llm_resolver import resolve_model_runtime, apply_model_runtime
    from services.llm_metrics import track_llm_call
    try:
        runtime_config = await get_llm_runtime_config(db)
    except Exception as _rc_err:
        logger.warning("get_llm_runtime_config failed: %s — using empty config", _rc_err)
        runtime_config = {}

    # 依第一原則（first-principles-api-key §三）：以 model_name 解析 model-level 設定
    # provider 由 model 名稱自動推測；model-level 的 api_key / base_url / provider 覆寫 system_settings fallback
    if model:
        try:
            _mr = await resolve_model_runtime(db, model, fallback_provider=runtime_config.get("provider"))
            runtime_config = apply_model_runtime(runtime_config, _mr)
        except ValueError as _ve:
            logger.error("resolve_model_runtime strict reject: %s", _ve)
            err_text = f"模型設定錯誤：{_ve}"
            db.add(Message(
                id=str(uuid.uuid4()), conv_id=conv_id, role="assistant",
                content=err_text, sources=[],
            ))
            await db.commit()
            yield "data: " + json.dumps({"type": "error", "text": err_text}) + "\n\n"
            yield "data: [DONE]\n\n"
            return

    _eff_provider = runtime_config.get("provider") or settings.LLM_PROVIDER
    _eff_model = model or runtime_config.get("model") or "unknown"

    # 7. 串流 LLM（統一適配層）
    # 改善三：若 provider 支援 function calling 且頁面有工具定義，使用 llm_with_tools（非串流）
    from llm_client import llm_with_tools, FC_PROVIDERS
    from prompts.page_agents import get_tools_for_page as _get_tools

    _use_fc = (
        _eff_provider in FC_PROVIDERS
        and bool(_page_for_skill)
        and mode == "agent"
        and bool(_get_tools(_page_for_skill))
    )

    full_reply = ""
    _fc_tool_calls: list[dict] = []  # populated when FC path is used

    if _use_fc:
        # FC 路徑：非串流呼叫，取得 text + tool_calls
        _tools = _get_tools(_page_for_skill)
        try:
            async with track_llm_call(
                model=_eff_model, provider=_eff_provider, call_type="chat",
                user_id=user_id, conv_id=conv_id,
                template_id=_matched_template_id,
            ) as _on_usage:
                _fc_result = await llm_with_tools(
                    messages_payload, _tools, settings,
                    model_override=model,
                    config_override=runtime_config,
                    max_tokens=_max_tokens,
                )
            fc_text = _fc_result.get("text", "")
            _fc_tool_calls = _fc_result.get("tool_calls", [])
            # 若 FC 無 tool_calls 也無 text（provider 不支援），fallback 到文字路徑
            if not fc_text and not _fc_tool_calls:
                _use_fc = False
            else:
                full_reply = fc_text
                # 模擬串流：逐詞 yield text tokens
                if fc_text:
                    _words = fc_text.split(" ")
                    for _i, _w in enumerate(_words):
                        _tok = (_w + " ") if _i < len(_words) - 1 else _w
                        yield "data: " + json.dumps({"type": "token", "text": _tok}) + "\n\n"
        except Exception as _fce:
            logger.warning("llm_with_tools failed, fallback to llm_stream: %s", _fce)
            _use_fc = False
            full_reply = ""
            _fc_tool_calls = []

    if not _use_fc:
        # 文字串流路徑（原有邏輯）
        try:
            async with track_llm_call(
                model=_eff_model, provider=_eff_provider, call_type="chat",
                user_id=user_id, conv_id=conv_id,
                template_id=_matched_template_id,
            ) as _on_usage:
                async for token in llm_stream(
                    messages_payload, settings,
                    model_override=model,
                    config_override=runtime_config,
                    temperature=_temperature,
                    max_tokens=_max_tokens,
                    usage_callback=_on_usage,
                ):
                    full_reply += token
                    yield "data: " + json.dumps({"type": "token", "text": token}) + "\n\n"
        except httpx.HTTPStatusError as e:
            logger.error("LLM stream error: %s", e)
            _status = getattr(getattr(e, "response", None), "status_code", "?")
            _resp_preview = ""
            try:
                _resp_preview = (e.response.text or "")[:120].replace("\n", " ")
            except Exception:
                pass
            err_text = (
                f"LLM 服務錯誤（{_eff_provider} HTTP {_status}）：{_resp_preview}"
                if _resp_preview
                else f"LLM 服務錯誤（{_eff_provider} HTTP {_status}）"
            )
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

    # 7b. 改善二：後端執行 action（FC tool_calls 或文字 __action__ 解析）
    # FC 路徑：執行 tool_calls
    for _tc in _fc_tool_calls:
        _tc_action = {"type": _tc.get("name", ""), **(_tc.get("arguments") or {})}
        if _tc_action.get("type") in _BACKEND_WRITE_TYPES:
            _tc_res, _tc_dispatch = await _execute_action_backend(_tc_action, db)
            yield "data: " + json.dumps({
                "type": "action_result",
                "action_type": _tc_action.get("type"),
                "result": _tc_res,
                "dispatch": _tc_dispatch,
            }, ensure_ascii=False) + "\n\n"

    # 文字路徑：解析 __action__:{} 並執行寫入操作
    if not _use_fc:
        for _am in _ACTION_RE_BACKEND.finditer(full_reply):
            try:
                _act = json.loads(_am.group(1))
            except Exception:
                continue
            if _act.get("type") in _BACKEND_WRITE_TYPES:
                _ar, _ad = await _execute_action_backend(_act, db)
                yield "data: " + json.dumps({
                    "type": "action_result",
                    "action_type": _act.get("type"),
                    "result": _ar,
                    "dispatch": _ad,
                }, ensure_ascii=False) + "\n\n"

    # 8. 儲存助理回覆
    assistant_msg = Message(
        id=str(uuid.uuid4()),
        conv_id=conv_id,
        role="assistant",
        content=full_reply,
        sources=sources,
        regenerated_from=regenerated_from,
    )
    db.add(assistant_msg)
    await db.commit()

    # 9. 傳送 sources 事件
    yield "data: " + json.dumps({"type": "sources", "sources": sources}) + "\n\n"

    # 9a. E7：若涉及文件有 ingestion_warnings，發送 system_notice 提示前端
    try:
        _doc_ids = [s.get("doc_id") for s in sources if s.get("doc_id")]
        if _doc_ids:
            _seen = set()
            _unique_ids = [d for d in _doc_ids if not (d in _seen or _seen.add(d))]
            _wrow = await db.execute(
                sa_text("SELECT id, ingestion_warnings FROM documents WHERE id = ANY(:ids) AND jsonb_array_length(COALESCE(ingestion_warnings,'[]'::jsonb)) > 0"),
                {"ids": _unique_ids},
            )
            _warn_docs = _wrow.fetchall()
            if _warn_docs:
                from prompts import EMBEDDING_FALLBACK_NOTICE
                yield "data: " + json.dumps({
                    "type": "system_notice",
                    "level": "warning",
                    "message": EMBEDDING_FALLBACK_NOTICE,
                    "affected_doc_ids": [str(r[0]) for r in _warn_docs],
                }, ensure_ascii=False) + "\n\n"
    except Exception as _we:
        logger.warning("system_notice for ingestion_warnings failed: %s", _we)

    # 9b. C2 Chat Reflection（system_settings.chat_reflection_enabled 開啟時）
    try:
        _ref_row = (await db.execute(
            sa_text("SELECT value FROM system_settings WHERE key='chat_reflection_enabled'")
        )).first()
        _ref_on = bool(_ref_row and str(_ref_row[0]).strip().lower() in ("1", "true", "on", "yes"))
    except Exception:
        _ref_on = False

    if _ref_on and full_reply.strip() and context.strip():
        try:
            judge_prompt = REFLECTION_JUDGE_PROMPT(query, context, full_reply)
            judge_messages = [{"role": "user", "content": judge_prompt}]
            judge_text = ""
            async with track_llm_call(
                model=_eff_model, provider=_eff_provider, call_type="reflection",
                user_id=user_id, conv_id=conv_id,
            ) as _on_judge_usage:
                async for tk in llm_stream(
                    judge_messages, settings,
                    model_override=model,
                    config_override=runtime_config,
                    temperature=0.0,
                    max_tokens=400,
                    usage_callback=_on_judge_usage,
                ):
                    judge_text += tk
            # 嘗試從回覆內擷取 JSON
            _jt = judge_text.strip()
            if "```" in _jt:
                _jt = _jt.split("```")[1]
                if _jt.startswith("json"):
                    _jt = _jt[4:]
            _jt = _jt.strip()
            try:
                judge_obj = json.loads(_jt)
            except Exception:
                judge_obj = None
            if isinstance(judge_obj, dict):
                _scores = judge_obj.get("scores") or {}
                _total = judge_obj.get("total")
                if not isinstance(_total, int):
                    try:
                        _total = sum(int(v) for v in _scores.values()) if _scores else 0
                    except Exception:
                        _total = 0
                _should_regen = bool(judge_obj.get("should_regenerate"))
                _regen_hint = (judge_obj.get("regenerate_hint") or "").strip()
                yield "data: " + json.dumps({
                    "type": "reflection",
                    "scores": _scores,
                    "total": _total,
                    "verdict": judge_obj.get("verdict", ""),
                    "should_regenerate": _should_regen,
                }, ensure_ascii=False) + "\n\n"

                # 不足門檻且裁議 should_regenerate → 以 hint 重生一次
                if _should_regen and (_total or 0) < REFLECTION_TOTAL_THRESHOLD and _regen_hint:
                    regen_messages = list(messages_payload)
                    # 以 system 附加提示，保留原始上下文
                    regen_messages.append({
                        "role": "system",
                        "content": f"以下是審查嘴意見，請重新回答並修正不足：{_regen_hint}",
                    })
                    regen_full = ""
                    async with track_llm_call(
                        model=_eff_model, provider=_eff_provider, call_type="chat_regen",
                        user_id=user_id, conv_id=conv_id,
                    ) as _on_regen_usage:
                        async for tk in llm_stream(
                            regen_messages, settings,
                            model_override=model,
                            config_override=runtime_config,
                            temperature=_temperature,
                            max_tokens=_max_tokens,
                            usage_callback=_on_regen_usage,
                        ):
                            regen_full += tk
                            yield "data: " + json.dumps({"type": "regen_token", "text": tk}) + "\n\n"
                    if regen_full.strip():
                        # 更新原 assistant 訊息為重生版（保留原本於 content 以 ===REGEN=== 區隔以供查看）
                        merged = full_reply + "\n\n---\n【反思重生】\n" + regen_full
                        await db.execute(
                            sa_update(Message)
                            .where(Message.id == assistant_msg.id)
                            .values(content=merged)
                        )
                        await db.commit()
                        full_reply = merged
                        yield "data: " + json.dumps({"type": "regen_done"}) + "\n\n"
        except Exception as _re:
            logger.warning("Chat reflection failed: %s", _re)

    # 10. 自動命名（conv_title == "新對話" 時觸發）
    if conv_title == "新對話":
        try:
            title_messages = [
                {"role": "user", "content": TITLE_GEN_PROMPT(query)}
            ]
            new_title = ""
            async with track_llm_call(
                model=_eff_model, provider=_eff_provider, call_type="title",
                user_id=user_id, conv_id=conv_id,
            ) as _on_title_usage:
                async for token in llm_stream(
                    title_messages, settings,
                    model_override=model,
                    config_override=runtime_config,
                    temperature=0.3,
                    max_tokens=30,
                    usage_callback=_on_title_usage,
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

@router.post("/rag-search")
async def rag_search(
    req: ChatRequest,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """純 RAG 檢索端點：嵌入 query 後從 Qdrant 取 top-k chunks，僅回傳 sources（不呼叫 LLM）。
    給 MCP rag_search tool 使用。"""
    from config import settings as _settings

    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能為空")

    top_k = 8
    qdrant_filter = None
    kb_id = req.kb_scope_id
    doc_ids = req.doc_ids
    if doc_ids:
        qdrant_filter = Filter(must=[FieldCondition(key="doc_id", match=MatchAny(any=doc_ids))])
    elif kb_id:
        qdrant_filter = Filter(must=[FieldCondition(key="kb_id", match=MatchValue(value=kb_id))])

    query_vec = await _embed_query(req.query, _settings)
    qdrant = get_qdrant_client()
    res = await qdrant.query_points(
        collection_name=_settings.QDRANT_COLLECTION,
        query=query_vec,
        limit=top_k,
        with_payload=True,
        query_filter=qdrant_filter,
    )
    sources = []
    for hit in res.points:
        payload = hit.payload or {}
        sources.append({
            "chunk_id":        payload.get("chunk_id") or str(getattr(hit, "id", "") or ""),
            "doc_id":          payload.get("doc_id", ""),
            "title":           payload.get("title", ""),
            "page_number":     payload.get("page_number"),
            "score":           hit.score,
            "content_preview": (payload.get("content") or "")[:400],
        })
    return {"query": req.query, "results": sources}


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
            user_id=current_user.id if current_user else None,
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

    # 分析附件，建立 file_context（先組基本內容，第一輪 priming 在 conv 解析後加）
    file_context: Optional[str] = None
    _file_priming: Optional[str] = None  # 僅第一輪注入的「先詢問意圖」提示
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        fname = file.filename
        if ext in _EXCEL_EXTENSIONS:
            file_context = f"【使用者本次附上檔案：{fname}（Excel/CSV）】"
            _file_priming = (
                "在進行任何操作之前，請先確認使用者的意圖：是要匯入連結清單、進行資料分析、還是其他用途？\n"
                "若使用者明確說要「匯入」或「匯入連結」，請在回應中加入以下 JSON 標記（獨立一行）：\n"
                '{"__action__": "import_excel"}'
            )
        elif ext in _DOC_EXTENSIONS:
            file_context = f"【使用者本次附上檔案：{fname}】"
            _file_priming = "在進行任何操作之前，請先詢問使用者：是要將此文件加入知識庫，還是只想讓你閱讀並回答問題？"
        else:
            file_context = f"【使用者本次附上檔案：{fname}，格式暫不支援自動處理】"

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
    # 第一輪才注入 file priming（詢問意圖）；之後使用者已表態則只保留檔案名稱
    if file_context and _file_priming:
        try:
            _msg_count_res = await db.execute(
                select(func.count(Message.id)).where(Message.conv_id == conv_id)
            )
            _msg_count = _msg_count_res.scalar() or 0
        except Exception:
            _msg_count = 0
        if _msg_count == 0:
            file_context = file_context + "\n" + _file_priming
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
            user_id=current_user.id if current_user else None,
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


# ── C1：訊息重生成 ──────────────────────────────────────────────

@router.post("/conversations/{conv_id}/messages/{msg_id}/regenerate")
async def regenerate_message(
    conv_id: str,
    msg_id: str,
    model: Optional[str] = None,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """重新生成指定 assistant 訊息：以前一則 user 訊息為輸入，重跑 RAG。
    新訊息的 regenerated_from 指向 msg_id，前端可據此呈現分支關係。
    """
    from config import settings
    # 1. 驗證對話與訊息
    conv_r = await db.execute(select(Conversation).where(Conversation.id == conv_id))
    conv = conv_r.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="對話不存在")

    msg_r = await db.execute(select(Message).where(Message.id == msg_id, Message.conv_id == conv_id))
    target = msg_r.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="訊息不存在")
    if target.role != "assistant":
        raise HTTPException(status_code=400, detail="只能重新生成 AI 回覆")

    # 2. 取得緊鄰前一則 user 訊息
    prev_r = await db.execute(
        select(Message)
        .where(Message.conv_id == conv_id, Message.role == "user", Message.created_at <= target.created_at)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    prev_user = prev_r.scalar_one_or_none()
    if prev_user is None:
        raise HTTPException(status_code=400, detail="找不到對應的使用者訊息")

    return StreamingResponse(
        _rag_stream(
            prev_user.content, conv_id, model, settings, db,
            conv_doc_scope_ids=conv.doc_scope_ids or None,
            conv_kb_scope_id=conv.kb_scope_id,
            conv_tag_scope_ids=conv.tag_scope_ids or None,
            conv_title=conv.title or "",
            agent_type=conv.agent_type or "chat",
            mode="agent",
            user_id=current_user.id if current_user else None,
            regenerated_from=msg_id,
        ),
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


# ── 改善二：後端直接執行 action 端點 ─────────────────────────

class ExecuteActionIn(BaseModel):
    action_type: str
    params: dict = {}


@router.post("/execute-action")
async def execute_action_endpoint(
    req: ExecuteActionIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    action = {"type": req.action_type, **req.params}
    result, dispatch = await _execute_action_backend(action, db)
    return {"result": result, "dispatch": dispatch}


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
        created_at=m.created_at.isoformat(),
        regenerated_from=getattr(m, "regenerated_from", None),
    ) for m in msgs]


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

