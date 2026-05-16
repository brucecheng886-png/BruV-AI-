"""
共享硬碟 Router — 資料夾 CRUD、文件管理、白名單
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, CurrentAdmin
from database import get_db
from models import Folder, FolderDocument, FolderPermission, Document, User

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────

class FolderIn(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[str] = None
    icon: str = "📁"
    color: str = "#2563eb"


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class FolderMoveIn(BaseModel):
    parent_id: Optional[str] = None  # None = 移到根目錄


class FolderDocAddIn(BaseModel):
    doc_ids: list[str]


class FolderPermIn(BaseModel):
    user_id: str
    permission: str = "read"  # "read" | "write" | "manage"


class FolderOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    parent_id: Optional[str]
    icon: str
    color: str
    created_by: Optional[str]
    created_at: str
    updated_at: str
    children_count: int = 0
    doc_count: int = 0


class FolderPermOut(BaseModel):
    id: int
    folder_id: str
    user_id: str
    user_email: Optional[str]
    user_display_name: Optional[str]
    permission: str
    granted_by: Optional[str]
    granted_at: str


class FolderDocOut(BaseModel):
    doc_id: str
    title: str
    file_type: Optional[str]
    status: str
    added_by: Optional[str]
    added_at: str


# ── 權限繼承輔助函式 ─────────────────────────────────────────────

async def _get_effective_permission(
    folder_id: str,
    user_id: str,
    db: AsyncSession,
    _depth: int = 0,
) -> Optional[str]:
    """遞迴向上查詢使用者對資料夾的有效權限（繼承父層）"""
    if _depth > 10:  # 防止循環參照
        return None

    # 查詢此層直接授權
    result = await db.execute(
        select(FolderPermission).where(
            FolderPermission.folder_id == folder_id,
            FolderPermission.user_id == user_id,
        )
    )
    perm = result.scalar_one_or_none()
    if perm:
        return perm.permission

    # 向上查父層
    folder_result = await db.execute(
        select(Folder.parent_id).where(Folder.id == folder_id)
    )
    row = folder_result.first()
    if row and row[0]:
        return await _get_effective_permission(row[0], user_id, db, _depth + 1)
    return None


async def _check_access(
    folder_id: str,
    user: User,
    db: AsyncSession,
    required: str = "read",
) -> None:
    """確認使用者對資料夾有足夠權限，不足則 raise 403。admin 永遠通過。"""
    if user.role == "admin":
        return
    perm = await _get_effective_permission(folder_id, user.id, db)
    if perm is None:
        raise HTTPException(status_code=403, detail="無此資料夾的存取權限")
    order = {"read": 0, "write": 1, "manage": 2}
    if order.get(perm, -1) < order.get(required, 0):
        raise HTTPException(status_code=403, detail=f"需要 {required} 權限")


async def _folder_to_out(folder: Folder, db: AsyncSession) -> FolderOut:
    children_result = await db.execute(
        select(Folder).where(Folder.parent_id == folder.id)
    )
    children_count = len(children_result.scalars().all())
    doc_result = await db.execute(
        select(FolderDocument).where(FolderDocument.folder_id == folder.id)
    )
    doc_count = len(doc_result.scalars().all())
    return FolderOut(
        id=folder.id,
        name=folder.name,
        description=folder.description,
        parent_id=folder.parent_id,
        icon=folder.icon or "📁",
        color=folder.color or "#2563eb",
        created_by=folder.created_by,
        created_at=folder.created_at.isoformat(),
        updated_at=folder.updated_at.isoformat(),
        children_count=children_count,
        doc_count=doc_count,
    )


# ── 資料夾 CRUD ────────────────────────────────────────────────

@router.get("", response_model=list[FolderOut])
@router.get("/", response_model=list[FolderOut], include_in_schema=False)
async def list_root_folders(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """列出根目錄資料夾（依白名單過濾，admin 看全部）"""
    result = await db.execute(
        select(Folder).where(Folder.parent_id == None).order_by(Folder.name)  # noqa: E711
    )
    folders = result.scalars().all()

    if current_user.role != "admin":
        visible = []
        for f in folders:
            perm = await _get_effective_permission(f.id, current_user.id, db)
            if perm:
                visible.append(f)
        folders = visible

    return [await _folder_to_out(f, db) for f in folders]


@router.post("", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
async def create_folder(
    body: FolderIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """建立資料夾（admin 或對父資料夾有 manage 權限者）"""
    if body.parent_id:
        # 確認父資料夾存在
        parent_result = await db.execute(select(Folder).where(Folder.id == body.parent_id))
        if not parent_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="父資料夾不存在")
        await _check_access(body.parent_id, current_user, db, required="manage")
    elif current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有 admin 可以建立根目錄資料夾")

    folder = Folder(
        name=body.name,
        description=body.description,
        parent_id=body.parent_id,
        icon=body.icon,
        color=body.color,
        created_by=current_user.id,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return await _folder_to_out(folder, db)


@router.get("/{folder_id}", response_model=FolderOut)
async def get_folder(
    folder_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="資料夾不存在")
    await _check_access(folder_id, current_user, db)
    return await _folder_to_out(folder, db)


@router.get("/{folder_id}/children", response_model=list[FolderOut])
async def list_children(
    folder_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _check_access(folder_id, current_user, db)
    result = await db.execute(
        select(Folder).where(Folder.parent_id == folder_id).order_by(Folder.name)
    )
    return [await _folder_to_out(f, db) for f in result.scalars().all()]


@router.put("/{folder_id}", response_model=FolderOut)
async def update_folder(
    folder_id: str,
    body: FolderUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="資料夾不存在")
    await _check_access(folder_id, current_user, db, required="manage")

    if body.name is not None:
        folder.name = body.name
    if body.description is not None:
        folder.description = body.description
    if body.icon is not None:
        folder.icon = body.icon
    if body.color is not None:
        folder.color = body.color
    await db.commit()
    await db.refresh(folder)
    return await _folder_to_out(folder, db)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="資料夾不存在")
    await _check_access(folder_id, current_user, db, required="manage")

    # 禁止刪除非空資料夾
    children_result = await db.execute(
        select(Folder).where(Folder.parent_id == folder_id)
    )
    if children_result.scalars().first():
        raise HTTPException(
            status_code=400,
            detail="資料夾內有子資料夾，請先移除子資料夾才能刪除",
        )
    await db.delete(folder)
    await db.commit()


@router.post("/{folder_id}/move", response_model=FolderOut)
async def move_folder(
    folder_id: str,
    body: FolderMoveIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="資料夾不存在")
    await _check_access(folder_id, current_user, db, required="manage")

    if body.parent_id == folder_id:
        raise HTTPException(status_code=400, detail="資料夾不能移動到自己")
    if body.parent_id:
        target_result = await db.execute(select(Folder).where(Folder.id == body.parent_id))
        if not target_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="目標父資料夾不存在")
        await _check_access(body.parent_id, current_user, db, required="manage")

    folder.parent_id = body.parent_id
    await db.commit()
    await db.refresh(folder)
    return await _folder_to_out(folder, db)


# ── 資料夾文件管理 ─────────────────────────────────────────────

@router.get("/{folder_id}/documents", response_model=list[FolderDocOut])
async def list_folder_docs(
    folder_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _check_access(folder_id, current_user, db)
    result = await db.execute(
        select(FolderDocument, Document)
        .join(Document, Document.id == FolderDocument.doc_id)
        .where(FolderDocument.folder_id == folder_id)
        .where(Document.deleted_at == None)  # noqa: E711
        .order_by(FolderDocument.added_at.desc())
    )
    rows = result.all()
    return [
        FolderDocOut(
            doc_id=assoc.doc_id,
            title=doc.title,
            file_type=doc.file_type,
            status=doc.status,
            added_by=assoc.added_by,
            added_at=assoc.added_at.isoformat(),
        )
        for assoc, doc in rows
    ]


@router.post("/{folder_id}/documents", status_code=status.HTTP_201_CREATED)
async def add_docs_to_folder(
    folder_id: str,
    body: FolderDocAddIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """將一批文件加入資料夾（需要 write 權限）"""
    await _check_access(folder_id, current_user, db, required="write")

    added = 0
    for doc_id in body.doc_ids:
        # 確認文件存在
        doc_result = await db.execute(
            select(Document).where(Document.id == doc_id, Document.deleted_at == None)  # noqa: E711
        )
        if not doc_result.scalar_one_or_none():
            continue
        # 已存在則跳過
        exist_result = await db.execute(
            select(FolderDocument).where(
                FolderDocument.folder_id == folder_id,
                FolderDocument.doc_id == doc_id,
            )
        )
        if exist_result.scalar_one_or_none():
            continue
        db.add(FolderDocument(
            folder_id=folder_id,
            doc_id=doc_id,
            added_by=current_user.id,
        ))
        added += 1
    await db.commit()
    return {"added": added}


@router.delete("/{folder_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_doc_from_folder(
    folder_id: str,
    doc_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _check_access(folder_id, current_user, db, required="write")
    result = await db.execute(
        select(FolderDocument).where(
            FolderDocument.folder_id == folder_id,
            FolderDocument.doc_id == doc_id,
        )
    )
    assoc = result.scalar_one_or_none()
    if not assoc:
        raise HTTPException(status_code=404, detail="文件不在此資料夾中")
    await db.delete(assoc)
    await db.commit()


# ── 白名單管理 ─────────────────────────────────────────────────

@router.get("/{folder_id}/permissions", response_model=list[FolderPermOut])
async def list_permissions(
    folder_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _check_access(folder_id, current_user, db, required="manage")
    result = await db.execute(
        select(FolderPermission, User)
        .join(User, User.id == FolderPermission.user_id)
        .where(FolderPermission.folder_id == folder_id)
        .order_by(FolderPermission.granted_at.desc())
    )
    rows = result.all()
    return [
        FolderPermOut(
            id=perm.id,
            folder_id=perm.folder_id,
            user_id=perm.user_id,
            user_email=user.email,
            user_display_name=user.display_name,
            permission=perm.permission,
            granted_by=perm.granted_by,
            granted_at=perm.granted_at.isoformat(),
        )
        for perm, user in rows
    ]


@router.post("/{folder_id}/permissions", response_model=FolderPermOut, status_code=status.HTTP_201_CREATED)
async def grant_permission(
    folder_id: str,
    body: FolderPermIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _check_access(folder_id, current_user, db, required="manage")

    if body.permission not in ("read", "write", "manage"):
        raise HTTPException(status_code=400, detail="permission 必須為 read / write / manage")

    # 確認使用者存在
    user_result = await db.execute(select(User).where(User.id == body.user_id))
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="使用者不存在")

    # 若已有授權則更新
    exist_result = await db.execute(
        select(FolderPermission).where(
            FolderPermission.folder_id == folder_id,
            FolderPermission.user_id == body.user_id,
        )
    )
    existing = exist_result.scalar_one_or_none()
    if existing:
        existing.permission = body.permission
        existing.granted_by = current_user.id
        await db.commit()
        await db.refresh(existing)
        perm = existing
    else:
        perm = FolderPermission(
            folder_id=folder_id,
            user_id=body.user_id,
            permission=body.permission,
            granted_by=current_user.id,
        )
        db.add(perm)
        await db.commit()
        await db.refresh(perm)

    return FolderPermOut(
        id=perm.id,
        folder_id=perm.folder_id,
        user_id=perm.user_id,
        user_email=target_user.email,
        user_display_name=target_user.display_name,
        permission=perm.permission,
        granted_by=perm.granted_by,
        granted_at=perm.granted_at.isoformat(),
    )


@router.delete("/{folder_id}/permissions/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_permission(
    folder_id: str,
    user_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _check_access(folder_id, current_user, db, required="manage")
    result = await db.execute(
        select(FolderPermission).where(
            FolderPermission.folder_id == folder_id,
            FolderPermission.user_id == user_id,
        )
    )
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=404, detail="此使用者未在白名單中")
    await db.delete(perm)
    await db.commit()
