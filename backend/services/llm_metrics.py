"""
Phase B2: LLM 呼叫監測層
- track_llm_call(): async context manager，包住 LLM 呼叫，自動記錄 token / 延遲 / 錯誤
- prometheus 指標: llm_calls_total / llm_latency_seconds / llm_tokens_total / llm_cost_usd_total
- 非阻塞 DB insert（失敗時只 log warning，不影響主流程）
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable

from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal
from models import LLMUsageLog

logger = logging.getLogger(__name__)


# ── Prometheus 指標 ────────────────────────────────────────────
LLM_CALLS_TOTAL = Counter(
    "llm_calls_total",
    "Total number of LLM calls",
    ["provider", "model", "call_type", "success"],
)
LLM_LATENCY_SECONDS = Histogram(
    "llm_latency_seconds",
    "LLM call latency in seconds",
    ["provider", "model", "call_type"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)
LLM_TOKENS_TOTAL = Counter(
    "llm_tokens_total",
    "Total tokens consumed",
    ["provider", "model", "type"],  # type=prompt|completion
)
LLM_COST_USD_TOTAL = Counter(
    "llm_cost_usd_total",
    "Estimated total cost in USD",
    ["provider", "model"],
)


# ── 成本估算 ────────────────────────────────────────────────────
def estimate_cost_usd(model_name: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    """依 settings.LLM_COST_TABLE 估算成本（USD）。模型未列入時回傳 None。"""
    if not model_name:
        return None
    table = getattr(settings, "LLM_COST_TABLE", {}) or {}
    entry = table.get(model_name)
    if not entry:
        # 嘗試前綴匹配（例如 claude-3-5-sonnet-20241022 → claude-3-5-sonnet-*）
        for k, v in table.items():
            if model_name.startswith(k):
                entry = v
                break
    if not entry:
        return None
    inp = float(entry.get("input", 0.0))
    out = float(entry.get("output", 0.0))
    return round((prompt_tokens / 1_000_000.0) * inp + (completion_tokens / 1_000_000.0) * out, 6)


# ── 非阻塞 DB insert ──────────────────────────────────────────
async def _persist_log(record: dict) -> None:
    """非阻塞地寫入 llm_usage_log。失敗只 log warning。"""
    try:
        async with AsyncSessionLocal() as db:
            entry = LLMUsageLog(**record)
            db.add(entry)
            await db.commit()
    except Exception as e:
        logger.warning("llm_usage_log insert failed: %s", e)


# ── 主 context manager ────────────────────────────────────────
@asynccontextmanager
async def track_llm_call(
    *,
    model: str,
    provider: str,
    call_type: str,
    user_id: str | None = None,
    conv_id: str | None = None,
    agent_task_id: str | None = None,
    template_id: str | None = None,
) -> AsyncIterator[Callable[[dict], None]]:
    """
    包住一次 LLM 呼叫，自動記錄使用量、延遲、成功/失敗。

    用法：
        async with track_llm_call(model=..., provider=..., call_type="chat") as on_usage:
            async for token in llm_stream(..., usage_callback=on_usage):
                ...
        # context exit 時自動寫入 DB + 更新 prometheus 指標

    on_usage(usage_dict): 由底層 llm_client 在收到最終 usage 時呼叫。
        usage_dict = {"prompt_tokens": int, "completion_tokens": int}
    """
    captured: dict = {"prompt_tokens": 0, "completion_tokens": 0}

    def on_usage(usage: dict) -> None:
        if not isinstance(usage, dict):
            return
        try:
            captured["prompt_tokens"] = int(usage.get("prompt_tokens") or 0)
            captured["completion_tokens"] = int(usage.get("completion_tokens") or 0)
        except (TypeError, ValueError):
            pass

    start = time.perf_counter()
    success = True
    error_message: str | None = None

    try:
        yield on_usage
    except Exception as e:
        success = False
        error_message = str(e)[:500]
        raise
    finally:
        latency_s = time.perf_counter() - start
        latency_ms = int(latency_s * 1000)
        prompt_tokens = captured["prompt_tokens"]
        completion_tokens = captured["completion_tokens"]
        total_tokens = prompt_tokens + completion_tokens
        cost = estimate_cost_usd(model, prompt_tokens, completion_tokens)

        # Prometheus 指標
        try:
            LLM_CALLS_TOTAL.labels(
                provider=provider or "unknown",
                model=model or "unknown",
                call_type=call_type,
                success=str(success).lower(),
            ).inc()
            LLM_LATENCY_SECONDS.labels(
                provider=provider or "unknown",
                model=model or "unknown",
                call_type=call_type,
            ).observe(latency_s)
            if prompt_tokens > 0:
                LLM_TOKENS_TOTAL.labels(
                    provider=provider or "unknown",
                    model=model or "unknown",
                    type="prompt",
                ).inc(prompt_tokens)
            if completion_tokens > 0:
                LLM_TOKENS_TOTAL.labels(
                    provider=provider or "unknown",
                    model=model or "unknown",
                    type="completion",
                ).inc(completion_tokens)
            if cost and cost > 0:
                LLM_COST_USD_TOTAL.labels(
                    provider=provider or "unknown",
                    model=model or "unknown",
                ).inc(cost)
        except Exception as e:
            logger.warning("prometheus metric update failed: %s", e)

        # DB insert（背景任務，不阻塞主流程）
        record = {
            "conv_id": conv_id,
            "agent_task_id": agent_task_id,
            "user_id": user_id,
            "model_name": (model or "unknown")[:128],
            "provider": (provider or "unknown")[:32],
            "call_type": call_type[:32],
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
            "cost_usd": cost,
            "success": success,
            "error_message": error_message,
            "template_id": template_id,
        }
        try:
            asyncio.create_task(_persist_log(record))
        except RuntimeError:
            # 沒有 running loop 時退回同步寫入
            await _persist_log(record)
