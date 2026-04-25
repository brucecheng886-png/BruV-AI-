"""
搜尋 Router — Playwright 爬蟲 + 截圖（Phase 3a）+ 批量爬取（Phase B）
"""
import base64
import hashlib
import logging
import uuid
from io import BytesIO
from typing import List
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser
from config import settings
from database import get_db
from models import Document

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────

class CrawlRequest(BaseModel):
    url: str
    title: str | None = None


class CrawlResponse(BaseModel):
    doc_id: str
    status: str


class CrawlBatchRequest(BaseModel):
    urls: List[str]
    batch_name: str | None = None
    concurrency: int = 10


class CrawlBatchResponse(BaseModel):
    batch_id: str
    total: int
    deduplicated: int


class CrawlBatchStatus(BaseModel):
    batch_id: str
    batch_name: str | None
    total: int
    success: int
    failed: int
    pending: int
    status: str


class ScreenshotRequest(BaseModel):
    url: str
    full_page: bool = True


class ScreenshotResponse(BaseModel):
    minio_key: str
    url: str


# ── 工具函式 ─────────────────────────────────────────────────

def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="URL 必須以 http:// 或 https:// 開頭",
        )


# ── 端點 ─────────────────────────────────────────────────────

@router.post("/crawl", status_code=status.HTTP_202_ACCEPTED, response_model=CrawlResponse)
async def crawl_url(
    body: CrawlRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """提交 URL 爬蟲任務，非同步處理後寫入三庫"""
    _validate_url(body.url)

    doc_id = str(uuid.uuid4())
    title  = body.title or body.url

    doc = Document(
        id=doc_id,
        title=title,
        source=body.url,
        file_type="html",
        status="pending",
        created_by=current_user.id,
    )
    db.add(doc)
    await db.commit()

    from tasks.crawl_tasks import crawl_document
    crawl_document.delay(doc_id, body.url)

    logger.info("Crawl task queued: doc_id=%s url=%s", doc_id, body.url)
    return CrawlResponse(doc_id=doc_id, status="pending")


@router.post("/screenshot", response_model=ScreenshotResponse)
async def screenshot_url(
    body: ScreenshotRequest,
    current_user: CurrentUser,
):
    """截圖並儲存至 MinIO，回傳 minio_key"""
    _validate_url(body.url)

    # 1. 呼叫 playwright-service /screenshot
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.post(
                f"{settings.PLAYWRIGHT_SERVICE_URL}/screenshot",
                json={"url": body.url, "full_page": body.full_page, "timeout_ms": 30_000},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Playwright service error: {exc}",
            ) from exc

    data = resp.json()
    data_b64 = data.get("data_base64", "")
    if not data_b64:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Playwright service returned no image data",
        )

    # 2. 解碼並上傳至 MinIO
    img_bytes = base64.b64decode(data_b64)
    minio_key = f"screenshots/{uuid.uuid4()}.png"

    from minio import Minio
    mc = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,
    )
    if not mc.bucket_exists(settings.MINIO_BUCKET):
        mc.make_bucket(settings.MINIO_BUCKET)

    mc.put_object(
        settings.MINIO_BUCKET,
        minio_key,
        BytesIO(img_bytes),
        len(img_bytes),
        content_type="image/png",
    )

    logger.info("Screenshot uploaded: key=%s url=%s", minio_key, body.url)
    return ScreenshotResponse(minio_key=minio_key, url=body.url)


# ── 批量爬蟲端點（Phase B）──────────────────────────────────────

@router.post("/crawl-batch", status_code=status.HTTP_202_ACCEPTED, response_model=CrawlBatchResponse)
async def crawl_batch(
    body: CrawlBatchRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """批量提交 URL 爬蟲，同批次 SHA256 去重，回傳 batch_id（202 Accepted）"""
    if not body.urls:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="urls 不可為空")
    if len(body.urls) > 10000:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="一次最多提交 10000 筆 URL")

    # 請求內去重（同批次重複 URL 只留一筆）
    seen_fps: dict[str, str] = {}
    for url in body.urls:
        fp = hashlib.sha256(url.encode("utf-8")).hexdigest()
        seen_fps[fp] = url
    deduplicated = len(body.urls) - len(seen_fps)
    unique_urls  = list(seen_fps.values())

    # 建立批次記錄
    batch_id = str(uuid.uuid4())
    from sqlalchemy import text
    await db.execute(
        text(
            "INSERT INTO crawl_batches (id, batch_name, total, status) "
            "VALUES (:id, :name, 0, 'queued')"
        ),
        {"id": batch_id, "name": body.batch_name or f"batch-{batch_id[:8]}"},
    )
    await db.commit()

    # 提交 Celery 批量任務
    from tasks.crawl_tasks import crawl_batch_task
    crawl_batch_task.delay(batch_id, unique_urls, current_user.id)

    logger.info("Crawl batch queued: batch_id=%s total=%d deduplicated=%d",
                batch_id, len(unique_urls), deduplicated)
    return CrawlBatchResponse(batch_id=batch_id, total=len(unique_urls), deduplicated=deduplicated)


@router.get("/crawl-batch/{batch_id}/status", response_model=CrawlBatchStatus)
async def crawl_batch_status(
    batch_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """查詢批量爬蟲進度（從 PostgreSQL 聚合，持久化）"""
    from sqlalchemy import text
    row = await db.execute(
        text("""
            SELECT
                cb.id,
                cb.batch_name,
                cb.total,
                cb.status,
                COUNT(CASE WHEN d.status = 'indexed' THEN 1 END)   AS success,
                COUNT(CASE WHEN d.status = 'failed'  THEN 1 END)   AS failed,
                COUNT(CASE WHEN d.status IN ('pending','processing') THEN 1 END) AS pending
            FROM crawl_batches cb
            LEFT JOIN documents d ON d.batch_id = cb.id::uuid
            WHERE cb.id = :batch_id
            GROUP BY cb.id, cb.batch_name, cb.total, cb.status
        """),
        {"batch_id": batch_id},
    )
    result = row.fetchone()
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="批次 ID 不存在")

    bid, bname, total, bstatus, success, failed, pending = result

    # 所有任務完成時自動更新狀態
    if bstatus == "running" and (success + failed) >= total > 0:
        await db.execute(
            text("UPDATE crawl_batches SET status='done' WHERE id=:id"),
            {"id": batch_id},
        )
        await db.commit()
        bstatus = "done"

    return CrawlBatchStatus(
        batch_id=str(bid),
        batch_name=bname,
        total=total or 0,
        success=success or 0,
        failed=failed or 0,
        pending=pending or 0,
        status=bstatus,
    )

