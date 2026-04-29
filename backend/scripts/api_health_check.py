"""API 健康檢查腳本

用途：登入後依序測試各核心 API，記錄 HTTP 狀態、響應時間、成功與否。
另對 /api/chat/stream 測試 4 種 agent_type：
  - page_agent:docs
  - page_agent:ontology
  - kb_agent
  - global_agent

執行：
  在容器內：docker compose exec -T backend python scripts/api_health_check.py
  在本機（後端跑於 localhost:8000）：python backend/scripts/api_health_check.py

可用環境變數：
  API_BASE   (default: http://localhost:8000)
  LOGIN_EMAIL/LOGIN_PASSWORD (default: 123 / admin123456)
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
LOGIN_EMAIL = os.environ.get("LOGIN_EMAIL", "123")
LOGIN_PASSWORD = os.environ.get("LOGIN_PASSWORD", "admin123456")

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def _request(method: str, path: str, *, token: str | None = None,
             body: dict | None = None, stream: bool = False, timeout: int = 30):
    url = f"{API_BASE}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    t0 = time.perf_counter()
    status = 0
    text = ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            if stream:
                # 只讀前 4KB 確認有資料
                text = resp.read(4096).decode("utf-8", errors="replace")
            else:
                text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            text = e.read().decode("utf-8", errors="replace")
        except Exception:
            text = str(e)
    except Exception as e:
        status = -1
        text = f"EXC: {type(e).__name__}: {e}"
    elapsed = (time.perf_counter() - t0) * 1000
    return status, text, elapsed


def login() -> str | None:
    status, text, _ = _request(
        "POST", "/api/auth/login",
        body={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
    )
    if status != 200:
        print(f"{RED}登入失敗 status={status} body={text[:200]}{RESET}")
        return None
    try:
        return json.loads(text).get("access_token")
    except Exception:
        return None


def stream_check(token: str, label: str, body: dict, timeout: int = 30):
    """測 SSE：成功條件 = HTTP 200 且首批內容含 'data: '。"""
    t0 = time.perf_counter()
    status, text, _ = _request(
        "POST", "/api/chat/stream",
        token=token, body=body, stream=True, timeout=timeout,
    )
    elapsed = (time.perf_counter() - t0) * 1000
    ok = (status == 200) and ("data:" in text)
    detail = ""
    if not ok:
        detail = text[:160].replace("\n", " ")
    return {
        "endpoint": f"/api/chat/stream [{label}]",
        "status": status,
        "elapsed_ms": elapsed,
        "ok": ok,
        "detail": detail,
    }


def normal_check(token: str, method: str, path: str, body: dict | None = None,
                 expect_status: int = 200, timeout: int = 30):
    status, text, elapsed = _request(method, path, token=token, body=body, timeout=timeout)
    ok = (status == expect_status)
    return {
        "endpoint": f"{method} {path}",
        "status": status,
        "elapsed_ms": elapsed,
        "ok": ok,
        "detail": "" if ok else text[:160].replace("\n", " "),
    }


def main():
    print(f"\n=== API 健康檢查 @ {API_BASE} ===\n")
    token = login()
    if not token:
        print(f"{RED}無法取得 token，中止測試{RESET}")
        raise SystemExit(2)

    print(f"{GREEN}登入成功{RESET}\n")

    results: list[dict] = []

    # 一般 API
    results.append(normal_check(token, "GET", "/api/documents/"))
    results.append(normal_check(token, "GET", "/api/knowledge-bases/"))
    results.append(normal_check(token, "GET", "/api/agent-skills/"))
    results.append(normal_check(token, "GET", "/api/wiki/models"))
    results.append(normal_check(token, "GET", "/api/settings/chat"))
    results.append(normal_check(token, "GET", "/api/settings/llm"))

    # /api/chat/stream 各種 agent_type
    base_body = {
        "query": "你好，自我介紹",
        "conversation_id": None,
        "model": None,
        "doc_ids": [],
        "kb_id": None,
        "tag_ids": [],
        "category_ids": [],
        "mode": "agent",
    }
    for agent_type in ("page_agent:docs", "page_agent:ontology", "kb_agent", "global_agent"):
        body = dict(base_body)
        body["agent_type"] = agent_type
        results.append(stream_check(token, agent_type, body))

    # 報表
    print(f"{'端點':<55}{'狀態':<8}{'耗時(ms)':<12}{'結果'}")
    print("-" * 90)
    for r in results:
        color = GREEN if r["ok"] else RED
        flag = "PASS" if r["ok"] else "FAIL"
        ep = r["endpoint"][:54]
        print(f"{color}{ep:<55}{r['status']:<8}{r['elapsed_ms']:<12.1f}{flag}{RESET}"
              + (f"  {YELLOW}{r['detail']}{RESET}" if r["detail"] else ""))

    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    failed = total - passed
    rate = (passed / total * 100) if total else 0.0
    print("-" * 90)
    print(f"總計：{total}  通過：{GREEN}{passed}{RESET}  失敗：{RED}{failed}{RESET}  通過率：{rate:.1f}%")
    raise SystemExit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
