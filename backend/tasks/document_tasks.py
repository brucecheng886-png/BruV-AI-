"""
文件攝取 Celery 任務

Pipeline：
  MinIO 下載 → 解析 → SentenceWindow 分塊 (Excel 除外)
  → bge-m3 嵌入 → Qdrant 寫入 → LLM 實體分析 → Neo4j 寫入
  → PG chunks 寫入 → 更新文件狀態

所有跨庫操作由 SagaLog 保護（必要元件）。
"""
import io
import json
import logging
import re
import uuid
from typing import List, Tuple

import httpx
import psycopg2
from celery import shared_task
from celery.utils.log import get_task_logger
from minio import Minio
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

logger = get_task_logger(__name__)


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


def _minio():
    s = _settings()
    return Minio(s.MINIO_ENDPOINT,
                 access_key=s.MINIO_ACCESS_KEY,
                 secret_key=s.MINIO_SECRET_KEY,
                 secure=False)


def _qdrant():
    s = _settings()
    return QdrantClient(host=s.QDRANT_HOST, port=s.QDRANT_PORT)


def _neo4j():
    s = _settings()
    return GraphDatabase.driver(s.NEO4J_URI, auth=(s.NEO4J_USER, s.NEO4J_PASSWORD))


# ── 文件解析 ───────────────────────────────────────────────────

def _parse_pdf(data: bytes) -> List[Tuple[str, int]]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return [(p.extract_text() or "", i + 1)
            for i, p in enumerate(reader.pages)
            if (p.extract_text() or "").strip()]


def _parse_docx(data: bytes) -> List[Tuple[str, int]]:
    from docx import Document as DocxDoc
    doc = DocxDoc(io.BytesIO(data))
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return [(text, 1)]


def _parse_xlsx(data: bytes) -> List[Tuple[str, int]]:
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    results = []
    for sheet_idx, ws in enumerate(wb.worksheets, 1):
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        headers = [str(h) if h is not None else f"col{i}"
                   for i, h in enumerate(rows[0])]
        for row in rows[1:]:
            if all(v is None for v in row):
                continue
            parts = [f"{h}: {v}" for h, v in zip(headers, row) if v is not None]
            text = " | ".join(parts)
            if text.strip():
                results.append((text, sheet_idx))
    return results


def _parse_html(data: bytes) -> List[Tuple[str, int]]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return [(soup.get_text(separator="\n"), 1)]


def _parse_text(data: bytes) -> List[Tuple[str, int]]:
    # 嘗試 UTF-8（含 BOM）→ fallback CP950（繁中 Windows）
    for enc in ("utf-8-sig", "utf-8", "cp950", "latin-1"):
        try:
            text = data.decode(enc)
            return [(text, 1)]
        except (UnicodeDecodeError, LookupError):
            continue
    return [(data.decode("utf-8", errors="replace"), 1)]


_PARSERS = {
    "pdf": _parse_pdf,
    "docx": _parse_docx,
    "xlsx": _parse_xlsx,
    "html": _parse_html,
    "txt":  _parse_text,
    "md":   _parse_text,
    "csv":  _parse_text,
}


# ── 分塊 ──────────────────────────────────────────────────────

CHUNK_SIZE = 400     # 字元（軟上限）
WINDOW     = 3       # 句子視窗


def _sentence_window_chunks(text: str, page: int) -> List[dict]:
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
            "content": content,
            "window_context": window_ctx,
            "page_number": page,
        })
        i += max(1, WINDOW - 1)
    return chunks


def _xlsx_chunks(pages: List[Tuple[str, int]]) -> List[dict]:
    """Excel：每行直接成為一個 chunk（不做 sentence window）"""
    return [{"content": t, "window_context": t, "page_number": pg}
            for t, pg in pages if t.strip()]


# ── Ollama 工具 ───────────────────────────────────────────────

