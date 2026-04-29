"""集中管理 LLM prompt 常數。

每個 prompt 模組對應一個用途，便於 unit test、版本化與 A/B 測試。
"""

from .rag_system import RAG_SYSTEM_PROMPT
from .title_gen import TITLE_GEN_PROMPT
from .reflection_judge import REFLECTION_JUDGE_PROMPT, REFLECTION_TOTAL_THRESHOLD
from .agent_reflection import AGENT_REFLECTION_PROMPT
from .system_messages import EMBEDDING_FALLBACK_NOTICE

__all__ = [
    "RAG_SYSTEM_PROMPT",
    "TITLE_GEN_PROMPT",
    "REFLECTION_JUDGE_PROMPT",
    "REFLECTION_TOTAL_THRESHOLD",
    "AGENT_REFLECTION_PROMPT",
    "EMBEDDING_FALLBACK_NOTICE",
]
