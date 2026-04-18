"""
Webhook Celery 任務（Phase 3b）

對插件 endpoint 發送 POST 請求，自動 retry（指數退避）。
auth_header 以 Fernet 加密儲存，呼叫前解密後放入 Authorization header。
"""
import logging
from typing import Any, Dict, Optional

import httpx
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=60,
    name="tasks.call_webhook",
)
def call_webhook(
    self,
    plugin_id: str,
    endpoint: str,
    auth_header_encrypted: Optional[str],
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """
    對插件 endpoint 發送 POST 請求。

    Args:
        plugin_id: 插件 UUID（用於 logging）
        endpoint: 目標 URL
        auth_header_encrypted: Fernet 加密的 Authorization header 值（可為 None）
        payload: 請求 body（JSON）

    Returns:
        {"status_code": int, "body": str}
    """
    logger.info(
        "[task:%s] Invoking plugin plugin_id=%s endpoint=%s",
        self.request.id, plugin_id, endpoint,
    )

    headers: Dict[str, str] = {"Content-Type": "application/json"}

    if auth_header_encrypted:
        try:
            from utils.crypto import decrypt_secret
            headers["Authorization"] = decrypt_secret(auth_header_encrypted)
        except ValueError as exc:
            logger.error(
                "[task:%s] Failed to decrypt auth_header for plugin_id=%s: %s",
                self.request.id, plugin_id, exc,
            )
            raise

    with httpx.Client(timeout=30) as client:
        resp = client.post(endpoint, json=payload, headers=headers)

    logger.info(
        "[task:%s] Plugin response plugin_id=%s status=%d",
        self.request.id, plugin_id, resp.status_code,
    )

    if resp.status_code >= 500:
        raise RuntimeError(
            f"Plugin endpoint returned {resp.status_code}: {resp.text[:200]}"
        )

    return {"status_code": resp.status_code, "body": resp.text[:1000]}
