"""
稽核日誌 Middleware

攔截所有 HTTP 請求，對需要稽核的操作（寫入/刪除類）記錄至 audit_logs 表。
讀取類（GET）一律略過，不寫 DB 以保持效能。
"""
import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from database import AsyncSessionLocal
from models import AuditLog

logger = logging.getLogger(__name__)

# 需要稽核的 HTTP 方法（GET/HEAD/OPTIONS 略過）
_AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# 不稽核的路徑前綴（效能相關、健康檢查、stream）
_SKIP_PREFIXES = (
    "/api/health",
    "/api/chat/stream",       # SSE stream 太頻繁
    "/api/chat/rag-search",
    "/metrics",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
)


def _action_from_request(method: str, path: str) -> str:
    """將 method + path 對應成可讀 action 名稱"""
    path_lower = path.lower()
    if method == "DELETE":
        if "document" in path_lower:
            return "DELETE_DOCUMENT"
        if "knowledge_base" in path_lower or "kb" in path_lower:
            return "DELETE_KB"
        if "user" in path_lower:
            return "DELETE_USER"
        if "plugin" in path_lower:
            return "DELETE_PLUGIN"
        if "fido" in path_lower or "key" in path_lower:
            return "DELETE_FIDO_KEY"
        return "DELETE"
    if method == "POST":
        if "login" in path_lower:
            return "LOGIN"
        if "upload" in path_lower:
            return "UPLOAD_DOCUMENT"
        if "register" in path_lower:
            return "FIDO2_REGISTER"
        if "users" in path_lower:
            return "CREATE_USER"
        if "step-up" in path_lower:
            return "STEP_UP"
        return "POST"
    if method == "PATCH":
        if "user" in path_lower:
            return "UPDATE_USER"
        return "PATCH"
    return method


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 略過不需稽核的請求
        if request.method not in _AUDIT_METHODS:
            return await call_next(request)
        if any(request.url.path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        # 取得使用者資訊（從 Authorization header decode，失敗不影響請求）
        user_id: str | None = None
        user_email: str | None = None
        try:
            from auth import decode_token
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                payload = decode_token(auth_header[7:])
                user_id = payload.sub
                user_email = payload.email
        except Exception:
            pass

        # 執行請求
        response = await call_next(request)

        # 非同步寫入 audit log（不阻塞回應）
        action = _action_from_request(request.method, request.url.path)
        ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)

        try:
            async with AsyncSessionLocal() as db:
                log = AuditLog(
                    user_id=user_id,
                    user_email=user_email,
                    action=action,
                    method=request.method,
                    path=request.url.path,
                    ip=ip,
                    status_code=response.status_code,
                )
                db.add(log)
                await db.commit()
        except Exception as e:
            # 日誌寫入失敗不影響主要請求
            logger.warning("Audit log write failed: %s", e)

        return response
