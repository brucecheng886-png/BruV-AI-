"""
Saga 補償日誌（SQLite，必要元件）
確保跨資料庫操作的最終一致性
"""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

SAGA_DB_PATH = Path("/data/saga.db")


def init_saga_db():
    """初始化 SQLite saga 資料表"""
    SAGA_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SAGA_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS saga_log (
                id              TEXT PRIMARY KEY,
                operation       TEXT NOT NULL,
                resource_id     TEXT NOT NULL,
                completed_steps TEXT NOT NULL DEFAULT '[]',
                status          TEXT NOT NULL DEFAULT 'in_progress',
                error_detail    TEXT,
                started_at      TEXT NOT NULL,
                finished_at     TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON saga_log(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_resource ON saga_log(resource_id)")
        conn.commit()
    logger.info("Saga DB initialized at %s", SAGA_DB_PATH)


class SagaLog:
    def __init__(self, operation: str, resource_id: str):
        import uuid
        self.id = str(uuid.uuid4())
        self.operation = operation
        self.resource_id = resource_id
        self.completed_steps: List[str] = []

    def begin(self):
        with sqlite3.connect(SAGA_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO saga_log (id, operation, resource_id, status, started_at) VALUES (?,?,?,?,?)",
                (self.id, self.operation, self.resource_id,
                 "in_progress", datetime.utcnow().isoformat()),
            )
            conn.commit()
        logger.debug("Saga %s started: %s/%s", self.id, self.operation, self.resource_id)

    def record_step(self, step: str):
        self.completed_steps.append(step)
        with sqlite3.connect(SAGA_DB_PATH) as conn:
            conn.execute(
                "UPDATE saga_log SET completed_steps=? WHERE id=?",
                (json.dumps(self.completed_steps), self.id),
            )
            conn.commit()

    def commit(self):
        with sqlite3.connect(SAGA_DB_PATH) as conn:
            conn.execute(
                "UPDATE saga_log SET status='committed', finished_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), self.id),
            )
            conn.commit()
        logger.debug("Saga %s committed", self.id)

    def compensate(self, compensation_fns: dict):
        """按逆序執行補償函式
        compensation_fns: {"step_name": async_fn, ...}
        """
        for step in reversed(self.completed_steps):
            fn = compensation_fns.get(step)
            if fn:
                try:
                    import asyncio
                    asyncio.get_event_loop().run_until_complete(fn())
                    logger.info("Saga %s: compensated step %s", self.id, step)
                except Exception as e:
                    logger.error(
                        "Saga %s: compensation failed for step %s: %s",
                        self.id, step, e, exc_info=True,
                    )

    def mark_compensated(self, error: str = ""):
        with sqlite3.connect(SAGA_DB_PATH) as conn:
            conn.execute(
                "UPDATE saga_log SET status='compensated', error_detail=?, finished_at=? WHERE id=?",
                (error, datetime.utcnow().isoformat(), self.id),
            )
            conn.commit()
        logger.warning("Saga %s compensated. Error: %s", self.id, error)


@contextmanager
def saga_transaction(operation: str, resource_id: str, compensation_fns: dict = None):
    """
    使用範例：
        with saga_transaction("ingest_document", doc_id, compensations) as saga:
            await write_to_postgres()
            saga.record_step("postgres")
            await write_to_qdrant()
            saga.record_step("qdrant")
    """
    saga = SagaLog(operation=operation, resource_id=resource_id)
    saga.begin()
    try:
        yield saga
        saga.commit()
    except Exception as exc:
        error_msg = str(exc)
        logger.error("Saga transaction failed: %s", error_msg, exc_info=True)
        if compensation_fns:
            saga.compensate(compensation_fns)
        saga.mark_compensated(error=error_msg)
        raise RuntimeError(f"Transaction rolled back: {error_msg}") from exc
