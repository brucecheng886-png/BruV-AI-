import asyncio
from fastapi import APIRouter
from datetime import datetime

router = APIRouter()


@router.get("")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "ai-knowledge-base",
    }


@router.get("/services")
async def services_health():
    """各依賴服務健康狀態"""
    import httpx
    from config import settings

    async def check(name: str, url: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(url)
                return {"name": name, "status": "ok", "code": r.status_code}
        except Exception as e:
            return {"name": name, "status": "error", "detail": str(e)}

    checks = await asyncio.gather(
        check("qdrant", f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}/health"),
        check("ollama", f"{settings.OLLAMA_BASE_URL}/api/tags"),
        check("playwright", f"{settings.PLAYWRIGHT_SERVICE_URL}/health"),
    )
    return {"services": list(checks)}
