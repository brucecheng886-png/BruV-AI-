"""E2：Reflection Judge prompt（Phase C2 Chat Reflection 用）。"""

# 觸發重生的閾值：total < THRESHOLD 或 should_regenerate == True
REFLECTION_TOTAL_THRESHOLD = 6


def REFLECTION_JUDGE_PROMPT(question: str, context: str, answer: str) -> str:
    """組裝 reflection judge 的 user message。

    judge LLM 回傳純 JSON，呼叫端負責解析。
    """
    q = (question or "").strip()
    c = (context or "").strip()
    a = (answer or "").strip()
    return (
        "你是一個 AI 回答品質評審。給定「使用者問題」、「參考資料」、「AI 回答」，"
        "請依下列五個維度打分（0-2）：\n\n"
        "1. relevance（切題）：回答是否回應使用者真正的問題\n"
        "2. grounded（有據）：回答中的事實是否都能在參考資料中找到\n"
        "3. completeness（完整）：是否涵蓋問題的關鍵面向\n"
        "4. clarity（清晰）：結構、用字是否易懂\n"
        "5. citation（引用）：是否依規則標註 [#N]\n\n"
        "請只輸出 JSON，不得有其他文字：\n"
        "{\n"
        '  "scores": {"relevance": 0, "grounded": 0, "completeness": 0, "clarity": 0, "citation": 0},\n'
        '  "total": 0,\n'
        '  "issues": ["具體問題1", "具體問題2"],\n'
        '  "should_regenerate": false,\n'
        '  "regenerate_hint": ""\n'
        "}\n\n"
        "判定 should_regenerate=true 的條件（任一）：\n"
        "- grounded < 2（有編造）\n"
        "- relevance == 0（完全跑題）\n"
        f"- total < {REFLECTION_TOTAL_THRESHOLD}\n\n"
        f"=== 使用者問題 ===\n{q}\n\n"
        f"=== 參考資料 ===\n{c}\n\n"
        f"=== AI 回答 ===\n{a}\n"
    )
