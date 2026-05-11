"""
Notion 同步 Celery 任務

流程：
  從 DB 取 plugin → Fernet 解密 notion_token
  → list_database（Notion API）
  → 比對 notion_sync_log.last_edited_time
  → 只處理新增/修改頁面（SentenceWindow 分塊）
  → Saga 三庫寫入（PG → Qdrant → Neo4j）
  → UPSERT notion_sync_log

使用 psycopg2 直接操作（與 crawl_tasks.py 風格一致）。
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
import psycopg2
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

NOTION_API = "https://api.notion.com/v1"


# ── 連線工廠 ───────────────────────────────────────────────────

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
    from qdrant_client import QdrantClient
    s = _settings()
    return QdrantClient(host=s.QDRANT_HOST, port=s.QDRANT_PORT, api_key=s.QDRANT_API_KEY or None, https=False)


def _neo4j():
    from neo4j import GraphDatabase
    s = _settings()
    return GraphDatabase.driver(s.NEO4J_URI, auth=(s.NEO4J_USER, s.NEO4J_PASSWORD))


# ── Notion API 呼叫（同步 httpx）─────────────────────────────

def _list_database_sync(database_id: str, token: str) -> list[dict]:
    """取得 Notion 資料庫所有頁面（cursor-based，同步）"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    pages  = []
    cursor = None
    with httpx.Client(timeout=30) as client:
        while True:
            body: dict = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            resp = client.post(
                f"{NOTION_API}/databases/{database_id}/query",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

            for page in data.get("results", []):
                title = ""
                props_parts = []
                props_raw   = {}
                for prop_name, prop_val in page.get("properties", {}).items():
                    ptype    = prop_val.get("type", "")
                    text_val = ""
                    if ptype == "title":
                        text_val = "".join(t.get("plain_text", "") for t in prop_val.get("title", []))
                        title    = text_val
                    elif ptype == "rich_text":
                        text_val = "".join(t.get("plain_text", "") for t in prop_val.get("rich_text", []))
                    elif ptype == "select":
                        sel = prop_val.get("select") or {}
                        text_val = sel.get("name", "")
                    elif ptype == "multi_select":
                        text_val = ", ".join(s.get("name", "") for s in prop_val.get("multi_select", []))
                    elif ptype == "date":
                        date_data = prop_val.get("date") or {}
                        text_val  = date_data.get("start", "")
                    elif ptype == "number":
                        num = prop_val.get("number")
                        text_val = str(num) if num is not None else ""
                    elif ptype == "checkbox":
                        text_val = "是" if prop_val.get("checkbox") else "否"
                    elif ptype in ("url", "email", "phone_number"):
                        text_val = prop_val.get(ptype, "") or ""
                    if text_val:
                        props_parts.append(f"{prop_name}: {text_val}")
                        props_raw[prop_name] = text_val

                pages.append({
                    "page_id":          page.get("id", ""),
                    "title":            title or page.get("id", ""),
                    "last_edited_time": page.get("last_edited_time", ""),
                    "url":              page.get("url", ""),
                    "content_text":     "\n".join(props_parts),
                    "properties":       props_raw,
                })
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
    return pages


# ── 主任務 ────────────────────────────────────────────────────

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
    name="tasks.sync_notion_database_task",
)
def sync_notion_database_task(self, database_id: str, plugin_id: str):
    """
    增量同步 Notion 資料庫至本地知識庫。

    已同步且 last_edited_time 未變的頁面直接跳過。
    新增/修改頁面走完整 Saga 三庫寫入（PG → Qdrant → Neo4j）。
    """
    from tasks.crawl_tasks import (
        _sentence_window_chunks,
        _embed_texts,
        _llm_extract,
    )
    from qdrant_client.models import PointStruct
    from services.saga import SagaLog

    s = _settings()

    # 1. 從 DB 取得 plugin，解密 notion_token
    with _pg_conn() as pg:
        with pg.cursor() as cur:
            cur.execute(
                "SELECT auth_header, plugin_config FROM plugins WHERE id=%s::uuid",
                (plugin_id,),
            )
            row = cur.fetchone()
    if not row:
        raise ValueError(f"Plugin {plugin_id} 不存在")

    encrypted_token, plugin_config = row[0], row[1] or {}
    if not encrypted_token:
        raise ValueError(f"Plugin {plugin_id} 缺少 notion_token（auth_header 為空）")

    from utils.crypto import decrypt_secret
    notion_token  = decrypt_secret(encrypted_token)
    database_id   = database_id or plugin_config.get("database_id", "")
    if not database_id:
        raise ValueError("缺少 database_id")

    logger.info("[notion_sync] 開始同步 database_id=%s plugin_id=%s", database_id, plugin_id)

    # 2. 取得所有頁面
    pages = _list_database_sync(database_id, notion_token)
    logger.info("[notion_sync] Notion 頁面數: %d", len(pages))

    # 3. 讀取現有同步日誌
    with _pg_conn() as pg:
        with pg.cursor() as cur:
            cur.execute("SELECT page_id, last_edited_time FROM notion_sync_log")
            sync_log = {row[0]: row[1] for row in cur.fetchall()}

    processed = 0
    skipped   = 0

    for page in pages:
        page_id          = page["page_id"].replace("-", "")
        last_edited_raw  = page.get("last_edited_time", "")
        content_text     = page.get("content_text", "").strip()
        title            = page["title"]
        properties       = page.get("properties", {})

        if not content_text:
            skipped += 1
            continue

        # 解析 last_edited_time
        try:
            last_edited = datetime.fromisoformat(last_edited_raw.replace("Z", "+00:00"))
        except Exception:
            last_edited = datetime.now(tz=timezone.utc)

        # 比對：已同步且未修改 → 跳過
        existing_time = sync_log.get(page_id)
        if existing_time:
            # psycopg2 回傳的是 datetime（帶 tzinfo），需統一 tz
            if hasattr(existing_time, "tzinfo") and existing_time.tzinfo is None:
                existing_time = existing_time.replace(tzinfo=timezone.utc)
            if existing_time >= last_edited:
                skipped += 1
                continue

        # 4. SentenceWindow 分塊
        raw_chunks = _sentence_window_chunks(content_text)
        if not raw_chunks:
            skipped += 1
            continue

        doc_id      = str(uuid.uuid4())
        chunk_ids   = [str(uuid.uuid4()) for _ in raw_chunks]
        qdrant_ids  = [str(uuid.uuid4()) for _ in raw_chunks]

        # 5. 嵌入
        vectors = _embed_texts(
            [c["content"] for c in raw_chunks],
            s.OLLAMA_EMBED_MODEL,
            s.OLLAMA_BASE_URL,
        )

        # 6. LLM 分析
        sample   = " ".join(c["content"] for c in raw_chunks[:10])[:3000]
        analysis = _llm_extract(sample, s.OLLAMA_LLM_MODEL, s.OLLAMA_BASE_URL)

        # 7. Saga 三庫寫入（PG → Qdrant → Neo4j）
        saga = SagaLog("notion_sync", doc_id)
        saga.begin()

        try:
            # ── PG document + chunks（第一寫）──────────────────
            with _pg_conn() as pg:
                with pg.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO documents
                          (id, title, source, file_type, status, chunk_count, custom_fields)
                        VALUES (%s, %s, %s, 'notion', 'indexed', %s, %s)
                        """,
                        (doc_id, title[:500], page.get("url", ""), len(raw_chunks),
                         json.dumps(properties)),
                    )
                    for i, (c, qid, cid) in enumerate(zip(raw_chunks, qdrant_ids, chunk_ids)):
                        cur.execute(
                            """
                            INSERT INTO chunks
                              (id, doc_id, content, chunk_index, vector_id, window_context, page_number)
                            VALUES (%s, %s, %s, %s, %s, %s, 1)
                            """,
                            (cid, doc_id, c["content"], i, qid, c["window_context"]),
                        )
                pg.commit()
            saga.record_step("postgres")

            # ── Qdrant（第二寫）────────────────────────────────
            qdrant = _qdrant()
            points = [
                PointStruct(
                    id=qid,
                    vector=vec,
                    payload={
                        "doc_id":      doc_id,
                        "content":     c["content"],
                        "page_number": 1,
                        "title":       title,
                        "source_url":  page.get("url", ""),
                    },
                )
                for qid, vec, c in zip(qdrant_ids, vectors, raw_chunks)
            ]
            qdrant.upsert(collection_name=s.QDRANT_COLLECTION, points=points)
            saga.record_step("qdrant")

            # ── Neo4j（第三寫）─────────────────────────────────
            neo_driver = _neo4j()
            with neo_driver.session(database="neo4j") as neo_sess:
                neo_sess.run(
                    "MERGE (d:Document {id:$doc_id}) "
                    "SET d.title=$title, d.tags=$tags, d.summary=$summary, d.source='notion'",
                    doc_id=doc_id, title=title,
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

            saga.commit()

        except Exception as exc:
            saga.mark_compensated(error=str(exc))
            logger.error("[notion_sync] 頁面寫入失敗 page_id=%s: %s", page_id, exc, exc_info=True)
            continue

        # 8. 更新 notion_sync_log
        try:
            with _pg_conn() as pg:
                with pg.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO notion_sync_log (page_id, last_edited_time, doc_id, synced_at)
                        VALUES (%s, %s, %s::uuid, NOW())
                        ON CONFLICT (page_id) DO UPDATE
                          SET last_edited_time = EXCLUDED.last_edited_time,
                              doc_id           = EXCLUDED.doc_id,
                              synced_at        = NOW()
                        """,
                        (page_id, last_edited, doc_id),
                    )
                pg.commit()
        except Exception as log_err:
            logger.warning("[notion_sync] 更新 sync_log 失敗 page_id=%s: %s", page_id, log_err)

        processed += 1

    logger.info(
        "[notion_sync] 完成 database_id=%s: processed=%d skipped=%d total=%d",
        database_id, processed, skipped, len(pages),
    )
    return {"processed": processed, "skipped": skipped, "total": len(pages)}
