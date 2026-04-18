"""
插件 Router — CRUD + 啟停（Phase 3b）

auth_header 明文進、Fernet 密文存；讀出時不暴露原文。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentAdmin, CurrentUser
from database import get_db
from models import Plugin
from utils.crypto import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────

class PluginCreate(BaseModel):
    name: str
    description: Optional[str] = None
    endpoint: str
    auth_header: Optional[str] = None      # 明文，存入時加密
    input_schema: dict = {}
    enabled: bool = True


class PluginUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None
    auth_header: Optional[str] = None      # None 表示不變更；空字串表示清除
    input_schema: Optional[dict] = None
    enabled: Optional[bool] = None


class PluginOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    endpoint: str
    has_auth: bool                          # 是否有 auth_header（不暴露密文）
    input_schema: dict
    enabled: bool
    created_at: str

    class Config:
        from_attributes = True


def _to_out(p: Plugin) -> PluginOut:
    return PluginOut(
        id=p.id,
        name=p.name,
        description=p.description,
        endpoint=p.endpoint,
        has_auth=bool(p.auth_header),
        input_schema=p.input_schema or {},
        enabled=p.enabled,
        created_at=p.created_at.isoformat(),
    )


# ── 端點 ─────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, response_model=PluginOut)
async def create_plugin(
    body: PluginCreate,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
):
    """建立插件，auth_header 以 Fernet 加密後寫入 DB"""
    # 檢查名稱唯一性
    existing = await db.execute(select(Plugin).where(Plugin.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"插件名稱 '{body.name}' 已存在",
        )

    encrypted = encrypt_secret(body.auth_header) if body.auth_header else None

    plugin = Plugin(
        name=body.name,
        description=body.description,
        endpoint=body.endpoint,
        auth_header=encrypted,
        input_schema=body.input_schema,
        enabled=body.enabled,
    )
    db.add(plugin)
    await db.commit()
    await db.refresh(plugin)
    logger.info("Plugin created: id=%s name=%s", plugin.id, plugin.name)
    return _to_out(plugin)


@router.get("", response_model=list[PluginOut])
async def list_plugins(
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """列出所有插件"""
    result = await db.execute(select(Plugin).order_by(Plugin.created_at.desc()))
    return [_to_out(p) for p in result.scalars().all()]


@router.get("/{plugin_id}", response_model=PluginOut)
async def get_plugin(
    plugin_id: str,
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """取得單一插件"""
    result = await db.execute(select(Plugin).where(Plugin.id == plugin_id))
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件不存在")
    return _to_out(plugin)


@router.patch("/{plugin_id}", response_model=PluginOut)
async def update_plugin(
    plugin_id: str,
    body: PluginUpdate,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
):
    """更新插件資訊（部分更新）"""
    result = await db.execute(select(Plugin).where(Plugin.id == plugin_id))
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件不存在")

    if body.name is not None:
        plugin.name = body.name
    if body.description is not None:
        plugin.description = body.description
    if body.endpoint is not None:
        plugin.endpoint = body.endpoint
    if body.input_schema is not None:
        plugin.input_schema = body.input_schema
    if body.enabled is not None:
        plugin.enabled = body.enabled
    if body.auth_header is not None:
        # 空字串 → 清除；其他 → 重新加密
        plugin.auth_header = encrypt_secret(body.auth_header) if body.auth_header else None

    await db.commit()
    await db.refresh(plugin)
    logger.info("Plugin updated: id=%s", plugin_id)
    return _to_out(plugin)


@router.delete("/{plugin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plugin(
    plugin_id: str,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
):
    """刪除插件（硬刪除）"""
    result = await db.execute(select(Plugin).where(Plugin.id == plugin_id))
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件不存在")
    await db.delete(plugin)
    await db.commit()
    logger.info("Plugin deleted: id=%s", plugin_id)


@router.post("/{plugin_id}/toggle", response_model=PluginOut)
async def toggle_plugin(
    plugin_id: str,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
):
    """切換插件啟停狀態"""
    result = await db.execute(select(Plugin).where(Plugin.id == plugin_id))
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件不存在")
    plugin.enabled = not plugin.enabled
    await db.commit()
    await db.refresh(plugin)
    state = "啟用" if plugin.enabled else "停用"
    logger.info("Plugin %s: id=%s", state, plugin_id)
    return _to_out(plugin)


@router.post("/{plugin_id}/invoke")
async def invoke_plugin(
    plugin_id: str,
    payload: dict,
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """手動觸發插件 Webhook（Celery 非同步）"""
    result = await db.execute(select(Plugin).where(Plugin.id == plugin_id))
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件不存在")
    if not plugin.enabled:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="插件已停用",
        )

    from tasks.webhook_tasks import call_webhook
    task = call_webhook.delay(plugin_id, plugin.endpoint, plugin.auth_header, payload)
    return {"task_id": task.id, "status": "queued"}

