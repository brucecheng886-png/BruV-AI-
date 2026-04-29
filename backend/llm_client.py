"""
LLM Client 統一適配層
支援: ollama | openai | groq | gemini | openrouter

用法:
    async for token in llm_stream(messages, settings):
        yield token
"""
import json
import logging
from typing import AsyncIterator, Callable

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
    usage_callback: Callable[[dict], None] | None = None,
) -> AsyncIterator[str]:
    """
    統一串流介面，yield 每個 token 文字字串。
    config_override: {provider, model, api_key} 來自 DB 設定，優先於 env vars。
    usage_callback: 串流結束時被呼叫一次，傳入 {prompt_tokens, completion_tokens}（Phase B2 監測層用）。
    """
    override = config_override or {}
    provider = override.get("provider") or settings.LLM_PROVIDER
    model    = model_override or override.get("model") or _resolve_model(settings)

    if provider == "ollama":
        async for token in _ollama_stream(
            messages, model, settings,
            temperature=temperature, max_tokens=max_tokens,
            usage_callback=usage_callback,
        ):
            yield token
    elif provider == "anthropic":
        api_key_override = override.get("api_key")
        async for token in _anthropic_stream(
            messages, model, settings,
            api_key_override=api_key_override,
            temperature=temperature,
            max_tokens=max_tokens,
            usage_callback=usage_callback,
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
            usage_callback=usage_callback,
        ):
            yield token


# ── Ollama 串流 ───────────────────────────────────────────────────────────────

