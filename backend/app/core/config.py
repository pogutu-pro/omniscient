"""Central application configuration, sourced from environment variables.

Nothing here is a secret by default — see ../../../.env.example for the
documented list of variables an operator is expected to supply.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Application ---
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_url: str = "http://localhost:5173"
    api_url: str = "http://localhost:8000"
    secret_key: str = "insecure-development-key-change-me"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"

    # --- Database ---
    database_url: str = "postgresql+asyncpg://omniscient:omniscient@localhost:5432/omniscient"
    database_url_sync: str = "postgresql+psycopg2://omniscient:omniscient@localhost:5432/omniscient"

    # --- AI provider ---
    # "mock" needs no credentials and is the safe zero-config default.
    # "grok" (xAI) is the intended primary real provider; "openai",
    # "deepseek", "anthropic" and "custom" (any other OpenAI-compatible
    # endpoint — Groq, Together, Mistral, ...) are drop-in alternatives.
    # Switching providers is a config change only: see
    # agents/providers/factory.py.
    llm_provider: Literal["mock", "anthropic", "openai", "grok", "deepseek", "custom"] = "mock"
    llm_model: str = "claude-sonnet-5"
    llm_api_key: str | None = None
    llm_api_base: str | None = None  # required for "custom"; optional override for the rest
    llm_temperature: float = 0.2

    # --- Rumia integration boundary ---
    rumia_db_mode: Literal["disabled", "enabled"] = "disabled"
    rumia_database_url: str | None = None

    # --- Storage ---
    storage_provider: Literal["local", "s3"] = "local"
    storage_local_path: str = "./backend/var/storage"
    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str | None = None

    # --- Rate limiting ---
    rate_limit_chat_per_minute: int = 20
    rate_limit_default_per_minute: int = 60

    @field_validator("app_env")
    @classmethod
    def _validate_secret_in_prod(cls, v: str) -> str:
        return v

    @field_validator("llm_api_base")
    @classmethod
    def _require_api_base_for_custom_provider(cls, v: str | None, info) -> str | None:
        if info.data.get("llm_provider") == "custom" and not v:
            raise ValueError("LLM_API_BASE is required when LLM_PROVIDER=custom")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
