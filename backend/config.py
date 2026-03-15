"""
Engram — Core Configuration
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):

    # ── LLM ───────────────────────────────────
    gemini_api_key: str
    gemini_model: str = "gemini-3-flash-preview"

    # ── PostgreSQL ────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "engram"
    postgres_user: str = "engram"
    postgres_password: str = "engram_secret"

    # ── Qdrant ────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "memories"

    # ── Redis ─────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379

    # ── FalkorDB ──────────────────────────────
    falkordb_host: str = "localhost"
    falkordb_port: int = 6380

    # ── Embeddings ────────────────────────────
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # ── Reranker ──────────────────────────────
    reranker_model: str = "BAAI/bge-reranker-base"

    # ── Memory Tuning ─────────────────────────
    duplicate_threshold: float = 0.80
    graph_confidence_threshold: float = 0.85
    top_k_retrieval: int = 20
    top_k_reranked: int = 5
    max_context_tokens: int = 2000

    # ── App ───────────────────────────────────
    app_port: int = 8000

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
