"""
notion_sync_tool — LangChain Tool wrapper for Notion database sync.

Actions (JSON input):
  sync    → POST /api/plugins/notion/sync
  status  → GET  /api/plugins/notion/sync/{task_id}
"""
import json
import logging

import httpx
from langchain.tools import Tool

from config import settings

logger = logging.getLogger(__name__)

_BASE = f"http://localhost:{getattr(settings, 'PORT', 8000)}"


def _call(action: str, payload: dict) -> str:
    try:
        with httpx.Client(base_url=_BASE, timeout=30) as client:
            if action == "sync":
                plugin_id = payload.get("plugin_id")
                if not plugin_id:
                    return json.dumps({"error": "plugin_id 為必填（Notion 插件的 UUID）"})
                body = {
                    "plugin_id": plugin_id,
                    "database_id": payload.get("database_id"),
                }
                resp = client.post("/api/plugins/notion/sync", json=body)
                resp.raise_for_status()
                return json.dumps(resp.json(), ensure_ascii=False)

            elif action == "status":
                task_id = payload.get("task_id", "").strip()
                if not task_id:
                    return json.dumps({"error": "task_id 為必填"})
                resp = client.get(f"/api/plugins/notion/sync/{task_id}")
                resp.raise_for_status()
                return json.dumps(resp.json(), ensure_ascii=False)

            else:
                return json.dumps({"error": f"不支援的 action: {action}，可用：sync, status"})

    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"})
    except Exception as e:
        logger.error("notion_sync_tool error: %s", e, exc_info=True)
        return json.dumps({"error": str(e)})


def _run(raw_input: str) -> str:
    try:
        data = json.loads(raw_input)
    except json.JSONDecodeError:
        return json.dumps({"error": "輸入必須是 JSON 格式，例如: {\"action\":\"sync\",\"plugin_id\":\"xxxx\"}"})

    action = data.get("action", "sync")
    return _call(action, data)


def build_notion_sync_tool() -> Tool:
    return Tool(
        name="notion_sync",
        func=_run,
        description=(
            "同步 Notion 資料庫到知識庫（增量同步，僅處理有更新的頁面）。"
            "輸入：JSON 字串，包含 action 欄位（sync 或 status）。\n"
            "- sync：觸發同步，需填 plugin_id（Notion 插件的 UUID）、database_id（可選，若不填則用插件預設）。\n"
            "  範例：{\"action\":\"sync\",\"plugin_id\":\"xxxx-xxxx\",\"database_id\":\"yyyy-yyyy\"}\n"
            "- status：查詢同步進度，需填 task_id（Celery 任務 ID）。\n"
            "  範例：{\"action\":\"status\",\"task_id\":\"zzzz-zzzz\"}\n"
            "回傳：JSON，包含 task_id、status、synced、skipped 等欄位。"
        ),
    )
