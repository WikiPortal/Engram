"""
Engram — Core Configuration
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path

def _find_env() -> str:
    root_env    = Path(__file__).parent.parent / ".env"
    backend_env = Path(__file__).parent / ".env"
    if root_env.exists():
        return str(root_env)
    return str(backend_env)


class Settings(BaseSettings):

    llm_provider: str = "gemini"
    llm_model: str = ""

    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""

    gemini_model: str = "gemini-3-flash-preview"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "engram"
    postgres_user: str = "engram"
    postgres_password: str = "engram_secret"

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "memories"

    redis_host: str = "localhost"
    redis_port: int = 6379

    falkordb_host: str = "localhost"
    falkordb_port: int = 6380

    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    reranker_model: str = "BAAI/bge-reranker-base"

    duplicate_threshold: float = 0.80
    graph_confidence_threshold: float = 0.85
    top_k_retrieval: int = 20
    top_k_reranked: int = 5
    max_context_tokens: int = 2000

    sliding_window_lookback: int = 5

    app_port: int = 8000

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    rate_limit_store:  str = "30/minute"
    rate_limit_chat:   str = "20/minute"
    rate_limit_recall: str = "60/minute"

    auth_secret: str = "engram-change-this-secret-in-production"

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
        env_file = _find_env()
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
