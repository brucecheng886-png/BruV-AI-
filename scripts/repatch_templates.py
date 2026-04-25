#!/usr/bin/env python3
"""
repatch_templates.py — 修復 DB 中亂碼的 Prompt 模板（用 PUT 覆寫正確中文內容）

使用方式：
    python scripts/repatch_templates.py --token <JWT>
"""
import argparse
import sys
import httpx

# template_id → 對應的完整 payload（含修正後的 example_triggers）
PATCHES = {
    "4044e48a-6e91-44bb-84e7-bd67268a9423": {
        "category": "code_gen",
        "title": "Copilot 代碼生成標準格式",
        "template": (
            "當前任務：{task}\n"
            "所在檔案：{file_path}\n"
            "相關型別定義：\n{type_defs}\n"
            "已有的鄰近代碼：\n{neighbor_code}\n"
            "限制條件：{constraints}\n\n"
            "請依上述資訊生成代碼，不要做：{do_not}"
        ),
        "required_vars": ["task", "file_path"],
        "optional_vars": ["type_defs", "neighbor_code", "constraints", "do_not"],
        "example_triggers": [
            "幫我實作",           # ← 短觸發詞，命中「幫我實作 crawl_tasks.py」
            "請幫我實作",
            "請幫我實作這個功能",
            "幫我寫程式碼",
            "生成這個元件的代碼",
            "寫一個 API endpoint",
        ],
        "pit_warnings": [
            "生成超過 100 行代碼前必須逐行閱讀",
            "不理解就直接貼入 AI 生成的代碼是禁止行為",
            "因為 AI 說「應該沒問題」就跳過測試是禁止行為",
        ],
    },
    "c8d69290-2d74-4515-8c22-a90b4efedb4c": {
        "category": "debug",
        "title": "分層診斷 Debug 格式",
        "template": (
            "## Bug 分層診斷\n\n"
            "**現象**（觀察到什麼 vs 預期什麼）：\n{symptom}\n\n"
            "**分層假說**：\n"
            "- Layer 1（掛載層）：{layer1_hypothesis}\n"
            "- Layer 2（數值層）：{layer2_hypothesis}\n"
            "- Layer 3（邏輯層）：{layer3_hypothesis}\n"
            "- Layer 4（時序層）：{layer4_hypothesis}\n\n"
            "**Canary Test**：\n{canary_test}\n\n"
            "**精確修改**（預期效果）：\n{fix_description}"
        ),
        "required_vars": ["symptom"],
        "optional_vars": [
            "layer1_hypothesis", "layer2_hypothesis",
            "layer3_hypothesis", "layer4_hypothesis",
            "canary_test", "fix_description",
        ],
        "example_triggers": [
            "程式報錯",           # ← 命中「程式報錯不知道怎麼修」
            "報錯",
            "不知道怎麼修",
            "遇到 bug",
            "有 bug",
            "畫面不如預期",
            "API 回傳異常",
            "元件不渲染",
            "數值計算錯誤",
            "TypeError",
            "AttributeError",
            "Exception",
            "traceback",
            "debug",
        ],
        "pit_warnings": [
            "禁止看到 bug 就重寫整個函式",
            "禁止同時改多處（無法判斷哪個有效）",
            "禁止用 hardcode 值繞過計算邏輯",
            "禁止跳過 L1/L2 直接猜 L3/L4",
            "不可跳層診斷",
        ],
    },
    "ac467cd2-cae3-4118-9993-68f6cd0d2f75": {
        "category": "review",
        "title": "Gate 驗收自檢格式",
        "template": (
            "## Gate {gate_id} 驗收報告\n\n"
            "**Phase**：{phase}\n"
            "**驗收日期**：{date}\n\n"
            "### 驗收清單\n"
            "- [ ] 所有容器狀態 healthy\n"
            "- [ ] 關鍵 API 回傳正確\n"
            "- [ ] 無 unhealthy 容器\n"
            "- [ ] 錯誤日誌無嚴重錯誤\n\n"
            "### 代碼自檢\n"
            "- [ ] 型別定義完整，沒有 any\n"
            "- [ ] 所有異常都有 log，不靜默吞掉\n"
            "- [ ] 跨資料庫操作有 Saga 日誌保護\n"
            "- [ ] 中文字串全部為繁體中文\n\n"
            "### 結論\n"
            "{conclusion}"
        ),
        "required_vars": ["gate_id", "phase"],
        "optional_vars": ["date", "conclusion"],
        "example_triggers": [
            "進行 Gate 驗收",
            "Gate 驗收",
            "Phase 完成確認",
            "代碼提交前自檢",
        ],
        "pit_warnings": [
            "不可跳過驗收閘門直接進入下一 Phase",
            "必須先跑再寫：確認依賴服務已啟動",
        ],
    },
    "7de5b865-4c8c-48e1-b88c-971af4b8e9ea": {
        "category": "phase",
        "title": "新 Phase 開始標準格式",
        "template": (
            "## Phase {phase_id} 開始\n\n"
            "**目標**：{objective}\n\n"
            "**前置條件**（Gate {prev_gate} 必須已通過）：\n"
            "- 所有依賴服務已啟動且 healthy\n"
            "- Saga 日誌已初始化\n\n"
            "**本 Phase 工作項目**：\n"
            "{work_items}\n\n"
            "**驗收閘門**：Gate {gate_id}\n\n"
            "**不做**：\n"
            "{out_of_scope}"
        ),
        "required_vars": ["phase_id", "objective", "gate_id"],
        "optional_vars": ["prev_gate", "work_items", "out_of_scope"],
        "example_triggers": [
            "開始新的 Phase",
            "進入下一個開發階段",
            "規劃本次迭代工作",
        ],
        "pit_warnings": [
            "每次只實作一個功能，立即測試",
            "任何跨資料庫操作必須先確認 Saga 日誌已初始化",
            "每個 Phase 必須通過驗收閘門才能進入下一個",
        ],
    },
    "4425e4d2-a5d8-40fc-a0cf-b556594b536c": {
        "category": "git",
        "title": "Conventional Commits 提交訊息格式",
        "template": (
            "{type}({scope}): {description}\n\n"
            "{body}"
        ),
        "required_vars": ["type", "scope", "description"],
        "optional_vars": ["body"],
        "example_triggers": [
            "寫 commit message",
            "提交代碼前",
            "git commit",
        ],
        "pit_warnings": [
            "禁止 commit message 寫「fix bug」（太模糊）",
            "禁止直接 commit 到 main",
            "一個 commit 只改一件事",
            "禁止 commit 含 console.log / debug code",
            "type 必須是 feat/fix/refactor/style/docs/chore/test 之一",
        ],
    },
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--token", required=True)
    args = p.parse_args()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {args.token}",
    }

    ok = 0
    failed = 0
    with httpx.Client(timeout=60.0) as client:
        for tid, payload in PATCHES.items():
            url = f"{args.base_url.rstrip('/')}/api/prompt-templates/{tid}"
            resp = client.put(url, headers=headers, json=payload)
            if resp.status_code == 200:
                print(f"[OK]   {payload['category']} ({tid[:8]})")
                ok += 1
            else:
                print(f"[FAIL] {payload['category']} ({tid[:8]}) → HTTP {resp.status_code}: {resp.text[:200]}")
                failed += 1

    print(f"\n完成：{ok} 筆成功，{failed} 筆失敗。")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
