from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "computer-course-rag"
    retrieval_top_k: int = 5
    retrieval_min_score: float = 0.43
    retrieval_vector_weight: float = 0.90
    chunk_size: int = 500
    chunk_overlap: int = 80
    storage_backend: str = "memory"
    database_url: str = "postgresql+psycopg://rag:rag@localhost:5432/rag"
    embedding_dimensions: int = 512
    embedding_provider: str = "hashing"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_cache_dir: str | None = None
    llm_provider: str = "offline"
    llm_api_base: str = "https://api.openai.com/v1"
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 30.0
    llm_fallback_offline: bool = True
    model_config_secret_path: str | None = None
    auth_required: bool = False
    assistant_task_worker_enabled: bool = True
    auth_secret: str = "change-this-local-secret"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
