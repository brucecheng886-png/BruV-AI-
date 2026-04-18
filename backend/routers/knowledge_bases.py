"""
知識庫 Router — CRUD
"""
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser
from database import get_db
from models import KnowledgeBase, Document

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────

class KBIn(BaseModel):
    name: str
    description: str | None = None
    color: str = "#2563eb"
    icon: str = "📚"


class KBOut(BaseModel):
    id: str
    name: str
    description: str | None
    color: str
    icon: str
    doc_count: int
    created_at: str


# ── Endpoints ─────────────────────────────────────────────────

@router.get("", response_model=list[KBOut])
async def list_knowledge_bases(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(KnowledgeBase).order_by(KnowledgeBase.created_at))
    kbs = result.scalars().all()
    out = []
    for kb in kbs:
        count_result = await db.execute(
            select(func.count()).select_from(Document).where(Document.knowledge_base_id == kb.id)
        )
        doc_count = count_result.scalar() or 0
        out.append(KBOut(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            color=kb.color or "#2563eb",
            icon=kb.icon or "📚",
            doc_count=doc_count,
            created_at=kb.created_at.isoformat(),
        ))
    return out


@router.post("", response_model=KBOut, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    body: KBIn,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    kb = KnowledgeBase(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        color=body.color,
        icon=body.icon,
        created_by=current_user.id if current_user else None,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return KBOut(
        id=kb.id, name=kb.name, description=kb.description,
        color=kb.color or "#2563eb", icon=kb.icon or "📚",
        doc_count=0, created_at=kb.created_at.isoformat(),
    )


@router.put("/{kb_id}", response_model=KBOut)
async def update_knowledge_base(
    kb_id: str,
    body: KBIn,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="找不到知識庫")
    kb.name = body.name
    kb.description = body.description
    kb.color = body.color
    kb.icon = body.icon
    await db.commit()
    await db.refresh(kb)
    count_result = await db.execute(
        select(func.count()).select_from(Document).where(Document.knowledge_base_id == kb.id)
    )
    doc_count = count_result.scalar() or 0
    return KBOut(
        id=kb.id, name=kb.name, description=kb.description,
        color=kb.color or "#2563eb", icon=kb.icon or "📚",
        doc_count=doc_count, created_at=kb.created_at.isoformat(),
    )


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    kb_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="找不到知識庫")
    await db.delete(kb)
    await db.commit()
