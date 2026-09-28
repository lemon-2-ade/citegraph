"""Application configuration loaded from environment variables.

Secrets are typed as ``SecretStr`` so they never appear in logs or reprs.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- application -------------------------------------------------------
    app_name: str = "ResearchGraph"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = True
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- Neo4j ---------------------------------------------------------------
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("")
    neo4j_database: str = "neo4j"
    neo4j_max_pool_size: int = 50

    # --- PostgreSQL ----------------------------------------------------------
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://researchgraph:researchgraph@localhost:5432/researchgraph"
    )

    # --- Redis / worker ------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # --- Ingestion -----------------------------------------------------------
    openalex_base_url: str = "https://api.openalex.org"
    # OpenAlex "polite pool": identify yourself with a contact e-mail.
    openalex_mailto: str | None = None
    openalex_requests_per_second: float = 5.0
    http_timeout_seconds: float = 30.0
    http_max_retries: int = 5

    # --- Analytics -------------------------------------------------------------
    # "auto" uses Neo4j GDS when the plugin is installed, NetworkX otherwise.
    analytics_backend: Literal["auto", "gds", "networkx"] = "auto"

    # --- AI (used from Phase 7 onwards) ------------------------------------------
    llm_provider: Literal["openai", "gemini", "ollama"] = "openai"
    llm_model: str = "gpt-4o-mini"
    embedding_provider: Literal["openai", "sentence-transformers"] = "openai"
    embedding_model: str = "text-embedding-3-small"
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"


@lru_cache
def get_settings() -> Settings:
    return Settings()
