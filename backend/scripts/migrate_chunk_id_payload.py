"""
migrate_chunk_id_payload.py
──────────────────────────
補寫 Qdrant 向量點的 chunk_id payload 欄位。

背景：document_tasks.py 原先建立 PointStruct 時未將 PG chunk UUID (chunk_id)
寫入 Qdrant payload，導致 chat.py 的 fallback 改用 Qdrant point UUID，
使前端 openChunkModal 查 /chunks/{id} 時 404。

修正策略：
  1. 從 PostgreSQL chunks 表讀取所有 (id, vector_id) 映射
  2. 對每個有 vector_id 的 chunk，呼叫 qdrant.set_payload 補寫 chunk_id
  3. 分批 100 筆處理，回報進度
  4. 統計成功 / 失敗 / 略過 數量

執行方式：
  docker compose exec -T backend python scripts/migrate_chunk_id_payload.py
"""

import asyncio
import logging
import sys
import os

# 確保可 import app 模組
sys.path.insert(0, "/app")
os.chdir("/app")

import asyncpg
from qdrant_client.models import SetPayload

from config import settings
from database import get_qdrant_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 100


async def main() -> None:
    # ── 1. 從 PostgreSQL 取得所有 (id, vector_id) 映射 ──────────────
    logger.info("連線 PostgreSQL …")
    # DATABASE_URL 格式：postgresql+asyncpg://user:pass@host/db
    # asyncpg.connect 需要去掉 +asyncpg 前綴
    dsn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)

    rows = await conn.fetch(
        "SELECT id, vector_id FROM chunks WHERE vector_id IS NOT NULL"
    )
    await conn.close()

    total = len(rows)
    logger.info("共找到 %d 筆有 vector_id 的 chunk", total)

    if total == 0:
        logger.info("無需 migration，結束。")
        return

    # ── 2. 分批補寫 Qdrant payload ──────────────────────────────────
    qdrant = get_qdrant_client()
    collection = settings.QDRANT_COLLECTION

    success = 0
    failed = 0
    skipped = 0

    for batch_start in range(0, total, BATCH_SIZE):
        batch = rows[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

        logger.info(
            "處理批次 %d/%d（第 %d～%d 筆）…",
            batch_num,
            total_batches,
            batch_start + 1,
            min(batch_start + BATCH_SIZE, total),
        )

        for row in batch:
            pg_chunk_id = str(row["id"])
            qdrant_point_id = str(row["vector_id"])

            try:
                # 先確認該 point 是否存在（避免對不存在的 point set_payload）
                existing = await qdrant.retrieve(
                    collection_name=collection,
                    ids=[qdrant_point_id],
                    with_payload=True,
                )
                if not existing:
                    logger.warning(
                        "  Qdrant point %s 不存在，略過 chunk %s",
                        qdrant_point_id,
                        pg_chunk_id,
                    )
                    skipped += 1
                    continue

                # 若已有正確的 chunk_id，略過
                existing_chunk_id = existing[0].payload.get("chunk_id")
                if existing_chunk_id == pg_chunk_id:
                    skipped += 1
                    continue

                # set_payload 補寫 chunk_id
                await qdrant.set_payload(
                    collection_name=collection,
                    payload={"chunk_id": pg_chunk_id},
                    points=[qdrant_point_id],
                )
                success += 1

            except Exception as exc:
                logger.error(
                    "  補寫失敗 qdrant_id=%s chunk_id=%s: %s",
                    qdrant_point_id,
                    pg_chunk_id,
                    exc,
                )
                failed += 1

    # ── 3. 統計結果 ─────────────────────────────────────────────────
    logger.info("=" * 50)
    logger.info("Migration 完成")
    logger.info("  總計：%d 筆", total)
    logger.info("  成功：%d 筆", success)
    logger.info("  略過（已有或不存在）：%d 筆", skipped)
    logger.info("  失敗：%d 筆", failed)
    logger.info("=" * 50)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
