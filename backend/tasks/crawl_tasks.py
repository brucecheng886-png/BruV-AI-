"""
爬蟲 Celery 任務

Pipeline：
  playwright /fetch → BeautifulSoup inner_text → SentenceWindow 分塊
  → bge-m3 嵌入 → Qdrant 寫入 → LLM 實體分析 → Neo4j 寫入
  → PG chunks 寫入 → 更新文件狀態

所有跨庫操作由 SagaLog 保護（必要元件）。
"""
import json
import logging
import re
import uuid
from typing import List

import httpx
import psycopg2
from bs4 import BeautifulSoup
from celery import shared_task
from celery.utils.log import get_task_logger
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

logger = get_task_logger(__name__)

CHUNK_SIZE = 400   # 字元（軟上限）
WINDOW     = 3     # 句子視窗


# ── 連線工廠（Task 內建立，不共用）────────────────────────────

def _settings():
    from config import settings
    return settings


def _pg_conn():
    s = _settings()
    return psycopg2.connect(
        host=s.POSTGRES_HOST, port=s.POSTGRES_PORT,
        database=s.POSTGRES_DB, user=s.POSTGRES_USER,
        password=s.POSTGRES_PASSWORD,
    )


def _qdrant():
    s = _settings()
    return QdrantClient(host=s.QDRANT_HOST, port=s.QDRANT_PORT)


def _neo4j():
    s = _settings()
    return GraphDatabase.driver(s.NEO4J_URI, auth=(s.NEO4J_USER, s.NEO4J_PASSWORD))


# ── HTML 解析 ─────────────────────────────────────────────────

def _html_to_text(html: str) -> str:
    """BeautifulSoup 萃取正文，移除 script/style/nav/footer"""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return soup.get_text(separator="\n")


# ── 分塊 ──────────────────────────────────────────────────────

def _sentence_window_chunks(text: str) -> List[dict]:
    """SentenceWindow 分塊：3 句滑動，附前後文 window_context"""
    sentences = [s.strip() for s in
                 re.split(r"(?<=[。！？.!?\n])\s*", text) if s.strip()]
    if not sentences:
        return []
    chunks = []
    i = 0
    while i < len(sentences):
        group = sentences[i: i + WINDOW]
        content = " ".join(group)
        if len(content) > CHUNK_SIZE * 2:
            content = sentences[i]
        prev = sentences[i - 1] if i > 0 else ""
        nxt  = sentences[i + len(group)] if i + len(group) < len(sentences) else ""
        window_ctx = " ".join(filter(None, [prev, content, nxt]))
        chunks.append({
            "content":        content,
            "window_context": window_ctx,
            "page_number":    1,
        })
        i += max(1, WINDOW - 1)
    return chunks


# ── Ollama 工具 ───────────────────────────────────────────────

def _embed_texts(texts: List[str], model: str, base_url: str) -> List[List[float]]:
    """批次嵌入，每次最多 8 筆。若批次失敗則逐筆重試，仍失敗者補零向量。"""
    EMBED_DIM = 1024
    all_vecs: List[List[float]] = []
    batch = 8
    with httpx.Client(timeout=120) as client:
        for i in range(0, len(texts), batch):
            batch_texts = texts[i: i + batch]
            try:
                resp = client.post(
                    f"{base_url}/api/embed",
                    json={"model": model, "input": batch_texts},
                )
                resp.raise_for_status()
                all_vecs.extend(resp.json().get("embeddings", []))
            except httpx.HTTPStatusError:
                # 批次失敗 → 逐筆降級
                for text in batch_texts:
                    try:
                        r2 = client.post(
                            f"{base_url}/api/embed",
                            json={"model": model, "input": [text]},
                        )
                        r2.raise_for_status()
                        all_vecs.extend(r2.json().get("embeddings", []))
                    except httpx.HTTPStatusError:
                        logger.warning(
                            "Embed failed for text (len=%d), using zero vector", len(text)
                        )
                        all_vecs.append([0.0] * EMBED_DIM)
    return all_vecs


def _llm_extract(sample: str, model: str, base_url: str) -> dict:
    prompt = (
        '請分析以下文字，以JSON格式回傳（不要其他說明）：\n'
        '{"summary":"摘要100字內","tags":["tag1","tag2"],'
        '"entities":[{"name":"名稱","type":"PERSON|PLACE|ORG|CONCEPT","description":"簡述"}]}\n\n'
        f'文字：{sample[:2000]}'
    )
    with httpx.Client(timeout=180) as client:
        resp = client.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "{}")
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {"summary": "", "tags": [], "entities": []}


