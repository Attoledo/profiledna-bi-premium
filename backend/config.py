from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ===== Resolução resiliente do arquivo de ambiente =====
# Em produção, o .env vive em /srv/profiledna/runtime/.env (não versionado).
# Em desenvolvimento local, esse diretório não existe — então caímos para um
# .env local, testando dois locais plausíveis de "raiz do projeto":
#   1) backend/.. -> .../profiledna/.env (raiz do app)
#   2) backend/../.. -> .../ProfileDNA_WORKING_COPY_20260610/.env (raiz do
#      workspace, um nível acima de profiledna/ — onde o .env local desta
#      sessão de desenvolvimento foi efetivamente criado)
# Se nenhum existir, mantemos o path de produção como valor padrão:
# pydantic-settings simplesmente ignora um env_file ausente, então isso não
# quebra o boot — as env vars já exportadas no processo continuam valendo.
_PROD_ENV_FILE = "/srv/profiledna/runtime/.env"
_APP_ROOT = Path(__file__).resolve().parent.parent
_LOCAL_ENV_CANDIDATES = (
    _APP_ROOT / ".env",
    _APP_ROOT.parent / ".env",
)


def _resolve_env_file() -> str:
    if os.path.exists(_PROD_ENV_FILE):
        return _PROD_ENV_FILE
    for candidate in _LOCAL_ENV_CANDIDATES:
        if os.path.exists(candidate):
            return str(candidate)
    return _PROD_ENV_FILE


class Settings(BaseSettings):
    """
    Settings estritamente alinhadas às env vars referenciadas no SSOT_PROFILEDNA_v2_0.md.

    Fonte: runtime/.env em produção (não versionado), com fallback para um
    .env na raiz do projeto em ambientes de desenvolvimento local.
    """

    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
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
