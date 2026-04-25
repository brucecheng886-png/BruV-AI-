"""
LLM Client 統一適配層
支援: ollama | openai | groq | gemini | openrouter

用法:
    async for token in llm_stream(messages, settings):
        yield token
"""
import json
import logging
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

# OpenAI 格式基礎 URL
_PROVIDER_BASE_URLS = {
    "openai":     "https://api.openai.com/v1",
    "groq":       "https://api.groq.com/openai/v1",
    "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai",
    "openrouter": "https://openrouter.ai/api/v1",
}

# 各 provider 預設模型（CLOUD_LLM_MODEL 可覆蓋）
_DEFAULT_CLOUD_MODELS = {
    "openai":     "gpt-4o-mini",
    "groq":       "llama-3.3-70b-versatile",
    "gemini":     "gemini-2.0-flash",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
}


def _resolve_model(settings) -> str:
    """決定最終使用的模型名稱"""
    if settings.LLM_PROVIDER == "ollama":
        return settings.OLLAMA_LLM_MODEL
    return settings.CLOUD_LLM_MODEL or _DEFAULT_CLOUD_MODELS.get(settings.LLM_PROVIDER, "gpt-4o-mini")


def _resolve_api_key(settings) -> str:
    """取得對應 provider 的 API Key"""
    mapping = {
        "openai":     settings.OPENAI_API_KEY,
        "groq":       settings.GROQ_API_KEY,
        "gemini":     settings.GEMINI_API_KEY,
        "openrouter": settings.OPENROUTER_API_KEY,
    }
    return mapping.get(settings.LLM_PROVIDER, "")


async def llm_stream(
    messages: list[dict],
    settings,
    model_override: str | None = None,
    config_override: dict | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> AsyncIterator[str]:
    """
    統一串流介面，yield 每個 token 文字字串。
    config_override: {provider, model, api_key} 來自 DB 設定，優先於 env vars。
    """
    override = config_override or {}
    provider = override.get("provider") or settings.LLM_PROVIDER
    model    = model_override or override.get("model") or _resolve_model(settings)

    if provider == "ollama":
        async for token in _ollama_stream(messages, model, settings, temperature=temperature, max_tokens=max_tokens):
            yield token
    elif provider == "anthropic":
        api_key_override = override.get("api_key")
        async for token in _anthropic_stream(
            messages, model, settings,
            api_key_override=api_key_override,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield token
    else:
        api_key_override = override.get("api_key")
        async for token in _openai_compat_stream(
            messages, model, settings,
            provider_override=provider,
            api_key_override=api_key_override,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield token


# ── Ollama 串流 ───────────────────────────────────────────────────────────────

async def _ollama_stream(
    messages: list[dict],
    model: str,
    settings,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> AsyncIterator[str]:
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream(
            "POST",
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={"model": model, "messages": messages, "stream": True,
                  "options": {"temperature": temperature, "num_predict": max_tokens}},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
                if chunk.get("done"):
                    break


# ── OpenAI 相容格式串流（Groq / Gemini / OpenRouter / OpenAI）────────────────

async def _openai_compat_stream(
    messages: list[dict],
    model: str,
    settings,
    provider_override: str | None = None,
    api_key_override: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> AsyncIterator[str]:
    provider = provider_override or settings.LLM_PROVIDER
    base_url = _PROVIDER_BASE_URLS.get(provider, "")
    api_key  = api_key_override or _resolve_api_key(settings)

    if not base_url:
        logger.error("Unknown LLM_PROVIDER: %s", provider)
        yield "[錯誤：未知的 LLM_PROVIDER]"
        return
    if not api_key:
        logger.error("Missing API key for provider: %s", provider)
        yield f"[錯誤：請在設定頁輸入 {provider.upper()} API Key]"
        return

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    # OpenRouter 需要額外 headers
    if provider == "openrouter":
        headers["HTTP-Referer"] = "http://localhost"
        headers["X-Title"]      = "BruV AI KB"

    payload = {
        "model":       model,
        "messages":    messages,
        "stream":      True,
        "temperature": temperature,
        "max_tokens":  max_tokens,
    }

    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream(
            "POST",
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                token = (chunk.get("choices") or [{}])[0] \
                             .get("delta", {}).get("content", "")
                if token:
                    yield token


# ── Anthropic 串流（Messages API）────────────────────────────────────────────

async def _anthropic_stream(
    messages: list[dict],
    model: str,
    settings,
    api_key_override: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> AsyncIterator[str]:
    api_key = api_key_override or getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        yield "[錯誤：請在設定頁輸入 ANTHROPIC API Key]"
        return

    # Anthropic 不接受 system 角色在 messages 裡，需分離
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    user_messages = [m for m in messages if m["role"] != "system"]
    system_prompt = "\n\n".join(system_parts) if system_parts else None

    payload: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": user_messages,
        "stream": True,
        "temperature": temperature,
    }
    if system_prompt:
        payload["system"] = system_prompt

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                logger.error("Anthropic error %s: %s", resp.status_code, body[:200])
                yield f"[Anthropic 錯誤 {resp.status_code}]"
                return
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data:
                    continue
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                chunk_type = chunk.get("type", "")
                if chunk_type == "content_block_delta":
                    token = chunk.get("delta", {}).get("text", "")
                    if token:
                        yield token
                elif chunk_type == "message_stop":
                    break
