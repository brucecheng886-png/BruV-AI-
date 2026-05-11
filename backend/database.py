"""
資料庫連線層
- PostgreSQL: SQLAlchemy asyncpg
- Neo4j: neo4j async driver
- Qdrant: qdrant-client
"""
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

logger = logging.getLogger(__name__)

# ── PostgreSQL ────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Neo4j ─────────────────────────────────────────────────────
from neo4j import AsyncGraphDatabase

_neo4j_driver = None


def get_neo4j_driver():
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            max_connection_pool_size=20,
        )
    return _neo4j_driver


async def get_neo4j_session():
    driver = get_neo4j_driver()
    async with driver.session(database="neo4j") as session:
        yield session


# ── Qdrant ────────────────────────────────────────────────────
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

_qdrant_client = None


def get_qdrant_client() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            api_key=settings.QDRANT_API_KEY or None,
            https=False,
        )
    return _qdrant_client


async def ensure_qdrant_collection():
    """確保 Qdrant collection 存在，不存在則建立"""
    client = get_qdrant_client()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]

    # 主文件 collection
    if settings.QDRANT_COLLECTION not in names:
        await client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
        )
        logger.info("已建立 Qdrant collection: %s", settings.QDRANT_COLLECTION)
    else:
        logger.info("Qdrant collection 已存在: %s", settings.QDRANT_COLLECTION)

    # prompt_templates collection
    _PROMPT_COLLECTION = "prompt_templates"
    if _PROMPT_COLLECTION not in names:
        await client.create_collection(
            collection_name=_PROMPT_COLLECTION,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
        )
        logger.info("已建立 Qdrant collection: %s", _PROMPT_COLLECTION)
    else:
        logger.info("Qdrant collection 已存在: %s", _PROMPT_COLLECTION)
