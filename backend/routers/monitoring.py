"""
Phase B6: LLM 使用量查詢端點
GET /api/monitoring/usage — 依日期範圍 / user / model 聚合
GET /api/monitoring/usage/daily — 每日明細（給前端折線圖）
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser
from database import get_db

router = APIRouter()


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


@router.get("/usage")
async def get_usage_summary(
    start: Optional[str] = Query(None, description="ISO date, e.g. 2026-04-01"),
    end:   Optional[str] = Query(None, description="ISO date, exclusive"),
    user_id: Optional[str] = Query(None),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """依模型聚合：呼叫次數 / 平均延遲 / 總 tokens / 估算成本"""
    start_dt = _parse_date(start) or (datetime.now(timezone.utc) - timedelta(days=30))
    end_dt   = _parse_date(end)   or (datetime.now(timezone.utc) + timedelta(days=1))

    where_parts = ["created_at >= :start", "created_at < :end"]
    params: dict = {"start": start_dt, "end": end_dt}
    if user_id:
        where_parts.append("user_id = :uid")
        params["uid"] = user_id

    sql = (
        "SELECT model_name, provider, "
        "COUNT(*) AS calls, "
        "SUM(CASE WHEN success THEN 1 ELSE 0 END) AS success_calls, "
        "SUM(prompt_tokens) AS prompt_tokens, "
        "SUM(completion_tokens) AS completion_tokens, "
        "SUM(total_tokens) AS total_tokens, "
        "AVG(latency_ms)::INT AS avg_latency_ms, "
        "SUM(COALESCE(cost_usd, 0))::NUMERIC(12,6) AS cost_usd "
        "FROM llm_usage_log "
        f"WHERE {' AND '.join(where_parts)} "
        "GROUP BY model_name, provider "
        "ORDER BY calls DESC"
    )
    rows = (await db.execute(sql_text(sql), params)).fetchall()
    items = [
        {
            "model_name": r[0],
            "provider": r[1],
            "calls": int(r[2] or 0),
            "success_calls": int(r[3] or 0),
            "prompt_tokens": int(r[4] or 0),
            "completion_tokens": int(r[5] or 0),
            "total_tokens": int(r[6] or 0),
            "avg_latency_ms": int(r[7] or 0),
            "cost_usd": float(r[8] or 0),
        }
        for r in rows
    ]
    totals = {
        "calls": sum(it["calls"] for it in items),
        "total_tokens": sum(it["total_tokens"] for it in items),
        "cost_usd": round(sum(it["cost_usd"] for it in items), 6),
    }
    return {"start": start_dt.isoformat(), "end": end_dt.isoformat(), "items": items, "totals": totals}


@router.get("/usage/daily")
async def get_usage_daily(
    days: int = Query(30, ge=1, le=180),
    user_id: Optional[str] = Query(None),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """最近 N 天每日使用量（給折線圖）"""
    end_dt = datetime.now(timezone.utc) + timedelta(days=1)
    start_dt = end_dt - timedelta(days=days + 1)

    where_parts = ["created_at >= :start", "created_at < :end"]
    params: dict = {"start": start_dt, "end": end_dt}
    if user_id:
        where_parts.append("user_id = :uid")
        params["uid"] = user_id

    sql = (
        "SELECT DATE(created_at AT TIME ZONE 'UTC') AS day, "
        "COUNT(*) AS calls, "
        "SUM(total_tokens) AS total_tokens, "
        "SUM(COALESCE(cost_usd, 0))::NUMERIC(12,6) AS cost_usd "
        "FROM llm_usage_log "
        f"WHERE {' AND '.join(where_parts)} "
        "GROUP BY day ORDER BY day ASC"
    )
    rows = (await db.execute(sql_text(sql), params)).fetchall()
    return {
        "days": days,
        "items": [
            {
                "date": r[0].isoformat() if r[0] else None,
                "calls": int(r[1] or 0),
                "total_tokens": int(r[2] or 0),
                "cost_usd": float(r[3] or 0),
            }
            for r in rows
        ],
    }
