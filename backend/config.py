"""
應用程式設定（從環境變數讀取）
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # PostgreSQL
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Qdrant
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "chunks"

    # Neo4j
    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str

    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET: str = "ai-kb-files"

    # Ollama（本地）
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_LLM_MODEL: str = "qwen2.5:14b"
    OLLAMA_EMBED_MODEL: str = "bge-m3"

    # LLM Provider 切換
    # 可選值: "ollama" | "openai" | "groq" | "gemini" | "openrouter"
    LLM_PROVIDER: str = "ollama"
    # 雲端 API Key（對應 provider 填一個即可）
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    # 雲端模型名稱（覆蓋 OLLAMA_LLM_MODEL）
    CLOUD_LLM_MODEL: str = ""

    # Playwright
    PLAYWRIGHT_SERVICE_URL: str = "http://playwright-service:3002"

    # SearXNG
    SEARXNG_URL: str = "http://searxng:8080"

    # 加密
    PLUGIN_ENCRYPT_KEY: str

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # KB 相似度分類
    KB_SIMILARITY_THRESHOLD: float = 0.75

    # 應用程式
    DEBUG: bool = False
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # ── LLM 成本表（USD per 1M tokens）─────────────────────────
    # Phase B6 用：估算 cost = (prompt_tokens / 1M) * input_price + (completion_tokens / 1M) * output_price
    # 模型未列入時 cost = 0（地端 / 自建模型）
    LLM_COST_TABLE: dict = {
        # OpenAI
        "gpt-4o":             {"input": 2.50,  "output": 10.00},
        "gpt-4o-mini":        {"input": 0.15,  "output": 0.60},
        "gpt-4-turbo":        {"input": 10.00, "output": 30.00},
        "o1":                 {"input": 15.00, "output": 60.00},
        "o1-mini":            {"input": 3.00,  "output": 12.00},
        "o3-mini":            {"input": 1.10,  "output": 4.40},
        # Anthropic
        "claude-3-5-sonnet-20241022": {"input": 3.00,  "output": 15.00},
        "claude-3-5-haiku-20241022":  {"input": 0.80,  "output": 4.00},
        "claude-3-opus-20240229":     {"input": 15.00, "output": 75.00},
        # Google Gemini
        "gemini-2.0-flash":   {"input": 0.10,  "output": 0.40},
        "gemini-1.5-pro":     {"input": 1.25,  "output": 5.00},
        # Groq（多為免費或低成本）
        "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    }

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
