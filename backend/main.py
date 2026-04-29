"""
FastAPI 主程式入口
"""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from config import settings
from routers import chat, documents, ontology, wiki, agent, plugins, search, health, knowledge_bases
from routers import auth as auth_router
from routers import settings_router
from routers import protein_router
from routers import prompt_engine
from routers import tags
from routers import agent_skills
from routers import monitoring

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """啟動與關閉時執行"""
    logger.info("Starting AI Knowledge Base Backend...")
    from services.saga import init_saga_db
    init_saga_db()
    from database import ensure_qdrant_collection
    await ensure_qdrant_collection()
    # 初始化資料庫連線、Re-ranker 等
    from services.reranker import get_reranker
    await get_reranker()  # 預載入 Re-ranker 模型

    # 補入預設 agent_skills（kb）
    try:
        from database import AsyncSessionLocal
        from sqlalchemy import text as _t
        async with AsyncSessionLocal() as _db:
            # 一次性 schema migration: knowledge_bases.agent_prompt
            await _db.execute(_t(
                "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS agent_prompt TEXT"
            ))
            await _db.execute(_t(
                "INSERT INTO agent_skills (page_key, name, user_prompt, is_enabled) "
                "VALUES (:pk, :nm, :up, TRUE) "
                "ON CONFLICT (page_key) DO NOTHING"
            ), {
                "pk": "kb",
                "nm": "知識庫助理",
                "up": "你是知識庫助理。你可以幫助使用者：\n- 搜尋知識庫文件\n- 回答知識庫相關問題\n- 協助整理和分類文件\n\n回答時請簡潔明確，優先使用繁體中文。",
            })
            await _db.commit()
    except Exception as _e:
        logger.warning("Seed kb agent_skill failed: %s", _e)

    logger.info("Backend ready.")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="地端 AI 知識庫 API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus metrics ────────────────────────────────────────
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ── 全域例外處理 ───────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception on %s %s",
        request.method,
        request.url,
        exc_info=True,
    )
    detail = str(exc) if settings.DEBUG else "內部伺服器錯誤，請聯絡管理員"
    return JSONResponse(status_code=500, content={"error": detail})

# ── 路由掛載 ───────────────────────────────────────────────────
app.include_router(health.router,       prefix="/api/health",       tags=["health"])
app.include_router(auth_router.router,  prefix="/api/auth",         tags=["auth"])
app.include_router(chat.router,         prefix="/api/chat",         tags=["chat"])
app.include_router(documents.router,    prefix="/api/documents",    tags=["documents"])
app.include_router(knowledge_bases.router, prefix="/api/knowledge-bases", tags=["knowledge-bases"])
app.include_router(ontology.router,     prefix="/api/ontology",     tags=["ontology"])
app.include_router(wiki.router,         prefix="/api/wiki",         tags=["wiki"])
app.include_router(agent.router,        prefix="/api/agent",        tags=["agent"])
app.include_router(plugins.router,      prefix="/api/plugins",      tags=["plugins"])
app.include_router(search.router,       prefix="/api/search",       tags=["search"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(protein_router.router,  prefix="/api/protein",   tags=["protein"])
app.include_router(prompt_engine.router,   prefix="/api/prompt-templates", tags=["prompt-engine"])
app.include_router(tags.router,            prefix="/api/tags",             tags=["tags"])
app.include_router(agent_skills.router,    prefix="/api/agent-skills",     tags=["agent-skills"])
app.include_router(monitoring.router,      prefix="/api/monitoring",       tags=["monitoring"])
