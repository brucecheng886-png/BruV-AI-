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


# ── 內建可安裝 Skill 清單 ────────────────────────────────────
AVAILABLE_SKILLS: list[dict] = [
    {
        "page_key": "kb",
        "name": "知識庫助理",
        "description": "在知識庫頁面協助搜尋與整理文件",
        "default_prompt": "你是知識庫助理。你可以幫助使用者：\n- 搜尋知識庫文件\n- 回答知識庫相關問題\n- 協助整理和分類文件\n\n回答時請簡潔明確，優先使用繁體中文。",
    },
    {
        "page_key": "docs",
        "name": "文件管理助理",
        "description": "協助批次上傳、分類、標籤管理",
        "default_prompt": "你是文件管理助理，協助使用者批次上傳、整理檔案標籤與分類。",
    },
    {
        "page_key": "chat",
        "name": "對話助理",
        "description": "聊天頁的通用助理",
        "default_prompt": "你是通用對話助理，請使用繁體中文簡潔回答。",
    },
    {
        "page_key": "wiki",
        "name": "Wiki 編輯助理",
        "description": "協助撰寫與編修 Wiki 條目",
        "default_prompt": "你是 Wiki 編輯助理，協助使用者撰寫、潤飾條目，並提供結構化建議。",
    },
    {
        "page_key": "ontology",
        "name": "知識圖譜助理",
        "description": "協助建立實體與關係",
        "default_prompt": "你是知識圖譜助理，協助使用者抽取實體、關係並回答圖譜查詢。",
    },
]


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


# ── Skill Store ─────────────────────────────────────────────

@router.get("/store/available")
async def list_available_skills(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    """列出所有可安裝的 skill，並標註是否已安裝。"""
    rows = await db.execute(text("SELECT page_key FROM agent_skills"))
    installed_keys = {r.page_key for r in rows.fetchall()}
    return [
        {
            "page_key": s["page_key"],
            "name": s["name"],
            "description": s["description"],
            "default_prompt": s["default_prompt"],
            "installed": s["page_key"] in installed_keys,
        }
        for s in AVAILABLE_SKILLS
    ]


class InstallSkillIn(BaseModel):
    page_key: str


@router.post("/store/install", response_model=AgentSkillOut)
async def install_skill(
    body: InstallSkillIn,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    spec = next((s for s in AVAILABLE_SKILLS if s["page_key"] == body.page_key), None)
    if not spec:
        raise HTTPException(status_code=404, detail="該 skill 不在可安裝清單中")
    await db.execute(
        text(
            "INSERT INTO agent_skills (page_key, name, user_prompt, is_enabled) "
            "VALUES (:pk, :nm, :up, TRUE) "
            "ON CONFLICT (page_key) DO UPDATE SET is_enabled = TRUE"
        ),
        {"pk": spec["page_key"], "nm": spec["name"], "up": spec["default_prompt"]},
    )
    await db.commit()
    return await get_skill(spec["page_key"], db, current_user)


@router.delete("/store/{page_key}", status_code=204)
async def uninstall_skill(
    page_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    existing = (await db.execute(
        text("SELECT id FROM agent_skills WHERE page_key = :pk"),
        {"pk": page_key},
    )).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Skill not found")
    await db.execute(
        text("DELETE FROM agent_skills WHERE page_key = :pk"),
        {"pk": page_key},
    )
    await db.commit()
