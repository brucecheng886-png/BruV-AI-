"""
Code Executor — RestrictedPython 沙盒（架構 §5.5）

白名單模組：math, statistics, json, re, datetime, collections, itertools, functools
Timeout：30 秒（threading）
"""
import logging
import threading
from typing import Any

from RestrictedPython import compile_restricted, safe_globals, safe_builtins
from RestrictedPython.Guards import safe_globals as _safe_globals
from RestrictedPython.PrintCollector import PrintCollector

logger = logging.getLogger(__name__)

ALLOWED_IMPORTS = frozenset({
    "math", "statistics", "json", "re", "datetime",
    "collections", "itertools", "functools", "decimal",
    "fractions", "random", "string",
})
TIMEOUT_SECONDS = 30


def _safe_import(name: str, *args: Any, **kwargs: Any):
    """只允許白名單模組匯入"""
    if name not in ALLOWED_IMPORTS:
        raise ImportError(f"Module '{name}' is not allowed in sandbox")
    return __import__(name, *args, **kwargs)


def _strip_code_fencing(code: str) -> str:
    """去除 markdown 代碼圍欄和常見的 LangChain Action Input 包裝格式"""
    code = code.strip()
    # 去除 ```python\n...\n``` 或 ```\n...\n```
    if code.startswith("```"):
        lines = code.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines).strip()
    # 去除單行 backtick wrapping: `code`
    elif code.startswith("`") and code.endswith("`") and code.count("`") == 2:
        code = code[1:-1]
    # 去除 code = "..." 或 code = '...' 格式
    elif code.startswith(("code = \"", "code = '", "code=\"", "code='")):
        # 萃取引號內的程式碼
        for prefix in ('code = "', 'code="', "code = '", "code='"):
            if code.startswith(prefix):
                inner = code[len(prefix):]
                quote = prefix[-1]
                if inner.endswith(quote):
                    inner = inner[:-1]
                code = inner
                break
    return code.strip()


def execute_code(code: str) -> dict:
    """
    在 RestrictedPython 沙盒中執行程式碼。

    安全策略：
    1. 靜態分析：阻止危險的 import（os, sys, subprocess 等）
    2. RestrictedPython 編譯時靜態分析
    3. 自訂 __import__ 白名單
    4. 30 秒 timeout（threading）

    回傳：{"output": {...}} 或 {"error": "..."}
    """
    # 0. 去除 markdown 代碼圍欄
    code = _strip_code_fencing(code)
    # 1. 白名單 import 靜態掃描
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            parts = stripped.split()
            module = parts[1].split(".")[0] if len(parts) > 1 else ""
            if module and module not in ALLOWED_IMPORTS:
                return {"error": f"Module '{module}' is not allowed. Allowed: {sorted(ALLOWED_IMPORTS)}"}

    # 2. RestrictedPython 編譯
    try:
        byte_code = compile_restricted(code, "<sandbox>", "exec")
    except SyntaxError as e:
        return {"error": f"SyntaxError: {e}"}
    except Exception as e:
        return {"error": f"Compilation error: {e}"}

    # 3. 執行（帶 timeout）
    exec_result: dict[str, Any] = {}
    exec_exception: list[Exception] = []

    def _run():
        try:
            restricted_globals = {
                **safe_globals,
                "__builtins__": {
                    **safe_builtins,
                    "__import__": _safe_import,
                },
                "_print_": PrintCollector,   # RestrictedPython print 機制
                "_getiter_": iter,
                "_getattr_": getattr,
                "_write_": lambda x: x,
            }
            exec(byte_code, restricted_globals, exec_result)  # noqa: S102
        except Exception as e:
            exec_exception.append(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=TIMEOUT_SECONDS)

    if t.is_alive():
        return {"error": f"Execution timeout ({TIMEOUT_SECONDS}s)"}

    if exec_exception:
        return {"error": str(exec_exception[0])}

    # 從 RestrictedPython PrintCollector 取得輸出
    if "_print" in exec_result and hasattr(exec_result["_print"], "txt"):
        raw_out = exec_result["_print"].txt
        if isinstance(raw_out, list):
            output_text = "".join(str(x) for x in raw_out)
        else:
            output_text = str(raw_out)
    else:
        output_text = ""
    result_vars = {
        k: repr(v)
        for k, v in exec_result.items()
        if not k.startswith("_")
    }

    return {
        "output": output_text,
        "variables": result_vars,
    }


def build_code_executor_tool():
    """建立 LangChain Tool"""
    from langchain.tools import Tool

    def _run(code: str) -> str:
        result = execute_code(code)
        if "error" in result:
            return f"執行錯誤：{result['error']}"
        parts = []
        if result.get("output"):
            parts.append(f"輸出：\n{result['output'].strip()}")
        if result.get("variables"):
            parts.append(f"變數：{result['variables']}")
        return "\n".join(parts) if parts else "程式碼執行完成（無輸出）"

    return Tool(
        name="code_executor",
        func=_run,
        description=(
            "在安全沙盒中執行 Python 程式碼。"
            "允許模組：math, statistics, json, re, datetime, collections, itertools等。"
            "不允許：os, sys, subprocess, socket等系統模組。"
            "輸入：Python 程式碼字串。輸出：執行結果。"
        ),
    )
