"""
Tags Router — tag CRUD + 文件貼標籤 / 移除標籤
"""
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser
from database import get_db
from models import DocumentTag, Tag, Document

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class TagCreate(BaseModel):
    name: str
    color: str = "#409eff"
    description: Optional[str] = None
    parent_id: Optional[str] = None


class TagUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None


class TagOut(BaseModel):
    id: str
    name: str
    slug: str
    color: str
    description: Optional[str]
    parent_id: Optional[str]
    doc_count: int

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_slug(name: str) -> str:
    """將 name 轉為 slug：英文小寫 + hyphen，中文保留原字。"""
    slug = name.strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^\w\u4e00-\u9fff-]", "", slug)
    return slug


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[TagOut])
async def list_tags(db: AsyncSession = Depends(get_db)):
    """列出所有 tags，含每個 tag 的文件數量。"""
    result = await db.execute(select(Tag))
    tags = result.scalars().all()

    # batch load doc_count（避免 N+1）
    if not tags:
        return []

    tag_ids = [t.id for t in tags]
    count_result = await db.execute(
        select(DocumentTag.tag_id, func.count(DocumentTag.doc_id).label("cnt"))
        .where(DocumentTag.tag_id.in_(tag_ids))
        .group_by(DocumentTag.tag_id)
    )
    count_map = {row.tag_id: row.cnt for row in count_result}

    return [
        TagOut(
            id=t.id,
            name=t.name,
            slug=t.slug,
            color=t.color,
            description=t.description,
            parent_id=t.parent_id,
            doc_count=count_map.get(t.id, 0),
        )
        for t in tags
    ]


@router.post("/", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: TagCreate,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """建立新 tag，自動產生 slug。"""
    slug = _make_slug(body.name)

    # 檢查重複
    existing = await db.execute(select(Tag).where(Tag.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"slug '{slug}' 已存在")

    tag = Tag(
        name=body.name.strip(),
        slug=slug,
        color=body.color,
        description=body.description,
        parent_id=body.parent_id or None,
        created_by=current_user.id if current_user else None,
    )
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    logger.info("Tag created: %s (%s)", tag.name, tag.id)
    return TagOut(id=tag.id, name=tag.name, slug=tag.slug, color=tag.color,
                  description=tag.description, parent_id=tag.parent_id, doc_count=0)


@router.patch("/{tag_id}", response_model=TagOut)
async def update_tag(
    tag_id: str,
    body: TagUpdate,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """更新 tag 的 name / color / description。"""
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag 不存在")

    if body.name is not None:
        new_slug = _make_slug(body.name)
        if new_slug != tag.slug:
            dup = await db.execute(select(Tag).where(Tag.slug == new_slug))
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=409, detail=f"slug '{new_slug}' 已存在")
        tag.name = body.name.strip()
        tag.slug = new_slug
    if body.color is not None:
        tag.color = body.color
    if body.description is not None:
        tag.description = body.description

    await db.commit()
    await db.refresh(tag)

    count_result = await db.execute(
        select(func.count(DocumentTag.doc_id)).where(DocumentTag.tag_id == tag.id)
    )
    doc_count = count_result.scalar() or 0
    return TagOut(id=tag.id, name=tag.name, slug=tag.slug, color=tag.color,
                  description=tag.description, parent_id=tag.parent_id, doc_count=doc_count)


@router.delete("/{tag_id}", status_code=status.HTTP_200_OK)
async def delete_tag(
    tag_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """徹底刪除 tag（CASCADE 自動刪 document_tags），回傳影響文件數。"""
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag 不存在")

    # 先算影響幾篇文件
    count_result = await db.execute(
        select(func.count()).select_from(DocumentTag).where(DocumentTag.tag_id == tag_id)
    )
    deleted_doc_count = count_result.scalar() or 0

    await db.delete(tag)
    await db.commit()
    return {"deleted": True, "deleted_doc_count": deleted_doc_count}


@router.delete("/{tag_id}/documents/all", status_code=status.HTTP_200_OK)
async def remove_tag_from_all_documents(
    tag_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """移除這個 tag 與所有文件的關聯，但 tag 本身保留。"""
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag 不存在")

    # 算影響幾篇文件
    count_result = await db.execute(
        select(func.count()).select_from(DocumentTag).where(DocumentTag.tag_id == tag_id)
    )
    affected_doc_count = count_result.scalar() or 0

    # 刪除所有關聯
    from sqlalchemy import delete as sa_delete
    await db.execute(sa_delete(DocumentTag).where(DocumentTag.tag_id == tag_id))
    await db.commit()
    return {"tag_id": tag_id, "removed_doc_count": affected_doc_count}


@router.post("/{tag_id}/documents/{doc_id}", status_code=status.HTTP_201_CREATED)
async def add_tag_to_document(
    tag_id: str,
    doc_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """將文件貼上標籤（source='manual'）。"""
    # 驗證 tag 和 doc 存在
    tag_result = await db.execute(select(Tag).where(Tag.id == tag_id))
    if tag_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Tag 不存在")

    doc_result = await db.execute(select(Document).where(Document.id == doc_id))
    if doc_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    # 若已存在則 idempotent 直接回傳
    existing = await db.execute(
        select(DocumentTag).where(DocumentTag.doc_id == doc_id, DocumentTag.tag_id == tag_id)
    )
    if existing.scalar_one_or_none():
        return {"doc_id": doc_id, "tag_id": tag_id, "source": "manual"}

    dt = DocumentTag(
        doc_id=doc_id,
        tag_id=tag_id,
        source="manual",
        created_by=current_user.id if current_user else None,
    )
    db.add(dt)
    await db.commit()
    return {"doc_id": doc_id, "tag_id": tag_id, "source": "manual"}


@router.delete("/{tag_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tag_from_document(
    tag_id: str,
    doc_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """移除文件的標籤。"""
    result = await db.execute(
        select(DocumentTag).where(DocumentTag.doc_id == doc_id, DocumentTag.tag_id == tag_id)
    )
    dt = result.scalar_one_or_none()
    if dt is None:
        raise HTTPException(status_code=404, detail="此文件沒有該標籤")
    await db.delete(dt)
    await db.commit()
