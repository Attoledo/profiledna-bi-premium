from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.attempt import Attempt
from backend.repositories import attempt as repo_attempt
from backend.services.token import generate_token, token_hash


@dataclass(frozen=True)
class StartResult:
    token: str
    attempt: Attempt


async def start_public_attempt(
    session: AsyncSession,
    *,
    nome: str,
    sobrenome: Optional[str],
    email: Optional[str],
    empresa_nome: Optional[str] = None,
    tipo_aplicacao: str,
    testdef_version: str = "v1",
) -> StartResult:
    """
    SSOT: Fluxo público (start) cria Participant + Attempt com bootstrap DEFAULT_*.

    Responsabilidades:
    - Regras do fluxo público ficam aqui (service).
    - Persistência/queries ficam nos repositories.
    - Router só lida com HTTP e redirecionamento.
    """
    token = generate_token()
    th = token_hash(token)

    attempt = await repo_attempt.create_participant_and_attempt_default_seed(
        session,
        nome=nome,
        sobrenome=sobrenome,
        email=email,
        empresa_nome=empresa_nome,
        tipo_aplicacao=tipo_aplicacao,
        token_hash_hex=th,
        testdef_version=testdef_version,
    )
    return StartResult(token=token, attempt=attempt)
