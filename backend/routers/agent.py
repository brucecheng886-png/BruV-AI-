"""
Agent Router — LangChain ReAct Agent

端點：
  POST /api/agent/run              → 202 + { task_id }
  GET  /api/agent/tasks/{task_id}  → { status, steps, result, error }
"""
import json
import logging
import threading
import uuid
from typing import Any, Optional

import httpx
import redis as redis_sync
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import CurrentUser
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Redis 同步客戶端（任務狀態儲存）─────────────────────────────
_redis_client: Optional[redis_sync.Redis] = None

def _get_redis() -> redis_sync.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_sync.from_url(
            settings.REDIS_URL.replace("/0", "/3"),  # 使用 DB3 避免衝突
            decode_responses=True,
        )
    return _redis_client


# ── Pydantic Schemas ──────────────────────────────────────────
class AgentRunRequest(BaseModel):
    instruction: str
    model: Optional[str] = None


class AgentRunResponse(BaseModel):
    task_id: str
    status: str = "running"


class AgentTaskStatus(BaseModel):
    task_id: str
    status: str          # running | completed | failed
    steps: list
    result: Optional[str] = None
    error: Optional[str] = None


# ── Web Search Tool ───────────────────────────────────────────
def _build_web_search_tool():
    from langchain.tools import Tool

    def web_search(query: str) -> str:
        """呼叫 SearXNG 搜尋引擎"""
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(
                    f"{settings.SEARXNG_URL}/search",
                    params={"q": query, "format": "json", "language": "zh-TW"},
                )
                resp.raise_for_status()
                data = resp.json()

            results = data.get("results", [])[:5]
            if not results:
                return "未找到相關搜尋結果。"

            parts = []
            for r in results:
                title = r.get("title", "")
                content = r.get("content", "")
                url = r.get("url", "")
                parts.append(f"【{title}】\n{content}\n來源：{url}")

            return "\n\n".join(parts)
        except Exception as e:
            logger.error("web_search 失敗: %s", e, exc_info=True)
            return f"搜尋發生錯誤：{e}"

    return Tool(
        name="web_search",
        func=web_search,
        description=(
            "在網際網路上搜尋最新資訊、時事新聞或知識庫中沒有的內容。"
            "輸入：搜尋查詢字串。輸出：搜尋結果摘要。"
        ),
    )


# ── Agent Runner（背景執行緒）────────────────────────────────────
def _run_agent_task(task_id: str, instruction: str, model: str):
    """在獨立執行緒中執行 LangChain ReAct Agent"""
    r = _get_redis()
    steps: list[dict[str, Any]] = []

    def _save_status(status: str, result: str = None, error: str = None):
        r.setex(
            f"agent_task:{task_id}",
            86400,  # TTL 24h
            json.dumps({
                "task_id": task_id,
                "status": status,
                "steps": steps,
                "result": result,
                "error": error,
            }),
        )

    try:
        _save_status("running")

        # 建立工具集
        from tools.llama_retriever_tool import build_knowledge_base_tool
        from tools.code_executor import build_code_executor_tool

        tools = [
            build_knowledge_base_tool(),
            _build_web_search_tool(),
            build_code_executor_tool(),
        ]

        # 建立 LangChain ReAct Agent
        from langchain_ollama import ChatOllama
        from langchain.agents import AgentExecutor, create_react_agent
        from langchain import hub

        llm = ChatOllama(
            model=model,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=0,
        )

        # ReAct prompt（使用 langchain hub 標準模板）
        try:
            prompt = hub.pull("hwchase17/react")
        except Exception:
            # fallback：若無法取得 hub，使用內建 prompt
            from langchain.prompts import PromptTemplate
            prompt = PromptTemplate.from_template(
                "Answer the following questions as best you can. "
                "You have access to the following tools:\n\n"
                "{tools}\n\n"
                "Use the following format:\n\n"
                "Question: the input question you must answer\n"
                "Thought: you should always think about what to do\n"
                "Action: the action to take, should be one of [{tool_names}]\n"
                "Action Input: the input to the action\n"
                "Observation: the result of the action\n"
                "... (this Thought/Action/Action Input/Observation can repeat N times)\n"
                "Thought: I now know the final answer\n"
                "Final Answer: the final answer to the original input question\n\n"
                "Begin!\n\n"
                "Question: {input}\n"
                "Thought:{agent_scratchpad}"
            )

        agent = create_react_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=False,
            max_iterations=8,
            early_stopping_method="generate",
            handle_parsing_errors=True,
        )

        # 收集 steps（LangChain callback）
        from langchain.callbacks.base import BaseCallbackHandler

        class StepCallback(BaseCallbackHandler):
            def on_agent_action(self, action, **kwargs):
                steps.append({
                    "type": "action",
                    "tool": action.tool,
                    "input": str(action.tool_input)[:500],
                })
                _save_status("running")

            def on_tool_end(self, output, **kwargs):
                steps.append({
                    "type": "observation",
                    "output": str(output)[:500],
                })
                _save_status("running")

        result = agent_executor.invoke(
            {"input": instruction},
            config={"callbacks": [StepCallback()]},
        )

        final_answer = result.get("output", "")
        _save_status("completed", result=final_answer)
        logger.info("Agent task %s completed", task_id)

    except Exception as e:
        logger.error("Agent task %s failed: %s", task_id, e, exc_info=True)
        _save_status("failed", error=str(e))


# ── API Endpoints ─────────────────────────────────────────────

@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=AgentRunResponse)
@router.post("/run", status_code=status.HTTP_202_ACCEPTED, response_model=AgentRunResponse)
async def run_agent(
    body: AgentRunRequest,
    _user: CurrentUser,
):
    """啟動 Agent 任務（非同步，背景執行緒）"""
    if not body.instruction.strip():
        raise HTTPException(status_code=400, detail="instruction 不得為空")

    task_id = str(uuid.uuid4())
    model = body.model or settings.OLLAMA_LLM_MODEL

    # 初始化 Redis 狀態
    r = _get_redis()
    r.setex(
        f"agent_task:{task_id}",
        86400,
        json.dumps({
            "task_id": task_id,
            "status": "running",
            "steps": [],
            "result": None,
            "error": None,
        }),
    )

    # 背景執行緒啟動 agent
    t = threading.Thread(
        target=_run_agent_task,
        args=(task_id, body.instruction, model),
        daemon=True,
    )
    t.start()

    return AgentRunResponse(task_id=task_id)


@router.get("/tasks/{task_id}", response_model=AgentTaskStatus)
async def get_task_status(task_id: str, _user: CurrentUser):
    """查詢 Agent 任務狀態"""
    r = _get_redis()
    raw = r.get(f"agent_task:{task_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="Task not found")
    data = json.loads(raw)
    return AgentTaskStatus(**data)

