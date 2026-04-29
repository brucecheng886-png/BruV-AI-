"""E4：對話標題生成 prompt。"""


def TITLE_GEN_PROMPT(first_message: str) -> str:
    """產生對話標題的 user message。

    參數：first_message — 使用者第一則訊息（已 trim）
    回傳：可直接放入 messages payload 的 user content
    """
    safe = (first_message or "").strip()
    return (
        "請依使用者第一個問題，產生一個 6-12 字的繁體中文對話標題。要求：\n"
        "- 不加標點、不加引號\n"
        "- 動詞開頭或名詞片語\n"
        "- 不得含「對話」「問題」「請求」等空泛詞\n\n"
        f"問題：{safe}\n"
        "標題："
    )
