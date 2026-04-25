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
    plugin_type: str = "webhook"            # webhook | builtin
    builtin_key: Optional[str] = None       # notion | chart | calculator | email | rss | weather
    endpoint: str = ""                      # webhook 用
    auth_header: Optional[str] = None       # 明文，存入時加密
    input_schema: dict = {}
    plugin_config: dict = {}                # 非敏感設定
    enabled: bool = True


class PluginUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    plugin_type: Optional[str] = None
    builtin_key: Optional[str] = None
    endpoint: Optional[str] = None
    auth_header: Optional[str] = None       # None 表示不變更；空字串表示清除
    input_schema: Optional[dict] = None
    plugin_config: Optional[dict] = None
    enabled: Optional[bool] = None


class PluginOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    plugin_type: str
    builtin_key: Optional[str]
    endpoint: str
    has_auth: bool
    input_schema: dict
    plugin_config: dict
    enabled: bool
    created_at: str

    class Config:
        from_attributes = True


def _to_out(p: Plugin) -> PluginOut:
    return PluginOut(
        id=p.id,
        name=p.name,
        description=p.description,
        plugin_type=getattr(p, "plugin_type", "webhook") or "webhook",
        builtin_key=getattr(p, "builtin_key", None),
        endpoint=p.endpoint or "",
        has_auth=bool(p.auth_header),
        input_schema=p.input_schema or {},
        plugin_config=getattr(p, "plugin_config", {}) or {},
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
        plugin_type=body.plugin_type,
        builtin_key=body.builtin_key,
        endpoint=body.endpoint,
        auth_header=encrypted,
        input_schema=body.input_schema,
        plugin_config=body.plugin_config,
        enabled=body.enabled,
    )
    db.add(plugin)
    await db.commit()
    await db.refresh(plugin)
    logger.info("Plugin created: id=%s name=%s type=%s", plugin.id, plugin.name, plugin.plugin_type)
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
    if body.plugin_type is not None:
        plugin.plugin_type = body.plugin_type
    if body.builtin_key is not None:
        plugin.builtin_key = body.builtin_key
    if body.endpoint is not None:
        plugin.endpoint = body.endpoint
    if body.input_schema is not None:
        plugin.input_schema = body.input_schema
    if body.plugin_config is not None:
        plugin.plugin_config = body.plugin_config
    if body.enabled is not None:
        plugin.enabled = body.enabled
    if body.auth_header is not None:
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
    """手動觸發插件 — builtin 直接返回結果，webhook 則交由 Celery"""
    result = await db.execute(select(Plugin).where(Plugin.id == plugin_id))
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件不存在")
    if not plugin.enabled:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="插件已停用",
        )

    ptype = getattr(plugin, "plugin_type", "webhook") or "webhook"

    if ptype == "builtin":
        builtin_key = getattr(plugin, "builtin_key", None)
        if not builtin_key:
            raise HTTPException(status_code=400, detail="未設定 builtin_key")

        config = dict(getattr(plugin, "plugin_config", {}) or {})
        if plugin.auth_header:
            try:
                config["_auth"] = decrypt_secret(plugin.auth_header)
                if builtin_key == "notion" and "notion_token" not in config:
                    config["notion_token"] = config["_auth"]
            except Exception:
                pass

        action = payload.pop("action", builtin_key)
        from plugins.registry import dispatch
        result_data = await dispatch(builtin_key, action, payload, config)
        return result_data
    else:
        from tasks.webhook_tasks import call_webhook
        task = call_webhook.delay(plugin_id, plugin.endpoint, plugin.auth_header, payload)
        return {"task_id": task.id, "status": "queued"}


@router.get("/catalog/list")
async def get_plugin_catalog(_user: CurrentUser):
    """插件目錄 — 回傳所有可用的內建插件清單（含規劃中）"""
    from plugins.registry import PLUGIN_CATALOG
    return PLUGIN_CATALOG


# ── Notion 同步端點（Phase C）────────────────────────────────────

class NotionSyncRequest(BaseModel):
    plugin_id: str
    database_id: str | None = None


@router.post("/notion/sync", status_code=status.HTTP_202_ACCEPTED)
async def notion_sync(
    body: NotionSyncRequest,
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """觸發 Notion 資料庫增量同步（202 Accepted）"""
    result = await db.execute(select(Plugin).where(Plugin.id == body.plugin_id))
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin 不存在")
    if not plugin.enabled:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Plugin 已停用")

    # database_id 優先使用 request body，否則從 plugin_config 取
    database_id = body.database_id
    if not database_id:
        config      = getattr(plugin, "plugin_config", {}) or {}
        database_id = config.get("database_id", "")
    if not database_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="缺少 database_id，請在 request body 或 plugin_config 中提供",
        )

    from tasks.notion_tasks import sync_notion_database_task
    task = sync_notion_database_task.delay(database_id, body.plugin_id)

    logger.info("Notion sync task queued: task_id=%s plugin_id=%s database_id=%s",
                task.id, body.plugin_id, database_id)
    return {"task_id": task.id, "status": "queued", "database_id": database_id}


@router.get("/notion/sync/{task_id}")
async def notion_sync_status(task_id: str, _user: CurrentUser):
    """查詢 Notion 同步任務狀態"""
    from celery.result import AsyncResult
    from tasks.notion_tasks import sync_notion_database_task  # 確保 task 已註冊

    result = AsyncResult(task_id)
    state  = result.state

    if state == "SUCCESS":
        return {"task_id": task_id, "status": "completed", "result": result.result}
    elif state == "FAILURE":
        return {"task_id": task_id, "status": "failed", "error": str(result.result)}
    elif state == "PENDING":
        return {"task_id": task_id, "status": "pending"}
    else:
        return {"task_id": task_id, "status": state.lower()}

