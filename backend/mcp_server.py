"""
MCP Server — 把句型引擎包裝成 Copilot / Claude Code 可呼叫的工具

協議：JSON-RPC 2.0 over SSE（不依賴 MCP SDK）
啟動：uvicorn mcp_server:app --port 8001
"""
import asyncio
import json
import logging
import os
import re
from typing import Any, AsyncGenerator

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

# ── 設定 ──────────────────────────────────────────────────────
MAIN_APP_URL = os.getenv("MAIN_APP_URL", "http://localhost:8000")
MCP_INTERNAL_TOKEN = os.getenv("MCP_INTERNAL_TOKEN", "")
MCP_LOGIN_EMAIL = os.getenv("MCP_LOGIN_EMAIL", "")
MCP_LOGIN_PASSWORD = os.getenv("MCP_LOGIN_PASSWORD", "")
REQUEST_TIMEOUT = 120.0

# LLM 填充 provider 設定
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")       # "ollama" | "openai"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5:14b")
_LLM_FILL_TIMEOUT = 60.0

# 執行期快取 token（auto-login 時使用）
_cached_token: str = ""

app = FastAPI(title="Prompt Engine MCP Server", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── Tool 定義 ─────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "match_prompt_template",
        "description": (
            "根據意圖自動選擇最相關的句型模板並填充變數，回傳完整 prompt。"
            "適合在要開始寫代碼、debug、git commit 等任何需要結構化提示的場景前呼叫。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "你想做什麼，例如「幫我實作爬蟲任務」或「程式報錯不知道怎麼修」",
                },
                "context": {
                    "type": "object",
                    "description": "補充變數，例如 {\"file_path\": \"tasks/crawl.py\", \"task\": \"建立 Celery worker\"}",
                },
            },
            "required": ["intent"],
        },
    },
    {
        "name": "list_prompt_categories",
        "description": "列出所有可用的句型模板類別與摘要，讓 AI 了解有哪些結構化模板可用。",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "search_prompt_templates",
        "description": "以自然語言搜尋最相關的句型模板（只搜尋、不填充變數）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋關鍵字或描述，例如「代碼審查」",
                },
                "top_k": {
                    "type": "integer",
                    "description": "回傳幾筆結果，預設 3",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "rag_search",
        "description": "對使用者知識庫做語義搜尋，回傳最相關的文件片段（chunk）。可選擇限定於特定 KB。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "自然語言查詢"},
                "kb_id": {"type": "string", "description": "（選填）限定知識庫 ID"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_kbs",
        "description": "列出所有知識庫（含 id、名稱、描述、文件數）。",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_docs",
        "description": "列出文件清單,可選擇以 kb_id 過濾。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string", "description": "（選填）限定知識庫 ID"},
                "search": {"type": "string", "description": "（選填）檔名關鍵字"},
                "page_size": {"type": "integer", "description": "回傳數量上限,預設 20", "default": 20},
            },
            "required": [],
        },
    },
]

# ── LLM 填充（MCP 端，可切換 provider） ───────────────────────

_SYSTEM_MSG = (
    "你是 Prompt 填充助手。"
    "請依據Context將Template中的{var}佔位符填入對應的實際內容。"
    "不要修改模板結構，不要新增或刪除任何內容，只將{}中的占位符替換為實際文字。"
    "如果Context沒有提供某個變數，保留原佔位符不動。只回傳填充後的Prompt，不要加任何說明文字。"
)

_UNFILLED_VAR_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


async def _llm_fill_openai(user_msg: str) -> str:
    """呼叫 OpenAI gpt-4o-mini 填充模板變數"""
    if not OPENAI_API_KEY:
        raise ValueError("LLM_PROVIDER=openai 但 OPENAI_API_KEY 未設定")
    async with httpx.AsyncClient(timeout=_LLM_FILL_TIMEOUT) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": _SYSTEM_MSG},
                    {"role": "user", "content": user_msg},
                ],
                "max_tokens": 1000,
                "temperature": 0,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _llm_fill_ollama(user_msg: str) -> str:
    """呼叫 Ollama 填充模板變數"""
    async with httpx.AsyncClient(timeout=_LLM_FILL_TIMEOUT) as client:
        resp = await client.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_LLM_MODEL,
                "stream": False,
                "messages": [
                    {"role": "system", "content": _SYSTEM_MSG},
                    {"role": "user", "content": user_msg},
                ],
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


async def _llm_fill(template: str, context: dict, intent: str) -> str:
    """依 LLM_PROVIDER 切換 OpenAI / Ollama 填充模板變數；失敗時降級回傳原始模板"""
    user_msg = (
        f"Intent：{intent}\n\n"
        f"Context：{context}\n\n"
        f"Template：\n{template}"
    )
    try:
        if LLM_PROVIDER == "openai":
            return await _llm_fill_openai(user_msg)
        return await _llm_fill_ollama(user_msg)
    except Exception:
        logger.exception("MCP _llm_fill 失敗（provider=%s），降級回傳原始模板", LLM_PROVIDER)
        return template


