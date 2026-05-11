"""
Prompt Injection Guard

清洗使用者輸入及文件 chunks，防止以下攻擊：
1. Prompt injection（利用角色扮演指令覆蓋 system prompt）
2. Jailbreak patterns（忽略/忘記指令等）
3. 過長重複字元（token flooding 攻擊）
"""
import re
import logging

logger = logging.getLogger(__name__)

# ── 黑名單 patterns（不分大小寫）──────────────────────────────
_INJECTION_PATTERNS: list[re.Pattern] = [
    # 指令覆蓋類
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?previous", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a|an|the)\s+\w", re.IGNORECASE),
    re.compile(r"act\s+as\s+(?:a|an|the)\s+(?:DAN|jailbreak|unrestricted|evil)", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"\[system\]|\[SYSTEM\]|\[System\]"),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    # 繁中常見的 prompt injection 嘗試
    re.compile(r"忽略(所有|之前|前面|上面)的?(指令|命令|設定|規則)", re.IGNORECASE),
    re.compile(r"你現在(是|變成|扮演).{0,20}(沒有|不受|不限)", re.IGNORECASE),
    re.compile(r"(忘記|清除|取消)(所有|之前|你的)(指令|規則|限制)", re.IGNORECASE),
    # Token flooding — 超過 20 個相同字元連續出現
    re.compile(r"(.)\1{20,}"),
]

# 最大 query 長度（超過截斷）
MAX_QUERY_LEN = 4096


def sanitize_query(text: str) -> str:
    """清洗使用者 query，移除或截斷潛在 injection 內容。
    回傳清洗後的字串；若偵測到嚴重注入嘗試，截斷並記錄警告。
    """
    if not text:
        return text

    # 長度截斷
    if len(text) > MAX_QUERY_LEN:
        logger.warning("Query truncated from %d to %d chars", len(text), MAX_QUERY_LEN)
        text = text[:MAX_QUERY_LEN]

    # 逐一檢查 patterns
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            logger.warning("Prompt injection pattern detected: %s ...", text[:80])
            # 不直接拒絕（避免誤判影響正常用戶），而是移除匹配的部分
            text = pattern.sub("[filtered]", text)

    return text.strip()


def sanitize_chunk(text: str) -> str:
    """清洗文件 chunk 內容（注入到 context 前）。
    比 query 更寬鬆：只移除明確的 system prompt 覆蓋指令。
    """
    if not text:
        return text

    # 只移除最危險的 patterns
    dangerous = [
        re.compile(r"\[system\]|\[SYSTEM\]", re.IGNORECASE),
        re.compile(r"<\s*system\s*>.*?<\s*/\s*system\s*>", re.IGNORECASE | re.DOTALL),
        re.compile(r"ignore\s+all\s+previous\s+instructions?", re.IGNORECASE),
    ]
    for pattern in dangerous:
        if pattern.search(text):
            logger.warning("Injection pattern in chunk content, sanitizing")
            text = pattern.sub("[removed]", text)

    return text
