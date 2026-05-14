"""
知識庫 Router — CRUD
"""
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, CurrentAdmin
from database import get_db
from models import KnowledgeBase, Document, DocumentKnowledgeBase, Chunk, KBPermission, User

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────

class KBIn(BaseModel):
    name: str
    description: str | None = None
    color: str = "#2563eb"
    icon: str = "📚"
    embedding_model: str | None = None
    embedding_provider: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    language: str | None = "auto"
    rerank_enabled: bool | None = None
    default_top_k: int | None = None
    agent_prompt: str | None = None


class KBOut(BaseModel):
    id: str
    name: str
    description: str | None
    color: str
    icon: str
    doc_count: int
    created_at: str
    embedding_model: str | None = None
    embedding_provider: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    language: str | None = None
    rerank_enabled: bool | None = None
    default_top_k: int | None = None
    agent_prompt: str | None = None


# ── Endpoints ─────────────────────────────────────────────────

def _kb_to_out(kb: KnowledgeBase, doc_count: int) -> KBOut:
    return KBOut(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        color=kb.color or "#2563eb",
        icon=kb.icon or "📚",
        doc_count=doc_count,
        created_at=kb.created_at.isoformat(),
        embedding_model=kb.embedding_model,
        embedding_provider=kb.embedding_provider,
        chunk_size=kb.chunk_size,
        chunk_overlap=kb.chunk_overlap,
        language=kb.language,
        rerank_enabled=kb.rerank_enabled,
        default_top_k=kb.default_top_k,
        agent_prompt=kb.agent_prompt,
    )


@router.get("", response_model=list[KBOut])
@router.get("/", response_model=list[KBOut], include_in_schema=False)
async def list_knowledge_bases(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(KnowledgeBase).order_by(KnowledgeBase.created_at))
    kbs = result.scalars().all()

    # 非 admin 只能看授權的 KB
    if current_user and current_user.role != "admin":
        perm_result = await db.execute(
            select(KBPermission.kb_id).where(KBPermission.user_id == current_user.id)
        )
        permitted = {row[0] for row in perm_result.all()}
        kbs = [kb for kb in kbs if kb.id in permitted]
    out = []
    for kb in kbs:
        count_result = await db.execute(
            select(func.count()).select_from(DocumentKnowledgeBase)
            .where(DocumentKnowledgeBase.kb_id == kb.id)
        )
        doc_count = count_result.scalar() or 0
        out.append(_kb_to_out(kb, doc_count))
    return out


@router.get("/{kb_id}", response_model=KBOut)
async def get_knowledge_base(
    kb_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="找不到知識庫")
    count_result = await db.execute(
        select(func.count()).select_from(DocumentKnowledgeBase)
        .where(DocumentKnowledgeBase.kb_id == kb.id)
    )
    doc_count = count_result.scalar() or 0
    return _kb_to_out(kb, doc_count)


@router.get("/{kb_id}/stats")
async def get_knowledge_base_stats(
    kb_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="找不到知識庫")

    doc_count_q = await db.execute(
        select(func.count()).select_from(DocumentKnowledgeBase)
        .where(DocumentKnowledgeBase.kb_id == kb_id)
    )
    doc_count = doc_count_q.scalar() or 0

    chunk_count_q = await db.execute(
        select(func.count()).select_from(Chunk)
        .join(DocumentKnowledgeBase, DocumentKnowledgeBase.doc_id == Chunk.doc_id)
        .where(DocumentKnowledgeBase.kb_id == kb_id)
    )
    chunk_count = chunk_count_q.scalar() or 0

    last_q = await db.execute(
        select(func.max(Document.updated_at))
        .join(DocumentKnowledgeBase, DocumentKnowledgeBase.doc_id == Document.id)
        .where(DocumentKnowledgeBase.kb_id == kb_id)
    )
    last_updated = last_q.scalar()

    return {
        "doc_count": doc_count,
        "chunk_count": chunk_count,
        "last_updated": last_updated.isoformat() if last_updated else None,
    }


@router.post("", response_model=KBOut, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=KBOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
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
        embedding_model=body.embedding_model,
        embedding_provider=body.embedding_provider,
        chunk_size=body.chunk_size,
        chunk_overlap=body.chunk_overlap,
        language=body.language or "auto",
        rerank_enabled=body.rerank_enabled,
        default_top_k=body.default_top_k,
        agent_prompt=body.agent_prompt,
        created_by=current_user.id if current_user else None,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return _kb_to_out(kb, 0)


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
    kb.embedding_model = body.embedding_model
    kb.embedding_provider = body.embedding_provider
    kb.chunk_size = body.chunk_size
    kb.chunk_overlap = body.chunk_overlap
    kb.language = body.language or "auto"
    kb.rerank_enabled = body.rerank_enabled
    kb.default_top_k = body.default_top_k
    kb.agent_prompt = body.agent_prompt
    await db.commit()
    await db.refresh(kb)
    count_result = await db.execute(
        select(func.count()).select_from(DocumentKnowledgeBase)
        .where(DocumentKnowledgeBase.kb_id == kb.id)
    )
    doc_count = count_result.scalar() or 0
    return _kb_to_out(kb, doc_count)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    kb_id: str,
    current_user: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="找不到知識庫")
    await db.delete(kb)
    await db.commit()


# ── KB 權限管理 ─────────────────────────────────────────────────

class PermissionIn(BaseModel):
    user_id: str
    permission: str = "read"  # "read" | "write"


class PermissionOut(BaseModel):
    user_id: str
    email: str
    display_name: str | None
    permission: str
    granted_at: str


@router.get("/{kb_id}/permissions", response_model=list[PermissionOut])
async def list_kb_permissions(
    kb_id: str,
    current_user: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
):
    """列出有此 KB 存取權的使用者"""
    result = await db.execute(
        select(KBPermission, User)
        .join(User, User.id == KBPermission.user_id)
        .where(KBPermission.kb_id == kb_id)
        .order_by(KBPermission.granted_at)
    )
    rows = result.all()
    return [
        PermissionOut(
            user_id=perm.user_id,
            email=user.email,
            display_name=user.display_name,
            permission=perm.permission,
            granted_at=perm.granted_at.isoformat(),
        )
        for perm, user in rows
    ]


@router.post("/{kb_id}/permissions", status_code=status.HTTP_201_CREATED)
async def grant_kb_permission(
    kb_id: str,
    body: PermissionIn,
    current_user: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
):
    """授予使用者對此 KB 的存取權"""
    kb = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))).scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="找不到知識庫")
    user = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="使用者不存在")

    existing = (await db.execute(
        select(KBPermission)
        .where(KBPermission.kb_id == kb_id, KBPermission.user_id == body.user_id)
    )).scalar_one_or_none()
    if existing:
        existing.permission = body.permission
    else:
        db.add(KBPermission(
            kb_id=kb_id,
            user_id=body.user_id,
            permission=body.permission,
            granted_by=current_user.id,
        ))
    await db.commit()
    return {"success": True}


@router.delete("/{kb_id}/permissions/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_kb_permission(
    kb_id: str,
    user_id: str,
    current_user: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
):
    """撤銷使用者對此 KB 的存取權"""
    perm = (await db.execute(
        select(KBPermission)
        .where(KBPermission.kb_id == kb_id, KBPermission.user_id == user_id)
    )).scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=404, detail="權限不存在")
    await db.delete(perm)
    await db.commit()
