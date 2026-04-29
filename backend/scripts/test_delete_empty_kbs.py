"""測試：後端 action 執行路徑驗證（execute-action endpoint + 對話流程）

測試項目：
A. POST /api/chat/execute-action：直接驗證後端執行 batch_delete_kb
B. (選用) 對話流程：透過 page_agent:docs 兩輪對話刪除空知識庫
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
EMAIL    = os.environ.get("LOGIN_EMAIL", "123")
PASSWORD = os.environ.get("LOGIN_PASSWORD", "admin123456")

PASS_COUNT = 0
FAIL_COUNT = 0


def _req(method: str, path: str, body=None, token: str | None = None, stream=False):
    url = API_BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    resp = urllib.request.urlopen(req, timeout=120)
    if stream:
        return resp
    return json.loads(resp.read().decode())


def check(label: str, passed: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    icon = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {icon}  {label}" + (f"  ({detail})" if detail else ""))
    if passed:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1


def sse_stream(payload: dict, token: str) -> tuple[str, list[dict]]:
    resp_stream = _req("POST", "/api/chat/stream", payload, token=token, stream=True)
    full_text = ""
    action_results: list[dict] = []
    for raw_line in resp_stream:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        ps = line[5:].strip()
        if ps == "[DONE]":
            break
        try:
            evt = json.loads(ps)
        except Exception:
            continue
        if evt.get("type") == "token":
            full_text += evt.get("text", "")
        elif evt.get("type") == "action_result":
            action_results.append(evt)
        elif evt.get("type") == "error":
            print(f"    ⚠️  SSE error: {evt.get('text')}")
    return full_text, action_results


# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("後端 Action 執行路徑驗證")
print("=" * 60)

# ── 登入 ───────────────────────────────────────────────────
data = _req("POST", "/api/auth/login", {"email": EMAIL, "password": PASSWORD})
token: str = data["access_token"]
print(f"\n登入成功\n")

# ── 取得空 KB 清單 ─────────────────────────────────────────
kbs_data = _req("GET", "/api/knowledge-bases/?limit=200", token=token)
kbs = kbs_data if isinstance(kbs_data, list) else kbs_data.get("items", [])
empty_kbs = [k for k in kbs if (k.get("doc_count") or 0) == 0]
all_ids   = [k["id"] for k in empty_kbs]
print(f"知識庫總數：{len(kbs)}，空知識庫：{len(empty_kbs)} 個\n")

# ═══════════════════════════════════════════════════════════
# 測試 A：直接呼叫 POST /api/chat/execute-action
# ═══════════════════════════════════════════════════════════
print("─" * 60)
print("A. 直接呼叫 /api/chat/execute-action")
print("─" * 60)

if not empty_kbs:
    print("  ⚠️  無空知識庫，跳過此測試")
else:
    # A1. 刪除第一個空 KB（單筆 delete_kb）
    target = empty_kbs[0]
    print(f"\nA1. delete_kb  id={target['id'][:8]}… 《{target['name'][:30]}》")
    resp_a1 = _req("POST", "/api/chat/execute-action",
                   {"action_type": "delete_kb", "params": {"kb_id": target["id"]}},
                   token=token)
    check("delete_kb 回傳 result", bool(resp_a1.get("result")), resp_a1.get("result", ""))
    check("delete_kb dispatch=reload_kbs", resp_a1.get("dispatch") == "reload_kbs",
          f"dispatch={resp_a1.get('dispatch')}")

    # 驗證已刪除
    kbs_after_a1_data = _req("GET", "/api/knowledge-bases/?limit=200", token=token)
    kbs_after_a1 = kbs_after_a1_data if isinstance(kbs_after_a1_data, list) else kbs_after_a1_data.get("items", [])
    ids_after_a1 = {k["id"] for k in kbs_after_a1}
    check("delete_kb 已從 DB 消失", target["id"] not in ids_after_a1)

    # A2. batch_delete_kb（剩餘的空 KB，最多 19 個）
    remaining_empty = [k for k in empty_kbs[1:20]]
    if remaining_empty:
        print(f"\nA2. batch_delete_kb  共 {len(remaining_empty)} 個")
        batch_ids = [k["id"] for k in remaining_empty]
        resp_a2 = _req("POST", "/api/chat/execute-action",
                       {"action_type": "batch_delete_kb", "params": {"kb_ids": batch_ids}},
                       token=token)
        check("batch_delete_kb 回傳 result", bool(resp_a2.get("result")), resp_a2.get("result", ""))
        check("batch_delete_kb dispatch=reload_kbs", resp_a2.get("dispatch") == "reload_kbs",
              f"dispatch={resp_a2.get('dispatch')}")

        kbs_after_a2_data = _req("GET", "/api/knowledge-bases/?limit=200", token=token)
        kbs_after_a2 = kbs_after_a2_data if isinstance(kbs_after_a2_data, list) else kbs_after_a2_data.get("items", [])
        empty_after_a2 = [k for k in kbs_after_a2 if (k.get("doc_count") or 0) == 0]
        check("batch_delete_kb 空 KB 已清空", len(empty_after_a2) == 0,
              f"剩餘空 KB：{len(empty_after_a2)}")

# ═══════════════════════════════════════════════════════════
# 測試 B：對話流程（建立 KB → 對話刪除 → 驗證）
# ═══════════════════════════════════════════════════════════
print("\n" + "─" * 60)
print("B. 透過 page_agent:docs 對話刪除空知識庫")
print("─" * 60)

# B0. 先建立 2 個測試用空 KB
print("\nB0. 建立測試用空知識庫")
kb1 = _req("POST", "/api/knowledge-bases/",
           {"name": "test-empty-kb-1", "description": "測試用空知識庫"}, token=token)
kb2 = _req("POST", "/api/knowledge-bases/",
           {"name": "test-empty-kb-2", "description": "測試用空知識庫"}, token=token)
# API 可能回傳 list wrapper 或直接 object
kb1_id = (kb1.get("id") or (kb1.get("items") or [{}])[0].get("id"))
kb2_id = (kb2.get("id") or (kb2.get("items") or [{}])[0].get("id"))
print(f"  建立 kb1 id={kb1_id}  kb2 id={kb2_id}")
check("建立測試 KB", bool(kb1_id and kb2_id))

# B1. 建立對話
conv = _req("POST", "/api/chat/conversations",
            {"title": "test-dialog-delete-kbs", "agent_type": "page_agent:docs"},
            token=token)
conv_id = conv["id"]
print(f"  建立對話 id={conv_id}")

# B2. 第一輪：告知名稱+ID，要求刪除
turn1_msg = (
    "請使用 batch_delete_kb 刪除以下 2 個空知識庫（均無文件，操作安全）：\n"
    f"1. 《test-empty-kb-1》 id: {kb1_id}\n"
    f"2. 《test-empty-kb-2》 id: {kb2_id}\n"
)
print(f"\nB1. 第一輪：送出刪除請求")
t1_text, t1_ar = sse_stream({
    "query": turn1_msg,
    "conv_id": conv_id,
    "agent_type": "page_agent:docs",
    "mode": "agent",
}, token)
print(f"  AI 回覆（前 150 字）：{t1_text[:150].replace(chr(10), ' ')}")
print(f"  action_result 數：{len(t1_ar)}")

# B3. 如果第一輪就已執行（action_result），代表 FC path 成功
if t1_ar:
    check("第一輪直接執行（FC path）", True, f"{t1_ar[0].get('result')}")
else:
    # B4. 第二輪：確認
    print(f"\nB2. 第二輪：回覆確認")
    confirm_msg = f"確認刪除，這 2 個知識庫（{kb1_id[:8]}…、{kb2_id[:8]}…）均為空的測試 KB"
    t2_text, t2_ar = sse_stream({
        "query": confirm_msg,
        "conv_id": conv_id,
        "agent_type": "page_agent:docs",
        "mode": "agent",
    }, token)
    print(f"  AI 回覆（前 150 字）：{t2_text[:150].replace(chr(10), ' ')}")
    print(f"  action_result 數：{len(t2_ar)}")
    all_ar = t1_ar + t2_ar
    check("對話觸發 action_result 事件", len(all_ar) > 0,
          f"共 {len(all_ar)} 個事件")
    if all_ar:
        check("action_type=batch_delete_kb",
              any(ar.get("action_type") == "batch_delete_kb" for ar in all_ar),
              str([ar.get("action_type") for ar in all_ar]))

# B5. 驗證 KB 已刪除
kbs_final_data = _req("GET", "/api/knowledge-bases/?limit=200", token=token)
kbs_final = kbs_final_data if isinstance(kbs_final_data, list) else kbs_final_data.get("items", [])
final_ids = {k["id"] for k in kbs_final}
check("test-empty-kb-1 已刪除", kb1_id not in final_ids if kb1_id else False)
check("test-empty-kb-2 已刪除", kb2_id not in final_ids if kb2_id else False)

# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print(f"總計：{PASS_COUNT + FAIL_COUNT}  通過：{PASS_COUNT}  失敗：{FAIL_COUNT}  "
      f"通過率：{PASS_COUNT/(PASS_COUNT+FAIL_COUNT)*100:.1f}%")
print("=" * 60)
sys.exit(0 if FAIL_COUNT == 0 else 1)

