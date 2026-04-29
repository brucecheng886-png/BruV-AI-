"""
Model runtime resolver — 第一原則：API Key 與 model 綁定，不與 provider 綁定

供 chat / documents / wiki / agent 等模組統一查詢「model + key + base_url」。
配合 `first-principles-api-key` skill §三 標準流程。

主要 API：
- `resolve_model_runtime(db, model_name, fallback_provider) -> dict`
  回傳 {model_id, provider, base_url, api_key}（皆可能為 None）
- `apply_model_runtime(runtime_config, model_runtime) -> dict`
  把 model-level 結果合併進 system_settings fallback config
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import LLMModel
from utils.crypto import decrypt_secret

logger = logging.getLogger(__name__)


def detect_provider_from_model(model_name: str) -> Optional[str]:
    """根據模型名稱推測 provider；無法判斷時回傳 None。
    與 chat.py 既有邏輯保持一致。"""
    if not model_name:
        return None
    m = model_name.lower()
    if "claude" in m:
        return "anthropic"
    if "gpt" in m or m.startswith("o1") or m.startswith("o3"):
        return "openai"
    if "gemini" in m:
        return "gemini"
    return None


async def resolve_model_runtime(
    db: AsyncSession,
    model_name: Optional[str],
    fallback_provider: Optional[str] = None,
) -> dict:
    """
    依照 first-principles §三 查詢 model-level 設定。

    回傳：
        {
          "model_id":  str | None,
          "provider":  str | None,
          "base_url":  str | None,
          "api_key":   str | None,   # 已解密
        }

    所有欄位皆可能為 None；呼叫端需自行決定 fallback。
    """
    if not model_name:
        return {"model_id": None, "provider": None, "base_url": None, "api_key": None}

    # 第一性原則：model name 是事實來源；偵測優先於 fallback。
    # 偵測不出時才用 fallback_provider；都沒有就不過濾 provider。
    detected = detect_provider_from_model(model_name)
    provider = detected or fallback_provider

    # 先以 (name + 偵測到的 provider) 查；查不到時退回「僅 by name」避免靜默走錯路徑
    async def _query(filter_provider: Optional[str]):
        stmt = select(LLMModel).where(LLMModel.name == model_name)
        if filter_provider:
            stmt = stmt.where(LLMModel.provider == filter_provider)
        return (await db.execute(stmt.limit(1))).scalar_one_or_none()

    try:
        m = await _query(provider) if provider else None
        if m is None:
            m = await _query(None)
    except Exception as e:
        logger.warning("resolve_model_runtime: 查詢失敗 model=%s provider=%s: %s",
                       model_name, provider, e)
        m = None

    if not m:
        # 找不到 model：若偵測或 fallback 指向雲端 provider，必須拒絕（否則會打到無效端點）
        _CLOUD_PROVIDERS_OUT = {"openai", "anthropic", "gemini", "azure", "openrouter"}
        if (provider or "").lower() in _CLOUD_PROVIDERS_OUT:
            raise ValueError(
                f"模型 {model_name} 未在系統登錄，無法解析 API Key 與端點，請至設定頁新增"
            )
        return {"model_id": None, "provider": provider, "base_url": None, "api_key": None}

    api_key: Optional[str] = None
    if getattr(m, "api_key", None):
        try:
            api_key = decrypt_secret(m.api_key)
        except Exception as e:
            logger.warning("resolve_model_runtime: 解密失敗 model=%s: %s", model_name, e)

    effective_provider = (m.provider or provider or "").lower()
    # 嚴格模式：雲端 provider 必須有 api_key，否則拒絕送出注定失敗的請求
    _CLOUD_PROVIDERS = {"openai", "anthropic", "gemini", "azure", "openrouter"}
    if effective_provider in _CLOUD_PROVIDERS and not (api_key and api_key.strip()):
        raise ValueError(
            f"模型 {model_name} 缺少 API Key，請至設定頁補齊"
        )

    return {
        "model_id": m.id,
        "provider": m.provider or provider,
        "base_url": m.base_url,
        "api_key":  api_key,
    }


def apply_model_runtime(runtime_config: dict, model_runtime: dict) -> dict:
    """
    將 resolve_model_runtime 的結果合併進 runtime_config。
    model-level 的非 None 欄位優先；None 則保留 fallback。
    """
    merged = dict(runtime_config or {})
    for k in ("provider", "base_url", "api_key", "model_id"):
        v = model_runtime.get(k)
        if v is not None:
            merged[k] = v
    return merged
