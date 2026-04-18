"""
LlamaIndex Retriever Tool — 將 Qdrant 向量搜尋包裝成 LangChain Tool

架構說明（§5.3）：使用直接 Qdrant + BGE-Reranker 搜尋，不依賴 LlamaIndex VectorStoreIndex
初始化（sync），因為 LangChain Tool.func 是同步呼叫的。
"""
import logging
import httpx

from langchain.tools import Tool

from config import settings

logger = logging.getLogger(__name__)

SEARCH_TOP_K = 20
RERANK_TOP_K = 5
MAX_CONTEXT_CHARS = 3000


def _embed_query_sync(query: str) -> list[float]:
    """同步呼叫 Ollama embed（供 Tool.func 使用）"""
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{settings.OLLAMA_BASE_URL}/api/embed",
            json={"model": settings.OLLAMA_EMBED_MODEL, "input": [query]},
        )
        resp.raise_for_status()
        return resp.json().get("embeddings", [[]])[0]


def knowledge_base_search(query: str) -> str:
    """
    搜尋本地知識庫，回答與已上傳文件相關的問題。
    """
    try:
        # 1. 向量化
        query_vec = _embed_query_sync(query)
        if not query_vec:
            return "知識庫查詢失敗：無法取得 embedding。"

        # 2. Qdrant 同步搜尋（qdrant-client 1.7+ 使用 query_points）
        from qdrant_client import QdrantClient
        from qdrant_client.models import NamedVector
        qdrant = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )
        result = qdrant.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=query_vec,
            limit=SEARCH_TOP_K,
            with_payload=True,
        )
        hits = result.points

        if not hits:
            return "知識庫中沒有找到相關內容。"

        # 3. BGE Re-ranker（sync）
        passages = [h.payload.get("content", "") for h in hits]
        try:
            from services.reranker import _reranker_instance
            if _reranker_instance is not None:
                top_idxs = _reranker_instance.rerank(query, passages, top_k=RERANK_TOP_K)
                hits = [hits[i] for i in top_idxs]
        except Exception as e:
            logger.warning("Re-ranker 不可用，使用原始排序: %s", e)
            hits = hits[:RERANK_TOP_K]

        # 4. 組合 context
        context_parts = []
        chars = 0
        for hit in hits:
            text = hit.payload.get("content", "")
            title = hit.payload.get("title", "")
            page = hit.payload.get("page_number", "")
            if chars + len(text) <= MAX_CONTEXT_CHARS:
                context_parts.append(f"[{title} p.{page}] {text}")
                chars += len(text)

        if not context_parts:
            return "知識庫中沒有找到足夠相關的內容。"

        return "\n\n".join(context_parts)

    except Exception as e:
        logger.error("knowledge_base_search 失敗: %s", e, exc_info=True)
        return f"知識庫查詢發生錯誤：{e}"


def build_knowledge_base_tool() -> Tool:
    return Tool(
        name="knowledge_base_search",
        func=knowledge_base_search,
        description=(
            "搜尋本地知識庫，回答與已上傳文件相關的問題。"
            "輸入：查詢字串（中文或英文）。"
            "輸出：相關文件片段，含來源標題和頁碼。"
        ),
    )
