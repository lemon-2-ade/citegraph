"""Application configuration loaded from environment variables.

Secrets are typed as ``SecretStr`` so they never appear in logs or reprs.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
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
    # Required (X-Admin-Token header) for administrative endpoints such as ingestion.
    # If unset, those endpoints are open in development and disabled in production.
    admin_api_token: SecretStr | None = None

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

    # Curated seed dataset; defaults to <repo>/data/seed/papers.json when unset.
    seed_path: str | None = None

    # --- Analytics -------------------------------------------------------------
    # "auto" uses Neo4j GDS when the plugin is installed, NetworkX otherwise.
    analytics_backend: Literal["auto", "gds", "networkx"] = "auto"

    # --- AI (used from Phase 7 onwards) ------------------------------------------
    llm_provider: Literal["openai", "gemini", "ollama"] = "openai"
    llm_model: str = "gpt-4o-mini"
    # "auto" uses OpenAI when OPENAI_API_KEY is set and a local CPU model otherwise.
    # "hashing" is a deterministic offline provider for tests and demos only.
    embedding_provider: Literal["auto", "openai", "local", "hashing"] = "auto"
    openai_embedding_model: str = "text-embedding-3-small"
    # Optional reduced output size for OpenAI's text-embedding-3 models.
    openai_embedding_dimensions: int | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    local_embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = 64
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"

    @field_validator(
        "admin_api_token",
        "openai_api_key",
        "gemini_api_key",
        "openalex_mailto",
        "seed_path",
        "openai_embedding_dimensions",
        mode="before",
    )
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        # Docker Compose passes unset variables as empty strings.
        return None if isinstance(value, str) and not value.strip() else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
