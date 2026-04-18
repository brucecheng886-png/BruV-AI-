"""
Re-ranker 服務（CPU 推理，backend 容器內）
模型：BAAI/bge-reranker-large
"""
import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

_reranker_instance = None


class Reranker:
    def __init__(self):
        logger.info("Loading BGE-reranker-large (CPU)...")
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        import torch

        self.tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-reranker-large")
        self.model = AutoModelForSequenceClassification.from_pretrained(
            "BAAI/bge-reranker-large"
        )
        self.model.eval()
        self._torch = torch
        logger.info("Re-ranker loaded.")

    def rerank(self, query: str, passages: list[str], top_k: int = 5) -> list[int]:
        """回傳排序後的 index 列表（最相關在前）"""
        if not passages:
            return []

        pairs = [[query, p] for p in passages]
        with self._torch.no_grad():
            inputs = self.tokenizer(
                pairs,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            scores = self.model(**inputs).logits.squeeze(-1)

        ranked = scores.argsort(descending=True).tolist()
        return ranked[:top_k]


async def get_reranker() -> Reranker:
    """單例：只在首次呼叫時載入模型"""
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = Reranker()
    return _reranker_instance
