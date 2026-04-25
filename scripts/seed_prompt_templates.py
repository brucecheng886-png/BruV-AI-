#!/usr/bin/env python3
"""
seed_prompt_templates.py — 批次匯入 SKILL.md 句型模板

使用方式（無須 asyncio.run，直接以 httpx 同步呼叫 API）：
    python scripts/seed_prompt_templates.py \
        --base-url http://localhost:8000 \
        --token <JWT>

若容器尚未啟動，可先用 --dry-run 印出 payload 確認內容。
"""
import argparse
import json
import sys

import httpx

# ── 種子資料 ────────────────────────────────────────────────────────────────

TEMPLATES = [
    # 1. code_gen — Copilot 代碼生成格式（源自 AI協作準則 SKILL.md）
    {
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
            "請幫我實作這個功能",
            "生成這個元件的代碼",
            "寫一個 API endpoint",
        ],
        "pit_warnings": [
            "生成超過 100 行代碼前必須逐行閱讀",
            "不理解就直接貼入 AI 生成的代碼是禁止行為",
            "因為 AI 說「應該沒問題」就跳過測試是禁止行為",
        ],
    },

    # 2. debug — 分層診斷格式（源自 debug準則 SKILL.md）
    {
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
            "layer1_hypothesis",
            "layer2_hypothesis",
            "layer3_hypothesis",
            "layer4_hypothesis",
            "canary_test",
            "fix_description",
        ],
        "example_triggers": [
            "遇到 bug",
            "畫面不如預期",
            "API 回傳異常",
            "元件不渲染",
            "數值計算錯誤",
        ],
        "pit_warnings": [
            "禁止看到 bug 就重寫整個函式",
            "禁止同時改多處（無法判斷哪個有效）",
            "禁止用 hardcode 值繞過計算邏輯",
            "禁止跳過 L1/L2 直接猜 L3/L4",
            "不可跳層診斷",
        ],
    },

    # 3. review — Gate 驗收格式（源自 執行準則 SKILL.md）
    {
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
            "Phase 完成確認",
            "代碼提交前自檢",
        ],
        "pit_warnings": [
            "不可跳過驗收閘門直接進入下一 Phase",
            "必須先跑再寫：確認依賴服務已啟動",
        ],
    },

    # 4. phase — 新 Phase 開始格式（源自 執行準則 SKILL.md）
    {
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

    # 5. git — Conventional Commits 格式（源自 git準則 SKILL.md）
    {
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
]

# ── 主程式 ────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="批次匯入 Prompt 模板種子資料")
    p.add_argument("--base-url", default="http://localhost:8000", help="API Base URL")
    p.add_argument("--token", default="", help="JWT Bearer Token（留空則跳過驗證）")
    p.add_argument("--dry-run", action="store_true", help="只印出 payload，不實際呼叫 API")
    return p.parse_args()


def _headers(token: str) -> dict:
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def seed(base_url: str, token: str, dry_run: bool) -> None:
    url = f"{base_url.rstrip('/')}/api/prompt-templates/"
    headers = _headers(token)

    ok = 0
    failed = 0

    with httpx.Client(timeout=30.0) as client:
        for tpl in TEMPLATES:
            if dry_run:
                print(json.dumps(tpl, ensure_ascii=False, indent=2))
                print("---")
                continue

            try:
                resp = client.post(url, headers=headers, json=tpl)
                if resp.status_code == 201:
                    data = resp.json()
                    print(f"[OK] {tpl['category']} / {tpl['title']}  → {data.get('template_id', '')}")
                    ok += 1
                elif resp.status_code == 409:
                    print(f"[SKIP] 已存在：{tpl['title']}")
                    ok += 1
                else:
                    print(
                        f"[FAIL] {tpl['title']} — HTTP {resp.status_code}: {resp.text[:200]}",
                        file=sys.stderr,
                    )
                    failed += 1
            except httpx.RequestError as exc:
                print(f"[ERROR] 連線失敗：{exc}", file=sys.stderr)
                failed += 1

    if not dry_run:
        print(f"\n匯入完成：成功 {ok} 筆，失敗 {failed} 筆。")
        if failed:
            sys.exit(1)


if __name__ == "__main__":
    args = _parse_args()
    seed(args.base_url, args.token, args.dry_run)