# ── HTTP 呼叫主 APP ───────────────────────────────────────────

async def _get_token() -> str:
    """取得 Bearer token：優先用環境變數，否則自動登入後快取"""
    global _cached_token
    if MCP_INTERNAL_TOKEN:
        return MCP_INTERNAL_TOKEN
    if _cached_token:
        return _cached_token
    if not MCP_LOGIN_EMAIL or not MCP_LOGIN_PASSWORD:
        return ""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{MAIN_APP_URL}/api/auth/login",
            json={"email": MCP_LOGIN_EMAIL, "password": MCP_LOGIN_PASSWORD},
        )
        resp.raise_for_status()
        _cached_token = resp.json()["access_token"]
        return _cached_token


async def _auth_headers() -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    token = await _get_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _call_match(intent: str, context: dict) -> str:
    payload = {"intent": intent, "context": context}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.post(
            f"{MAIN_APP_URL}/api/prompt-templates/match",
            json=payload,
            headers=await _auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()

    filled_prompt = data.get("filled_prompt", "")

    # ── MCP 端 LLM 填充（LLM_PROVIDER=openai 時觸發） ─────────
    # 條件：主 APP 回傳的 filled_prompt 仍含有 {var} 佔位符
    #      （代表主 APP 的 Ollama fill 超時或失敗）
    if LLM_PROVIDER == "openai" and _UNFILLED_VAR_RE.search(filled_prompt):
        filled_prompt = await _llm_fill(filled_prompt, context, intent)

    lines = [
        f"**類別**: {data.get('category', '')}",
        f"**模板 ID**: {data.get('matched_template_id', '')}",
        f"**信心分數**: {data.get('confidence', 0):.4f}",
        "",
        "**填充後的 Prompt**:",
        "```",
        filled_prompt,
        "```",
    ]
    if data.get("pit_warnings"):
        lines += ["", "**⚠️ 注意事項**:"]
        lines += [f"- {w}" for w in data["pit_warnings"]]
    if data.get("missing_vars"):
        lines += ["", f"**缺少變數**: {', '.join(data['missing_vars'])}"]
    return "\n".join(lines)


async def _call_list_categories() -> str:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.get(
            f"{MAIN_APP_URL}/api/prompt-templates/",
            headers=await _auth_headers(),
        )
        resp.raise_for_status()
        templates = resp.json()

    if not templates:
        return "目前沒有任何句型模板。"

    # 依 category 分組
    by_cat: dict[str, list] = {}
    for tpl in templates:
        cat = tpl.get("category", "unknown")
        by_cat.setdefault(cat, []).append(tpl)

    lines = [f"共 {len(templates)} 個模板，分 {len(by_cat)} 個類別：", ""]
    for cat, tpls in sorted(by_cat.items()):
        lines.append(f"### {cat} ({len(tpls)} 個)")
        for t in tpls:
            triggers = t.get("example_triggers", [])
            trigger_str = "、".join(triggers[:3]) if triggers else "（無關鍵詞）"
            lines.append(f"- **{t.get('title', '')}** — 觸發詞：{trigger_str}")
        lines.append("")
    return "\n".join(lines)


async def _call_search(query: str, top_k: int) -> str:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.post(
            f"{MAIN_APP_URL}/api/prompt-templates/search",
            params={"query": query, "top_k": top_k},
            headers=await _auth_headers(),
        )
        resp.raise_for_status()
        results = resp.json()

    if not results:
        return f"找不到與「{query}」相關的模板。"

    lines = [f"搜尋「{query}」，找到 {len(results)} 個結果：", ""]
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. **{r.get('title', '')}** (category: `{r.get('category', '')}`, "
            f"score: {r.get('score', 0):.4f})"
        )
        lines.append(f"   ID: `{r.get('template_id', '')}`")
        lines.append("")
    return "\n".join(lines)


async def _call_rag_search(query: str, kb_id: str | None) -> str:
    payload: dict = {"query": query}
    if kb_id:
        payload["kb_scope_id"] = kb_id
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.post(
            f"{MAIN_APP_URL}/api/chat/rag-search",
            json=payload,
            headers=await _auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
    results = data.get("results", [])
    if not results:
        return f"找不到與「{query}」相關的文件片段。"
    lines = [f"知識庫搜尋「{query}」，找到 {len(results)} 個片段：", ""]
    for i, r in enumerate(results, 1):
        title = r.get("title") or r.get("doc_id") or "（無標題）"
        page = r.get("page_number")
        page_str = f" p.{page}" if page else ""
        lines.append(
            f"{i}. **{title}**{page_str} (chunk_id: `{r.get('chunk_id','')}`, score: {r.get('score',0):.3f})"
        )
        lines.append(f"   {r.get('content_preview','')}")
        lines.append("")
    return "\n".join(lines)


async def _call_list_kbs() -> str:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.get(
            f"{MAIN_APP_URL}/api/knowledge-bases",
            headers=await _auth_headers(),
        )
        resp.raise_for_status()
        kbs = resp.json()
    if not kbs:
        return "目前沒有任何知識庫。"
    lines = [f"共 {len(kbs)} 個知識庫：", ""]
    for kb in kbs:
        lines.append(
            f"- **{kb.get('name','')}** (id: `{kb.get('id','')}`, doc_count: {kb.get('document_count', '?')})"
        )
        if kb.get("description"):
            lines.append(f"  {kb['description']}")
    return "\n".join(lines)


async def _call_list_docs(kb_id: str | None, search: str | None, page_size: int) -> str:
    params: dict = {"page_size": page_size}
    if kb_id:
        params["knowledge_base_id"] = kb_id
    if search:
        params["search"] = search
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.get(
            f"{MAIN_APP_URL}/api/documents/",
            params=params,
            headers=await _auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
    docs = data if isinstance(data, list) else data.get("items", [])
    if not docs:
        return "找不到符合條件的文件。"
    lines = [f"共 {len(docs)} 份文件：", ""]
    for d in docs:
        lines.append(
            f"- **{d.get('filename') or d.get('title','')}** (id: `{d.get('id','')}`, "
            f"chunks: {d.get('chunk_count', '?')}, kb: `{d.get('knowledge_base_id','')}`)"
        )
    return "\n".join(lines)


# ── Tool 分派 ─────────────────────────────────────────────────

async def _dispatch_tool(name: str, arguments: dict) -> str:
    if name == "match_prompt_template":
        intent = arguments.get("intent", "")
        if not intent:
            raise ValueError("intent 為必填欄位")
        context = arguments.get("context") or {}
        return await _call_match(intent, context)

    if name == "list_prompt_categories":
        return await _call_list_categories()

    if name == "search_prompt_templates":
        query = arguments.get("query", "")
        if not query:
            raise ValueError("query 為必填欄位")
        top_k = int(arguments.get("top_k") or 3)
        return await _call_search(query, top_k)

    if name == "rag_search":
        query = arguments.get("query", "")
        if not query:
            raise ValueError("query 為必填欄位")
        return await _call_rag_search(query, arguments.get("kb_id"))

    if name == "list_kbs":
        return await _call_list_kbs()

    if name == "list_docs":
        return await _call_list_docs(
            arguments.get("kb_id"),
            arguments.get("search"),
            int(arguments.get("page_size") or 20),
        )

    raise ValueError(f"未知的工具：{name}")


# ── JSON-RPC 2.0 工具函式 ─────────────────────────────────────

def _rpc_result(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: Any, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }


# ── SSE 端點（MCP 握手） ──────────────────────────────────────

async def _sse_stream(messages_url: str) -> AsyncGenerator[str, None]:
    """保持 SSE 連線，每 15 秒送一次 keep-alive comment"""
    endpoint_event = (
        f"event: endpoint\n"
        f"data: {json.dumps({'uri': messages_url})}\n\n"
    )
    yield endpoint_event
    while True:
        await asyncio.sleep(15)
        yield ": keep-alive\n\n"


@app.get("/sse")
async def sse_endpoint(request: Request) -> StreamingResponse:
    """MCP SSE 連線端點"""
    base = str(request.base_url).rstrip("/")
    messages_url = f"{base}/messages"
    return StreamingResponse(
        _sse_stream(messages_url),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── POST /messages — JSON-RPC 2.0 訊息處理 ───────────────────

@app.post("/messages")
async def messages_endpoint(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_rpc_error(None, -32700, "Parse error"), status_code=200)

    req_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params") or {}

    # initialize
    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "prompt-engine",
                "version": "1.0.0",
            },
        }
        return JSONResponse(_rpc_result(req_id, result))

    # notifications/initialized — 無回應
    if method == "notifications/initialized":
        return JSONResponse({}, status_code=200)

    # tools/list
    if method == "tools/list":
        return JSONResponse(_rpc_result(req_id, {"tools": TOOLS}))

    # tools/call
    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}
        try:
            text = await _dispatch_tool(tool_name, arguments)
            result = {"content": [{"type": "text", "text": text}]}
            return JSONResponse(_rpc_result(req_id, result))
        except ValueError as exc:
            return JSONResponse(_rpc_error(req_id, -32602, str(exc)))
        except httpx.HTTPStatusError as exc:
            msg = f"主 APP API 錯誤 {exc.response.status_code}: {exc.response.text[:200]}"
            return JSONResponse(_rpc_error(req_id, -32603, msg))
        except httpx.TimeoutException:
            return JSONResponse(_rpc_error(req_id, -32603, "主 APP API 請求逾時（60s）"))
        except Exception as exc:
            logger.exception("tools/call 未預期錯誤 tool=%s", tool_name)
            return JSONResponse(_rpc_error(req_id, -32603, f"內部錯誤: {exc}"))

    # 未知 method
    return JSONResponse(_rpc_error(req_id, -32601, f"Method not found: {method}"))
