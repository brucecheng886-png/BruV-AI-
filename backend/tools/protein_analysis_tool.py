"""
protein_analysis_tool — LangChain Tool wrapper for protein interaction analysis.

Actions (JSON input):
  stats   → GET /api/protein/stats      (weight distribution statistics)
  graph   → GET /api/protein/graph      (graph nodes + edges)
  top     → GET /api/protein/top        (top interactions by score)
"""
import json
import logging

import httpx
from langchain.tools import Tool

from config import settings

logger = logging.getLogger(__name__)

_BASE = f"http://localhost:{getattr(settings, 'PORT', 8000)}"


def _call(action: str, payload: dict) -> str:
    try:
        with httpx.Client(base_url=_BASE, timeout=30) as client:
            network = payload.get("network", "")
            if not network:
                return json.dumps({"error": "network 為必填，例如 'USP7' 或 'STRING'"})

            threshold = float(payload.get("threshold", payload.get("min_score", 0.5)))

            if action == "stats":
                resp = client.get(
                    "/api/protein/stats",
                    params={"network": network, "threshold": threshold},
                )
                resp.raise_for_status()
                return json.dumps(resp.json(), ensure_ascii=False)

            elif action == "graph":
                limit = int(payload.get("limit", 200))
                resp = client.get(
                    "/api/protein/graph",
                    params={"network": network, "min_score": threshold, "limit": limit},
                )
                resp.raise_for_status()
                data = resp.json()
                # 摘要化輸出，避免回傳過大
                summary = {
                    "node_count": len(data.get("nodes", [])),
                    "edge_count": len(data.get("links", [])),
                    "sample_nodes": [n["name"] for n in data.get("nodes", [])[:10]],
                }
                return json.dumps(summary, ensure_ascii=False)

            elif action == "top":
                limit = int(payload.get("limit", 20))
                resp = client.get(
                    "/api/protein/top",
                    params={"network": network, "limit": limit},
                )
                resp.raise_for_status()
                return json.dumps(resp.json(), ensure_ascii=False)

            else:
                return json.dumps({"error": f"不支援的 action: {action}，可用：stats, graph, top"})

    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"})
    except Exception as e:
        logger.error("protein_analysis_tool error: %s", e, exc_info=True)
        return json.dumps({"error": str(e)})


def _run(raw_input: str) -> str:
    try:
        data = json.loads(raw_input)
    except json.JSONDecodeError:
        return json.dumps({"error": "輸入必須是 JSON 格式，例如: {\"action\":\"stats\",\"network\":\"USP7\"}"})

    action = data.get("action", "stats")
    return _call(action, data)


def build_protein_analysis_tool() -> Tool:
    return Tool(
        name="protein_analysis",
        func=_run,
        description=(
            "分析蛋白質互作網路，查詢統計數據、圖譜節點或高分互作列表。"
            "輸入：JSON 字串，包含 action 欄位（stats、graph 或 top）。\n"
            "- stats：查詢評分分布統計，需填 network、threshold（可選，預設 0.5）。\n"
            "  範例：{\"action\":\"stats\",\"network\":\"USP7\",\"threshold\":0.4}\n"
            "  回傳：total_edges, mean_score, p50, p75, p90, distribution 等統計數據。\n"
            "- graph：取得圖譜節點與邊，需填 network，可選 threshold、limit（預設 200）。\n"
            "  範例：{\"action\":\"graph\",\"network\":\"USP7\",\"threshold\":0.7,\"limit\":100}\n"
            "  回傳：node_count, edge_count, sample_nodes（前 10 個節點名稱）。\n"
            "- top：取得評分最高的互作對，需填 network，可選 limit（預設 20）。\n"
            "  範例：{\"action\":\"top\",\"network\":\"USP7\",\"limit\":10}\n"
            "  回傳：interactions 陣列，每筆含 protein_a, protein_b, score。"
        ),
    )
