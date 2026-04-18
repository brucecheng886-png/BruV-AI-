"""
Playwright 爬蟲 HTTP 服務（內部 :3002）
提供 FastAPI backend 呼叫，不對外暴露
"""
import asyncio
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)
app = FastAPI(title="Playwright Service", docs_url=None, redoc_url=None)

# ── Schemas ──────────────────────────────────────────────────
class FetchRequest(BaseModel):
    url: str
    wait_for: Optional[str] = None      # CSS selector
    timeout_ms: int = 30_000


class FetchResponse(BaseModel):
    url: str
    text: str
    html: str
    status_code: int
    title: str


class ScreenshotRequest(BaseModel):
    url: str
    full_page: bool = True
    timeout_ms: int = 30_000


class ScreenshotResponse(BaseModel):
    path: str
    width: int
    height: int
    data_base64: str


# ── Routes ───────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "playwright-service"}


@app.post("/fetch", response_model=FetchResponse)
async def fetch_page(req: FetchRequest):
    """抓取網頁純文字與 HTML"""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            response = await page.goto(
                req.url,
                timeout=req.timeout_ms,
                wait_until="domcontentloaded",
            )
            if response is None:
                raise HTTPException(status_code=502, detail="No response from URL")

            if req.wait_for:
                await page.wait_for_selector(req.wait_for, timeout=req.timeout_ms)

            html = await page.content()
            text = await page.inner_text("body")
            title = await page.title()

            return FetchResponse(
                url=req.url,
                text=text.strip(),
                html=html,
                status_code=response.status,
                title=title,
            )
        except PlaywrightTimeout:
            raise HTTPException(status_code=504, detail=f"Timeout fetching {req.url}")
        except Exception as e:
            logger.error("Playwright fetch error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            await browser.close()


@app.post("/screenshot")
async def take_screenshot(req: ScreenshotRequest):
    """截圖並儲存至 /data/screenshots/，同時回傳 base64 資料供 backend 上傳 MinIO"""
    import os
    import time
    import base64

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(req.url, timeout=req.timeout_ms, wait_until="networkidle")

            os.makedirs("/data/screenshots", exist_ok=True)
            filename = f"/data/screenshots/{int(time.time())}.png"
            await page.screenshot(path=filename, full_page=req.full_page)

            with open(filename, "rb") as f:
                data_base64 = base64.b64encode(f.read()).decode()

            size = page.viewport_size or {"width": 1280, "height": 720}
            return {
                "path": filename,
                "width": size["width"],
                "height": size["height"],
                "data_base64": data_base64,
            }
        except PlaywrightTimeout:
            raise HTTPException(status_code=504, detail=f"Timeout fetching {req.url}")
        except Exception as e:
            logger.error("Playwright screenshot error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            await browser.close()
