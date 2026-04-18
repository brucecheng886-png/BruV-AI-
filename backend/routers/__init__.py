from routers.health import router as health_router
from routers.chat import router as chat_router
from routers.documents import router as documents_router
from routers.ontology import router as ontology_router
from routers.wiki import router as wiki_router
from routers.agent import router as agent_router
from routers.plugins import router as plugins_router
from routers.search import router as search_router

__all__ = [
    "health", "chat", "documents", "ontology",
    "wiki", "agent", "plugins", "search",
]
