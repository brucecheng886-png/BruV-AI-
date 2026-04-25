"""
Agent Skills Router

GET  /api/agent-skills/          → 列出所有 skill
GET  /api/agent-skills/{page_key} → 取得單一 skill
PATCH /api/agent-skills/{page_key} → 更新 user_prompt / is_enabled
"""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser
from database import get_db

router = APIRouter()


class AgentSkillOut(BaseModel):
    id: str
    page_key: str
    name: str
    user_prompt: str
    is_enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AgentSkillPatch(BaseModel):
    user_prompt: Optional[str] = None
    is_enabled: Optional[bool] = None


@router.get("/", response_model=list[AgentSkillOut])
async def list_skills(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    rows = await db.execute(
        text("SELECT id::text, page_key, name, user_prompt, is_enabled, created_at, updated_at FROM agent_skills ORDER BY page_key")
    )
    return [
        AgentSkillOut(
            id=r.id,
            page_key=r.page_key,
            name=r.name,
            user_prompt=r.user_prompt or "",
            is_enabled=r.is_enabled,
            created_at=r.created_at.isoformat() if r.created_at else None,
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
        )
        for r in rows.fetchall()
    ]


@router.get("/{page_key}", response_model=AgentSkillOut)
async def get_skill(
    page_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    row = (await db.execute(
        text("SELECT id::text, page_key, name, user_prompt, is_enabled, created_at, updated_at FROM agent_skills WHERE page_key = :pk"),
        {"pk": page_key},
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Skill not found")
    return AgentSkillOut(
        id=row.id,
        page_key=row.page_key,
        name=row.name,
        user_prompt=row.user_prompt or "",
        is_enabled=row.is_enabled,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


@router.patch("/{page_key}", response_model=AgentSkillOut)
async def update_skill(
    page_key: str,
    body: AgentSkillPatch,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    # 確認存在
    existing = (await db.execute(
        text("SELECT id FROM agent_skills WHERE page_key = :pk"),
        {"pk": page_key},
    )).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Skill not found")

    sets = []
    params: dict = {"pk": page_key, "now": datetime.utcnow()}
    if body.user_prompt is not None:
        sets.append("user_prompt = :user_prompt")
        params["user_prompt"] = body.user_prompt
    if body.is_enabled is not None:
        sets.append("is_enabled = :is_enabled")
        params["is_enabled"] = body.is_enabled
    if sets:
        sets.append("updated_at = :now")
        await db.execute(
            text(f"UPDATE agent_skills SET {', '.join(sets)} WHERE page_key = :pk"),
            params,
        )
        await db.commit()

    return await get_skill(page_key, db, current_user)
