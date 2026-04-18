"""
搜尋 Router — Playwright 爬蟲 + 截圖（Phase 3a）
"""
import base64
import logging
import uuid
from io import BytesIO
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