async def _ollama_stream(
    messages: list[dict],
    model: str,
    settings,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    usage_callback: Callable[[dict], None] | None = None,
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
                    if usage_callback:
                        try:
                            usage_callback({
                                "prompt_tokens": int(chunk.get("prompt_eval_count") or 0),
                                "completion_tokens": int(chunk.get("eval_count") or 0),
                            })
                        except Exception as _e:
                            logger.debug("ollama usage_callback failed: %s", _e)
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
    usage_callback: Callable[[dict], None] | None = None,
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
    # 要求 OpenAI 相容端在最後一個 chunk 附帶 usage（Groq / OpenRouter / Gemini 多數已支援）
    if usage_callback:
        payload["stream_options"] = {"include_usage": True}

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
                # 帶 usage 的 chunk 可能 choices 為空陣列
                usage = chunk.get("usage")
                if usage and usage_callback:
                    try:
                        usage_callback({
                            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                            "completion_tokens": int(usage.get("completion_tokens") or 0),
                        })
                    except Exception as _e:
                        logger.debug("openai usage_callback failed: %s", _e)
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
    usage_callback: Callable[[dict], None] | None = None,
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
            anthro_prompt_tokens = 0
            anthro_completion_tokens = 0
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
                if chunk_type == "message_start":
                    _u = (chunk.get("message") or {}).get("usage") or {}
                    anthro_prompt_tokens = int(_u.get("input_tokens") or 0)
                    anthro_completion_tokens = int(_u.get("output_tokens") or 0)
                elif chunk_type == "content_block_delta":
                    token = chunk.get("delta", {}).get("text", "")
                    if token:
                        yield token
                elif chunk_type == "message_delta":
                    _u = chunk.get("usage") or {}
                    if _u.get("output_tokens") is not None:
                        anthro_completion_tokens = int(_u.get("output_tokens") or 0)
                elif chunk_type == "message_stop":
                    break
            if usage_callback:
                try:
                    usage_callback({
                        "prompt_tokens": anthro_prompt_tokens,
                        "completion_tokens": anthro_completion_tokens,
                    })
                except Exception as _e:
                    logger.debug("anthropic usage_callback failed: %s", _e)


# ── 非串流單次呼叫 ────────────────────────────────────────────────────────────

async def llm_complete(
    messages: list[dict],
    settings,
    model_override: str | None = None,
    config_override: dict | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    """
    非串流單次呼叫，回傳完整回覆字串。
    與 llm_stream 共用相同的 provider/model/api_key 解析邏輯。
    config_override: {provider, model, api_key} 來自 DB 設定，優先於 env vars。
    失敗時直接拋出 Exception，不靜默吞掉。
    """
    override = config_override or {}
    provider = override.get("provider") or settings.LLM_PROVIDER
    model    = model_override or override.get("model") or _resolve_model(settings)
    api_key_override = override.get("api_key")

    if provider == "ollama":
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return (data.get("message") or {}).get("content", "")

    if provider == "anthropic":
        api_key = api_key_override or getattr(settings, "ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY 未設定")
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        user_messages = [m for m in messages if m["role"] != "system"]
        system_prompt = "\n\n".join(system_parts) if system_parts else None
        payload: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": user_messages,
            "stream": False,
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
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            blocks = data.get("content") or []
            if not blocks:
                return ""
            return blocks[0].get("text", "")

    # OpenAI 相容（openai / groq / gemini / openrouter）
    base_url = _PROVIDER_BASE_URLS.get(provider, "")
    api_key  = api_key_override or _resolve_api_key(settings)
    if not base_url:
        raise ValueError(f"未知的 LLM_PROVIDER: {provider}")
    if not api_key:
        raise ValueError(f"請先設定 {provider.upper()} API Key")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "http://localhost"
        headers["X-Title"]      = "BruV AI KB"

    payload = {
        "model":       model,
        "messages":    messages,
        "stream":      False,
        "temperature": temperature,
        "max_tokens":  max_tokens,
    }
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message") or {}).get("content", "")


# ── Function Calling（openai / anthropic / groq）───────────────────────────────

FC_PROVIDERS: frozenset[str] = frozenset({"openai", "anthropic", "groq"})


async def llm_with_tools(
    messages: list[dict],
    tools: list[dict],
    settings,
    model_override: str | None = None,
    config_override: dict | None = None,
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> dict:
    """
    Function calling 非串流呼叫。
    tools: 統一格式 [{"name": str, "description": str, "parameters": JsonSchema}]
    回傳: {"text": str, "tool_calls": [{"name": str, "arguments": dict}]}
    不支援 FC 的 provider（如 ollama）回傳 {"text": "", "tool_calls": []}，呼叫端應 fallback 到 __action__ 文字解析。
    """
    override = config_override or {}
    provider = override.get("provider") or settings.LLM_PROVIDER
    model = model_override or override.get("model") or _resolve_model(settings)
    api_key_override = override.get("api_key")

    if provider not in FC_PROVIDERS:
        return {"text": "", "tool_calls": []}

    if provider == "anthropic":
        return await _anthropic_with_tools(
            messages, tools, model, settings, api_key_override, temperature, max_tokens
        )
    return await _openai_with_tools(
        messages, tools, model, settings, provider, api_key_override, temperature, max_tokens
    )


async def _openai_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str,
    settings,
    provider: str,
    api_key_override: str | None,
    temperature: float,
    max_tokens: int,
) -> dict:
    base_url = _PROVIDER_BASE_URLS.get(provider, "")
    api_key = api_key_override or _resolve_api_key(settings)
    if not base_url or not api_key:
        return {"text": "", "tool_calls": []}

    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "tools": openai_tools,
        "tool_choice": "auto",
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    message = (data.get("choices") or [{}])[0].get("message", {})
    text = message.get("content") or ""
    tool_calls = []
    for tc in (message.get("tool_calls") or []):
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception:
            args = {}
        tool_calls.append({"name": fn.get("name", ""), "arguments": args})
    return {"text": text, "tool_calls": tool_calls}


async def _anthropic_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str,
    settings,
    api_key_override: str | None,
    temperature: float,
    max_tokens: int,
) -> dict:
    api_key = api_key_override or getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"text": "", "tool_calls": []}

    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    user_messages = [m for m in messages if m["role"] != "system"]
    system_prompt = "\n\n".join(system_parts) if system_parts else None

    anthropic_tools = [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
        }
        for t in tools
    ]
    payload: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": user_messages,
        "tools": anthropic_tools,
        "temperature": temperature,
        "stream": False,
    }
    if system_prompt:
        payload["system"] = system_prompt

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    text = ""
    tool_calls = []
    for block in (data.get("content") or []):
        if block.get("type") == "text":
            text += block.get("text", "")
        elif block.get("type") == "tool_use":
            tool_calls.append({
                "name": block.get("name", ""),
                "arguments": block.get("input") or {},
            })
    return {"text": text, "tool_calls": tool_calls}