# ── 主任務 ────────────────────────────────────────────────────

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=60,
    name="tasks.crawl_document",
)
def crawl_document(self, doc_id: str, url: str):
    """爬蟲主任務：playwright fetch → HTML 分塊 → 三庫寫入（Saga 保護）"""
    logger.info(
        "[task:%s] Starting crawl doc_id=%s url=%s",
        self.request.id, doc_id, url,
    )
    s = _settings()

    # 1. PG 狀態 → processing
    with _pg_conn() as pg:
        with pg.cursor() as cur:
            cur.execute(
                "UPDATE documents SET status='processing' WHERE id=%s RETURNING title",
                (doc_id,),
            )
            row = cur.fetchone()
        pg.commit()

    if row is None:
        raise ValueError(f"Document {doc_id} not found in DB")

    title = row[0]

    # 2. playwright /fetch → html + title
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{s.PLAYWRIGHT_SERVICE_URL}/fetch",
            json={"url": url, "timeout_ms": 30_000},
        )
        resp.raise_for_status()
        fetch_data = resp.json()

    html          = fetch_data.get("html", "")
    fetched_title = fetch_data.get("title", "").strip()
    display_title = fetched_title or title

    # 3. BeautifulSoup inner_text
    text = _html_to_text(html)

    if not text.strip():
        with _pg_conn() as pg:
            with pg.cursor() as cur:
                cur.execute(
                    "UPDATE documents SET status='indexed', chunk_count=0 WHERE id=%s",
                    (doc_id,),
                )
            pg.commit()
        logger.info("[task:%s] Empty page doc_id=%s", self.request.id, doc_id)
        return

    # 4. SentenceWindow 分塊
    raw_chunks = _sentence_window_chunks(text)

    if not raw_chunks:
        with _pg_conn() as pg:
            with pg.cursor() as cur:
                cur.execute(
                    "UPDATE documents SET status='indexed', chunk_count=0 WHERE id=%s",
                    (doc_id,),
                )
            pg.commit()
        return

    # 5. 更新 PG title（使用頁面實際標題）
    with _pg_conn() as pg:
        with pg.cursor() as cur:
            cur.execute(
                "UPDATE documents SET title=%s WHERE id=%s",
                (display_title, doc_id),
            )
        pg.commit()

    # 6. bge-m3 嵌入
    vectors   = _embed_texts(
        [c["content"] for c in raw_chunks],
        s.OLLAMA_EMBED_MODEL,
        s.OLLAMA_BASE_URL,
    )
    chunk_ids  = [str(uuid.uuid4()) for _ in raw_chunks]
    qdrant_ids = [str(uuid.uuid4()) for _ in raw_chunks]

    # 7-10. Saga 三庫寫入
    from services.saga import SagaLog
    saga = SagaLog("crawl_document", doc_id)
    saga.begin()

    try:
        # ── Qdrant ──────────────────────────────────────────
        qdrant = _qdrant()
        points = [
            PointStruct(
                id=qid,
                vector=vec,
                payload={
                    "doc_id":      doc_id,
                    "content":     c["content"],
                    "page_number": c["page_number"],
                    "title":       display_title,
                    "source_url":  url,
                },
            )
            for qid, vec, c in zip(qdrant_ids, vectors, raw_chunks)
        ]
        qdrant.upsert(collection_name=s.QDRANT_COLLECTION, points=points)
        saga.record_step("qdrant")

        # ── LLM 分析 ────────────────────────────────────────
        sample   = " ".join(c["content"] for c in raw_chunks[:10])[:3000]
        analysis = _llm_extract(sample, s.OLLAMA_LLM_MODEL, s.OLLAMA_BASE_URL)

        # ── Neo4j ────────────────────────────────────────────
        neo_driver = _neo4j()
        with neo_driver.session(database="neo4j") as neo_sess:
            neo_sess.run(
                "MERGE (d:Document {id:$doc_id}) "
                "SET d.title=$title, d.tags=$tags, d.summary=$summary, d.source_url=$url",
                doc_id=doc_id, title=display_title,
                tags=analysis.get("tags", []),
                summary=analysis.get("summary", ""),
                url=url,
            )
            for entity in analysis.get("entities", []):
                neo_sess.run(
                    """
                    MERGE (e:Entity {name: $name})
                    SET e.type=$etype, e.description=$desc
                    WITH e
                    MATCH (d:Document {id: $doc_id})
                    MERGE (d)-[:MENTIONS]->(e)
                    """,
                    name=entity.get("name", ""),
                    etype=entity.get("type", "CONCEPT"),
                    desc=entity.get("description", ""),
                    doc_id=doc_id,
                )
        neo_driver.close()
        saga.record_step("neo4j")

        # ── PG chunks ────────────────────────────────────────
        with _pg_conn() as pg:
            with pg.cursor() as cur:
                for i, (c, qid, cid) in enumerate(
                        zip(raw_chunks, qdrant_ids, chunk_ids)):
                    cur.execute(
                        """
                        INSERT INTO chunks
                          (id, doc_id, content, chunk_index, vector_id, window_context, page_number)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (cid, doc_id, c["content"], i, qid,
                         c["window_context"], c["page_number"]),
                    )
                cur.execute(
                    "UPDATE documents SET status='indexed', chunk_count=%s WHERE id=%s",
                    (len(raw_chunks), doc_id),
                )
            pg.commit()
        saga.record_step("postgres")

        saga.commit()
        logger.info(
            "[task:%s] Crawled doc_id=%s: %d chunks url=%s",
            self.request.id, doc_id, len(raw_chunks), url,
        )

    except Exception as exc:
        saga.mark_compensated(error=str(exc))
        with _pg_conn() as pg:
            with pg.cursor() as cur:
                cur.execute(
                    "UPDATE documents SET status='failed', error_message=%s WHERE id=%s",
                    (str(exc)[:500], doc_id),
                )
            pg.commit()
        logger.error(
            "[task:%s] Crawl failed doc_id=%s: %s",
            self.request.id, doc_id, exc, exc_info=True,
        )
        raise
