"""
migrate_qdrant_kb_id.py — 補寫舊 Qdrant points 的 kb_id payload

路徑：PG chunks.vector_id → chunks.doc_id → documents.knowledge_base_id
     → Qdrant set_payload(kb_id=...)

執行方式（在容器內）：
  docker exec bruv_ai_backend python scripts/migrate_qdrant_kb_id.py

乾跑（只顯示統計，不寫入）：
  docker exec bruv_ai_backend python scripts/migrate_qdrant_kb_id.py --dry-run
"""
import logging
import sys
from collections import defaultdict

import psycopg2
from qdrant_client import QdrantClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 100


def main(dry_run: bool = False):
    sys.path.insert(0, "/app")
    from config import settings  # noqa: PLC0415

    # 連接 PG，查詢所有需補寫的 (vector_id, knowledge_base_id) 配對
    pg = psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
    )
    try:
        logger.info("Querying PG for chunks with knowledge_base_id...")
        with pg.cursor() as cur:
            cur.execute(
                """
                SELECT c.vector_id, d.knowledge_base_id::text
                  FROM chunks c
                  JOIN documents d ON c.doc_id = d.id
                 WHERE c.vector_id IS NOT NULL
                   AND d.knowledge_base_id IS NOT NULL
                """
            )
            rows = cur.fetchall()
    finally:
        pg.close()

    logger.info("Found %d chunks eligible for kb_id migration", len(rows))
    if not rows:
        logger.info("Nothing to migrate. Exiting.")
        return

    # 依 kb_id 分組，減少 Qdrant API 呼叫次數
    kb_to_ids: dict[str, list[str]] = defaultdict(list)
    for vector_id, kb_id in rows:
        kb_to_ids[kb_id].append(vector_id)

    logger.info("Distinct knowledge_bases: %d", len(kb_to_ids))
    for kb_id, ids in kb_to_ids.items():
        logger.info("  KB %s → %d points", kb_id, len(ids))

    if dry_run:
        logger.info("[DRY-RUN] No changes written.")
        return

    # 連接 Qdrant，批次 set_payload
    qdrant = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    collection = settings.QDRANT_COLLECTION

    total_updated = 0
    for kb_id, vector_ids in kb_to_ids.items():
        logger.info("Updating KB %s (%d points)...", kb_id, len(vector_ids))
        for i in range(0, len(vector_ids), BATCH_SIZE):
            batch = vector_ids[i : i + BATCH_SIZE]
            qdrant.set_payload(
                collection_name=collection,
                payload={"kb_id": kb_id},
                points=batch,
            )
            total_updated += len(batch)

    logger.info("Migration complete. Total Qdrant points updated: %d", total_updated)


if __name__ == "__main__":
    _dry = "--dry-run" in sys.argv
    main(dry_run=_dry)
