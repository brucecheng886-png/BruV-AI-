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
from models import KnowledgeBase, Document, DocumentKnowledgeBase, Chunk

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
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="找不到知識庫")
    await db.delete(kb)
    await db.commit()
