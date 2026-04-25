"""
bulk_crawl_tool — LangChain Tool wrapper for batch URL crawling.

Actions (JSON input):
  submit  → POST /api/search/crawl-batch
  status  → GET  /api/search/crawl-batch/{batch_id}/status
"""
import json
import logging

import httpx
from langchain.tools import Tool

from config import settings

logger = logging.getLogger(__name__)

_BASE = f"http://localhost:{getattr(settings, 'PORT', 8000)}"


def _call(action: str, payload: dict) -> str:
    """Execute bulk crawl action and return JSON string result."""
    try:
        with httpx.Client(base_url=_BASE, timeout=30) as client:
            if action == "submit":
                urls = payload.get("urls", [])
                if not urls:
                    return json.dumps({"error": "urls 欄位為必填且不得為空"})
                body = {
                    "urls": urls,
                    "batch_name": payload.get("batch_name", ""),
                    "concurrency": int(payload.get("concurrency", 5)),
                }
                resp = client.post("/api/search/crawl-batch", json=body)
                resp.raise_for_status()
                return json.dumps(resp.json(), ensure_ascii=False)

            elif action == "status":
                batch_id = payload.get("batch_id", "").strip()
                if not batch_id:
                    return json.dumps({"error": "batch_id 為必填"})
                resp = client.get(f"/api/search/crawl-batch/{batch_id}/status")
                resp.raise_for_status()
                return json.dumps(resp.json(), ensure_ascii=False)

            else:
                return json.dumps({"error": f"不支援的 action: {action}，可用：submit, status"})

    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"})
    except Exception as e:
        logger.error("bulk_crawl_tool error: %s", e, exc_info=True)
        return json.dumps({"error": str(e)})


def _run(raw_input: str) -> str:
    """LangChain Tool entry point. Expects JSON string."""
    try:
        data = json.loads(raw_input)
    except json.JSONDecodeError:
        return json.dumps({"error": "輸入必須是 JSON 格式，例如: {\"action\":\"submit\",\"urls\":[...]}"})

    action = data.get("action", "submit")
    return _call(action, data)


def build_bulk_crawl_tool() -> Tool:
    return Tool(
        name="bulk_crawl",
        func=_run,
        description=(
            "批量爬取多個 URL 並存入知識庫。"
            "輸入：JSON 字串，包含 action 欄位（submit 或 status）。\n"
            "- submit：提交批次，需填 urls（陣列）、batch_name（可選）、concurrency（可選，預設 5）。\n"
            "  範例：{\"action\":\"submit\",\"urls\":[\"https://example.com/a\",\"https://example.com/b\"],\"batch_name\":\"my_batch\"}\n"
            "- status：查詢批次進度，需填 batch_id（UUID）。\n"
            "  範例：{\"action\":\"status\",\"batch_id\":\"xxxx-xxxx-...\"}\n"
            "回傳：JSON，包含 batch_id、total、pending、running、done、failed 等欄位。"
        ),
    )