def _embed_texts(texts: List[str], model: str, base_url: str) -> List[List[float]]:
    """批次嵌入，每次最多 8 筆；若批次失敗則逐一降級；NaN 以 0.0 取代"""
    import math

    # 預先偵測向量維度（用一個短文字探測）
    _DIM_CACHE: List[int] = []
    def _get_dim() -> int:
        if _DIM_CACHE:
            return _DIM_CACHE[0]
        try:
            r = httpx.post(f"{base_url}/api/embed", json={"model": model, "input": ["dim"]}, timeout=30)
            if r.status_code == 200:
                vecs = r.json().get("embeddings", [[]])
                dim = len(vecs[0]) if vecs else 1024
            else:
                dim = 1024
        except Exception:
            dim = 1024
        _DIM_CACHE.append(dim)
        return dim

    def _clean_vec(vec: List[float]) -> List[float]:
        return [0.0 if (v is None or (isinstance(v, float) and math.isnan(v))) else v for v in vec]

    def _embed_one(text: str) -> List[float]:
        try:
            with httpx.Client(timeout=120) as client:
                r = client.post(f"{base_url}/api/embed", json={"model": model, "input": [text]})
                r.raise_for_status()
                vecs = r.json().get("embeddings", [[]])
                return _clean_vec(vecs[0]) if vecs else [0.0] * _get_dim()
        except Exception:
            logger.warning("Failed to embed text (fallback to zero): %s", text[:60])
            return [0.0] * _get_dim()

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
                vecs = resp.json().get("embeddings", [])
                if len(vecs) == len(batch_texts):
                    all_vecs.extend([_clean_vec(v) for v in vecs])
                    continue
            except Exception:
                pass
            # 批次失敗 → 逐一嵌入
            logger.warning("Batch embed failed (batch %d-%d), falling back to individual", i, i + len(batch_texts))
            for t in batch_texts:
                all_vecs.append(_embed_one(t))
    return all_vecs


def _llm_extract(sample: str, model: str, base_url: str) -> dict:
    """LLM 提取摘要、標籤、實體（非串流，JSON 輸出）"""
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
    name="tasks.ingest_document",
)
def ingest_document(self, doc_id: str):
    """文件攝取主任務：解析 → LLM 分析 → 三庫寫入（Saga 保護）"""
    logger.info("[task:%s] Starting ingestion for doc_id=%s", self.request.id, doc_id)
    s = _settings()

    # 1. PG 取文件資訊，狀態 → processing
    with _pg_conn() as pg:
        with pg.cursor() as cur:
            cur.execute(
                "UPDATE documents SET status='processing' WHERE id=%s "
                "RETURNING file_path, file_type, title",
                (doc_id,),
            )
            row = cur.fetchone()
        pg.commit()

    if row is None:
        raise ValueError(f"Document {doc_id} not found in DB")
    file_path, file_type, title = row

    # 2. MinIO 下載
    mc = _minio()
    response = mc.get_object(s.MINIO_BUCKET, file_path)
    data = response.read()
    response.close()
    response.release_conn()

    # 3. 解析
    parser = _PARSERS.get(file_type or "", _parse_text)
    pages  = parser(data)

    # 4. 分塊
    if file_type == "xlsx":
        raw_chunks = _xlsx_chunks(pages)
    else:
        raw_chunks = []
        for text, page in pages:
            raw_chunks.extend(_sentence_window_chunks(text, page))

    if not raw_chunks:
        with _pg_conn() as pg:
            with pg.cursor() as cur:
                cur.execute(
                    "UPDATE documents SET status='indexed', chunk_count=0 WHERE id=%s",
                    (doc_id,))
            pg.commit()
        logger.info("[task:%s] No chunks generated for doc_id=%s", self.request.id, doc_id)
        return

    # 5. 嵌入
    vectors   = _embed_texts([c["content"] for c in raw_chunks],
                              s.OLLAMA_EMBED_MODEL, s.OLLAMA_BASE_URL)
    chunk_ids = [str(uuid.uuid4()) for _ in raw_chunks]

    # 6-9. Saga 三庫寫入
    from services.saga import SagaLog
    saga = SagaLog("ingest_document", doc_id)
    saga.begin()

    qdrant_ids = [str(uuid.uuid4()) for _ in raw_chunks]

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
                    "title":       title,
                },
            )
            for qid, vec, c in zip(qdrant_ids, vectors, raw_chunks)
        ]
        qdrant.upsert(collection_name=s.QDRANT_COLLECTION, points=points)
        saga.record_step("qdrant")

        # ── LLM 分析 ────────────────────────────────────────
        sample = " ".join(c["content"] for c in raw_chunks[:10])[:3000]
        analysis = _llm_extract(sample, s.OLLAMA_LLM_MODEL, s.OLLAMA_BASE_URL)

        # ── Neo4j ────────────────────────────────────────────
        neo_driver = _neo4j()
        with neo_driver.session(database="neo4j") as neo_sess:
            neo_sess.run(
                "MERGE (d:Document {id:$doc_id}) "
                "SET d.title=$title, d.tags=$tags, d.summary=$summary",
                doc_id=doc_id,
                title=title,
                tags=analysis.get("tags", []),
                summary=analysis.get("summary", ""),
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
            "[task:%s] Indexed doc_id=%s: %d chunks",
            self.request.id, doc_id, len(raw_chunks)
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
            "[task:%s] Ingestion failed for doc_id=%s: %s",
            self.request.id, doc_id, exc, exc_info=True
        )
        raise
