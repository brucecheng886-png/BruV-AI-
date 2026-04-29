"""E3：Agent self-critique prompt（Phase C3 用）。"""


def AGENT_REFLECTION_PROMPT(goal: str, steps_log: str) -> str:
    """組裝 agent self-critique 的 user message。

    參數：
      goal       — agent 的最終目標
      steps_log  — 已執行步驟的文字記錄（含 thought / action / observation）

    回傳：純 JSON 字串，呼叫端解析後依 next_action 執行。
    """
    g = (goal or "").strip()
    s = (steps_log or "").strip()
    return (
        "你是 Agent 監督員。以下是某 Agent 為達成目標已執行的步驟記錄：\n\n"
        f"目標：{g}\n"
        f"已執行步驟：\n{s}\n\n"
        "請評估並只輸出 JSON：\n"
        "{\n"
        '  "on_track": false,\n'
        '  "wasted_steps": 0,\n'
        '  "diagnosis": "簡述目前進度與卡點",\n'
        '  "next_action": "continue",\n'
        '  "strategy_hint": ""\n'
        "}\n\n"
        "next_action 可選值：continue | switch_strategy | abort\n\n"
        "判定原則：\n"
        "- 連續 2 步以上 observation 無新資訊 → switch_strategy\n"
        "- 同一 tool 連續呼叫 3 次失敗 → switch_strategy\n"
        "- 已達目標 → abort（含 reason=\"completed\"）\n"
        "- 步驟數已超過 max_iterations 80% 但仍無進展 → abort\n"
    )
