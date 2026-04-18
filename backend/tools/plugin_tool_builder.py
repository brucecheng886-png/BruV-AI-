"""
Plugin Tool Builder — 從 DB 動態生成 LangChain Tools

agent.py 在每次 task 啟動時呼叫 build_plugin_tools_sync()，
它從 PostgreSQL 讀取所有已啟用的插件，依 plugin_type 分別建立：
  - builtin: 直接呼叫 plugins.registry.dispatch()
  - webhook: HTTP POST 到 plugin.endpoint
"""
import asyncio
import json
import logging
from typing import List

import httpx
from langchain.tools import Tool

from config import settings
from utils.crypto import decrypt_secret

logger = logging.getLogger(__name__)


def build_plugin_tools_sync(session_factory) -> List[Tool]:
    """同步包裝器，在 agent 執行緒中呼叫"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_build_async(session_factory))
    except Exception as e:
        logger.error("build_plugin_tools_sync 失敗: %s", e)
        return []
    finally:
        loop.close()


async def _build_async(session_factory) -> List[Tool]:
    from sqlalchemy import select
    from models import Plugin

    tools: List[Tool] = []
    try:
        async with session_factory() as db:
            result = await db.execute(select(Plugin).where(Plugin.enabled == True))
            plugins = result.scalars().all()
    except Exception as e:
        logger.error("載入插件列表失敗: %s", e)
        return tools

    for plugin in plugins:
        try:
            tool = _make_tool(plugin)
            if tool:
                tools.append(tool)
        except Exception as e:
            logger.warning("插件 '%s' 工具建立失敗: %s", plugin.name, e)

    if tools:
        logger.info("載入 %d 個插件工具: %s", len(tools), [t.name for t in tools])
    return tools


def _make_tool(plugin) -> Tool | None:
    ptype      = getattr(plugin, "plugin_type", "webhook") or "webhook"
    builtin_key = getattr(plugin, "builtin_key", None)
    raw_config  = getattr(plugin, "plugin_config", {}) or {}
    # auth_header 解密後注入 config（供 notion_token 等使用）
    if plugin.auth_header:
        try:
            raw_config = {**raw_config, "_auth": decrypt_secret(plugin.auth_header)}
            # notion_token 使用 _auth
            if builtin_key == "notion" and "notion_token" not in raw_config:
                raw_config["notion_token"] = raw_config["_auth"]
        except Exception:
            pass

    # 工具名稱：去除空格 + 特殊字元，只保留 a-z0-9_
    import re
    safe_name = re.sub(r"[^a-z0-9_]", "_", f"plugin_{plugin.name}".lower())[:60]

    if ptype == "builtin" and builtin_key:
        return _builtin_tool(safe_name, plugin, builtin_key, raw_config)
    elif ptype == "webhook":
        return _webhook_tool(safe_name, plugin)
    return None


# ── builtin tool ─────────────────────────────────────────────────────────────

def _builtin_tool(name: str, plugin, builtin_key: str, config: dict) -> Tool:
    def invoke(input_str: str) -> str:
        try:
            params = json.loads(input_str) if input_str.strip().startswith("{") else {"query": input_str}
        except json.JSONDecodeError:
            params = {"query": input_str}

        action = params.pop("action", builtin_key)

        loop = asyncio.new_event_loop()
        try:
            from plugins.registry import dispatch
            result = loop.run_until_complete(dispatch(builtin_key, action, params, config))
        finally:
            loop.close()

        if result.get("success"):
            data = result.get("data", "")
            if isinstance(data, (dict, list)):
                return json.dumps(data, ensure_ascii=False, indent=2)
            return str(data)
        return f"[插件錯誤] {result.get('error', '未知錯誤')}"

    return Tool(
        name=name,
        func=invoke,
        description=(plugin.description or f"內建插件: {plugin.name}") + f"（builtin:{builtin_key}）",
    )


# ── webhook tool ──────────────────────────────────────────────────────────────

def _webhook_tool(name: str, plugin) -> Tool:
    endpoint     = plugin.endpoint or ""
    auth_enc     = plugin.auth_header

    def invoke(input_str: str) -> str:
        try:
            payload = json.loads(input_str) if input_str.strip().startswith("{") else {"query": input_str}
        except json.JSONDecodeError:
            payload = {"query": input_str}

        headers = {"Content-Type": "application/json"}
        if auth_enc:
            try:
                headers["Authorization"] = decrypt_secret(auth_enc)
            except Exception:
                pass

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.text[:3000]
        except Exception as e:
            return f"[Webhook 錯誤] {e}"

    return Tool(
        name=name,
        func=invoke,
        description=(plugin.description or f"Webhook 插件: {plugin.name}"),
    )
