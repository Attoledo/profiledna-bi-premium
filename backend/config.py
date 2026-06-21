from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Settings estritamente alinhadas às env vars referenciadas no SSOT_PROFILEDNA_v2_0.md.

    Fonte: runtime/.env em produção (não versionado).
    """

    model_config = SettingsConfigDict(
        env_file="/srv/profiledna/runtime/.env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ===== Core =====
    SECRET_KEY: str = Field(..., min_length=16)
    DATABASE_URL: str = Field(..., min_length=1)

    # ===== App server =====
    APP_HOST: str = Field(default="0.0.0.0")
    APP_PORT: int = Field(default=8000, ge=1, le=65535)

    # ===== Admin =====
    ADMIN_USERNAME: str = Field(..., min_length=1)
    ADMIN_PASSWORD: str = Field(..., min_length=8)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=1, le=60 * 24 * 30)

    # ===== AI / Agente =====
    AI_ENABLED: bool = Field(default=False)
    OPENAI_API_KEY: Optional[str] = Field(default=None)
    OPENAI_MODEL: str = Field(default="gpt-4o-mini")

    # ===== Alembic (migrações sync) =====
    ALEMBIC_DATABASE_URL: Optional[str] = Field(default=None)

    PROMPT_VERSION: str = Field(default="v1")
    SYSTEM_PROMPT: str = Field(default="")
    TOOL_DEFINITIONS: str = Field(default="")

    # ===== Docs / artefatos versionados (SSOT) =====
    API_CONTRACTS: str = Field(default="docs/API_CONTRACTS.md")
    DATA_DICTIONARY: str = Field(default="docs/DATA_DICTIONARY.md")
    RUNBOOK_PROD: str = Field(default="docs/RUNBOOK_PROD.md")

    # ===== Canonical JSON (SSOT) =====
    QUESTIONS_PDF_CORRIGIDO_CANONICAL: str = Field(
        default="docs/QUESTIONS_PDF_CORRIGIDO_CANONICAL.json"
    )

    # ===== Metadados SSOT (opcional) =====
    CONTEXTO_PROJETO: str = Field(default="TESTE PERFIL DNA")

    # ===== Estados (token aparece no SSOT; manter como constante configurável) =====
    IN_PROGRESS: str = Field(default="IN_PROGRESS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Cache singleton: evita reparse de env e garante determinismo.
    """
    return Settings()
