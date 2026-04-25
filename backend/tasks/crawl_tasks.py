"""
爬蟲 Celery 任務

Pipeline（Saga 正確順序）：
  playwright /fetch → MinIO HTML 儲存 → BeautifulSoup inner_text → SentenceWindow 分塊
  → bge-m3 嵌入 → LLM 實體分析 → PG chunks 寫入 → Qdrant 寫入 → Neo4j 寫入
  → OntologyReviewQueue INSERT → 更新文件狀態

crawl_batch_task：批量提交（SHA256 去重 → 建立文件 → 逐一 crawl_document）
所有跨庫操作由 SagaLog 保護（必要元件）。
"""
import hashlib
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
    """爬蟲任務：playwright fetch → 儲存 HTML → 交棒 ingest_document"""
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

    # 2. Playwright /fetch → html + title
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

    if not html.strip():
        with _pg_conn() as pg:
            with pg.cursor() as cur:
                cur.execute(
                    "UPDATE documents SET status='failed', error_message='頁面無內容' WHERE id=%s",
                    (doc_id,),
                )
            pg.commit()
        logger.info("[task:%s] Empty page doc_id=%s", self.request.id, doc_id)
        return

    # 3. 儲存原始 HTML 至 MinIO
    from io import BytesIO
    from minio import Minio
    html_bytes = html.encode("utf-8")
    minio_key  = f"raw_html/{doc_id}.html"
    mc = Minio(
        s.MINIO_ENDPOINT,
        access_key=s.MINIO_ACCESS_KEY,
        secret_key=s.MINIO_SECRET_KEY,
        secure=False,
    )
    if not mc.bucket_exists(s.MINIO_BUCKET):
        mc.make_bucket(s.MINIO_BUCKET)
    mc.put_object(
        s.MINIO_BUCKET, minio_key,
        BytesIO(html_bytes), len(html_bytes),
        content_type="text/html",
    )

    # 4. PG 更新 title / file_path / file_type
    with _pg_conn() as pg:
        with pg.cursor() as cur:
            cur.execute(
                "UPDATE documents SET title=%s, file_path=%s, file_type='html' WHERE id=%s",
                (display_title, minio_key, doc_id),
            )
        pg.commit()

    logger.info(
        "[task:%s] HTML stored, handing off to ingest_document doc_id=%s",
        self.request.id, doc_id,
    )

    # 5. 交棒 ingest_document（parse/chunk/embed/LLM/KB分類/Tag建議/Neo4j）
    from tasks.document_tasks import ingest_document
    ingest_document.delay(doc_id)


# ── 批量爬蟲任務 ────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="tasks.crawl_batch_task",
    max_retries=0,
)
def crawl_batch_task(self, batch_id: str, urls: list, user_id: str = None):
    """批量爬蟲：SHA256 去重 → 建立文件記錄 → 提交 crawl_document 任務"""
    queued  = 0
    skipped = 0

    for url in urls:
        doc_id = str(uuid.uuid4())
        fp     = hashlib.sha256(url.encode("utf-8")).hexdigest()
        try:
            with _pg_conn() as pg:
                with pg.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO documents
                          (id, title, source, file_type, status,
                           url_fingerprint, batch_id, created_by)
                        VALUES (%s, %s, %s, 'html', 'pending', %s, %s::uuid, %s::uuid)
                        ON CONFLICT (url_fingerprint)
                        WHERE url_fingerprint IS NOT NULL DO NOTHING
                        RETURNING id
                        """,
                        (doc_id, url[:200], url, fp, batch_id, user_id),
                    )
                    row = cur.fetchone()
                pg.commit()
        except Exception as insert_err:
            logger.warning("[batch:%s] 插入文件失敗 url=%s: %s", batch_id, url[:80], insert_err)
            skipped += 1
            continue

        if row:
            crawl_document.delay(doc_id, url)
            queued += 1
        else:
            skipped += 1

    # 更新批次：total = 實際提交數
    try:
        with _pg_conn() as pg:
            with pg.cursor() as cur:
                cur.execute(
                    "UPDATE crawl_batches SET total=%s, status='running' WHERE id=%s",
                    (queued, batch_id),
                )
            pg.commit()
    except Exception as upd_err:
        logger.warning("[batch:%s] 更新批次狀態失敗: %s", batch_id, upd_err)

    logger.info(
        "[batch:%s] 完成分派：queued=%d skipped=%d total_urls=%d",
        batch_id, queued, skipped, len(urls),
    )
