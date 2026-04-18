"""
Celery 應用程式設定
"""
from celery import Celery
from config import settings

# 確保 Saga SQLite 資料表存在
from services.saga import init_saga_db
init_saga_db()

celery_app = Celery(
    "ai_kb",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["tasks.document_tasks", "tasks.crawl_tasks", "tasks.webhook_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Taipei",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
