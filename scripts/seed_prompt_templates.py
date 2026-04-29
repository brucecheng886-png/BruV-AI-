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

    # ── E5：使用者面向模板批次（12 個）──────────────────────────

    # 6. writing — 文章撰寫
    {
        "category": "writing",
        "title": "文章撰寫",
        "template": (
            "## 角色\n你是專業文字工作者。\n\n"
            "## 任務\n為主題「{topic}」撰寫一篇文章。\n\n"
            "## 限制\n"
            "- 對象：{audience}\n"
            "- 語氣：{tone}\n"
            "- 字數：約 {length} 字（預設 600）\n"
            "- 不杜撰數據、人名、引文\n\n"
            "## 格式\n標題 + 引言 + 主體（小標題分段）+ 結語\n\n"
            "## 範例風格\n清晰、結構化、有具體例子"
        ),
        "required_vars": ["topic", "audience", "tone"],
        "optional_vars": ["length"],
        "example_triggers": ["寫一篇", "撰寫", "產生文章"],
        "pit_warnings": ["不可虛構數據或引用", "避免空話與套語"],
    },
    # 7. writing — 改寫潤稿
    {
        "category": "writing",
        "title": "改寫潤稿",
        "template": (
            "## 任務\n請將下列文字依「{style}」風格改寫，保留原意，不增刪事實。\n\n"
            "## 原文\n{original_text}\n\n"
            "## 輸出\n只給改寫後的文字，無前言"
        ),
        "required_vars": ["original_text", "style"],
        "optional_vars": [],
        "example_triggers": ["改寫", "潤稿", "修飾"],
        "pit_warnings": ["不得新增原文未提及的事實", "保留專有名詞拼寫"],
    },
    # 8. writing — 摘要
    {
        "category": "writing",
        "title": "摘要",
        "template": (
            "## 任務\n為下列內容產生摘要，長度約 {length} 字（預設 150）。\n\n"
            "## 來源\n{source_text}\n\n"
            "## 規則\n"
            "- 用客觀第三人稱\n"
            "- 不加自身評論\n"
            "- 條列式優先；單一概念用一句話"
        ),
        "required_vars": ["source_text"],
        "optional_vars": ["length"],
        "example_triggers": ["摘要", "簡述", "總結"],
        "pit_warnings": ["不得加入個人意見或詮釋", "不得遺漏關鍵數字 / 結論"],
    },
    # 9. translate — 中英翻譯
    {
        "category": "translate",
        "title": "中英翻譯",
        "template": (
            "## 任務\n請將下列文字翻譯為「{target_lang}」。\n\n"
            "## 原文\n{source_text}\n\n"
            "## 規則\n"
            "- 保留專有名詞、程式碼、URL 不譯\n"
            "- 數字與單位保留原格式\n"
            "- 只給譯文，無說明"
        ),
        "required_vars": ["source_text", "target_lang"],
        "optional_vars": [],
        "example_triggers": ["翻譯成", "翻成", "translate"],
        "pit_warnings": ["不得意譯導致原意流失", "代碼與 URL 不譯"],
    },
    # 10. analysis — 資料分析洞察
    {
        "category": "analysis",
        "title": "資料分析洞察",
        "template": (
            "## 任務\n依下列資料描述回答問題。\n\n"
            "## 資料描述\n{data_description}\n\n"
            "## 問題\n{question}\n\n"
            "## 規則\n"
            "- 區分「事實（資料中可見）」與「推論（基於資料的解讀）」\n"
            "- 推論前必須先列出依據\n"
            "- 若資料不足以回答，明說「資料不足」並建議補哪些欄位\n"
            "- 用條列 + 必要時加表格"
        ),
        "required_vars": ["data_description", "question"],
        "optional_vars": [],
        "example_triggers": ["分析", "解讀", "找出規律"],
        "pit_warnings": ["禁止編造資料中不存在的數值", "推論必須附依據"],
    },
    # 11. analysis — 比較對照
    {
        "category": "analysis",
        "title": "比較對照",
        "template": (
            "## 任務\n比較 {item_a} 與 {item_b}。\n\n"
            "## 比較維度\n{dimensions}\n\n"
            "## 輸出\n"
            "1. 用表格呈現各維度對照\n"
            "2. 表格下方給「適用情境」建議（各 1-2 句）\n"
            "3. 不偏袒任何一方"
        ),
        "required_vars": ["item_a", "item_b", "dimensions"],
        "optional_vars": [],
        "example_triggers": ["比較", "對比", "差異"],
        "pit_warnings": ["不得有選擇性偏袒", "事實必須可核實"],
    },
    # 12. analysis — SWOT 分析
    {
        "category": "analysis",
        "title": "SWOT 分析",
        "template": (
            "## 任務\n為「{subject}」做 SWOT 分析。\n\n"
            "## 輸出（嚴格依序）\n"
            "**Strengths（優勢）**\n- ...\n\n"
            "**Weaknesses（劣勢）**\n- ...\n\n"
            "**Opportunities（機會）**\n- ...\n\n"
            "**Threats（威脅）**\n- ...\n\n"
            "每個象限至少 3 項，避免空泛敘述。"
        ),
        "required_vars": ["subject"],
        "optional_vars": [],
        "example_triggers": ["SWOT", "優劣勢"],
        "pit_warnings": ["每項必須具體，不可寫「品質好」這類無資訊量描述"],
    },
    # 13. extract — 重點擷取
    {
        "category": "extract",
        "title": "重點擷取",
        "template": (
            "## 任務\n從下列文字擷取重點。\n\n"
            "## 來源\n{source_text}\n\n"
            "## 輸出\n"
            "- 條列式 5-10 點\n"
            "- 每點不超過 25 字\n"
            "- 重要數字 / 結論用 **粗體**\n"
            "- 按重要性排序"
        ),
        "required_vars": ["source_text"],
        "optional_vars": [],
        "example_triggers": ["擷取重點", "抓重點"],
        "pit_warnings": ["不得添加原文沒有的內容"],
    },
    # 14. extract — 關鍵字標籤
    {
        "category": "extract",
        "title": "關鍵字標籤",
        "template": (
            "## 任務\n為下列內容產生標籤（最多 {max_tags} 個，預設 8）。\n\n"
            "## 來源\n{source_text}\n\n"
            "## 規則\n"
            "- 每個標籤 1-4 字\n"
            "- 涵蓋：主題、領域、實體、動作\n"
            "- 輸出：以逗號分隔的單行字串，無其他說明"
        ),
        "required_vars": ["source_text"],
        "optional_vars": ["max_tags"],
        "example_triggers": ["產生標籤", "抽關鍵字"],
        "pit_warnings": ["標籤不可太抽象（例：好、重要）", "避免重複同義詞"],
    },
    # 15. code — 程式解說
    {
        "category": "code",
        "title": "程式解說",
        "template": (
            "## 任務\n用繁體中文解說下列 {language} 程式碼。\n\n"
            "## 代碼\n```\n{code}\n```\n\n"
            "## 輸出\n"
            "1. 一句話總結這段做什麼\n"
            "2. 依序解說每個邏輯區塊（用條列）\n"
            "3. 指出潛在問題或可改進處（若有）\n"
            "4. 範例輸入 / 輸出（若可）"
        ),
        "required_vars": ["code", "language"],
        "optional_vars": [],
        "example_triggers": ["解釋這段", "這段做什麼"],
        "pit_warnings": ["不得編造代碼未涉及的副作用"],
    },
    # 16. code — 程式重構建議
    {
        "category": "code",
        "title": "程式重構建議",
        "template": (
            "## 任務\n為下列代碼提出重構建議，目標：{goal}。\n\n"
            "## 代碼\n```\n{code}\n```\n\n"
            "## 輸出\n"
            "1. 現況問題分析（條列）\n"
            "2. 重構後代碼（完整，可直接替換）\n"
            "3. 改動摘要（一句話）\n"
            "4. 風險：哪些行為可能改變、需測哪些測試\n\n"
            "## 規則\n"
            "- 不引入新依賴除非必要\n"
            "- 保留原 public API"
        ),
        "required_vars": ["code", "goal"],
        "optional_vars": [],
        "example_triggers": ["重構", "優化此代碼"],
        "pit_warnings": ["重構不得改變對外行為", "必須註明風險"],
    },
    # 17. qa — 蘇格拉底式追問
    {
        "category": "qa",
        "title": "蘇格拉底式追問",
        "template": (
            "## 任務\n針對下列主張進行蘇格拉底式追問，協助釐清思考。\n\n"
            "## 主張\n{claim}\n\n"
            "## 輸出\n"
            "依序提出 5 個問題，逐步深入：\n"
            "1. 定義（這個主張中關鍵詞的精確定義是？）\n"
            "2. 證據（支持的證據有哪些？來源可靠嗎？）\n"
            "3. 反例（在什麼情境下會不成立？）\n"
            "4. 假設（隱含的前提是什麼？）\n"
            "5. 後果（若成立會推導出什麼？合理嗎？）\n\n"
            "## 規則\n只提問，不下結論"
        ),
        "required_vars": ["claim"],
        "optional_vars": [],
        "example_triggers": ["反思", "質疑", "為什麼"],
        "pit_warnings": ["不得帶入答案", "不得針對提主張的人攻擊"],
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
