from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories import attempt as repo_attempt
from backend.repositories import cliente as repo_cliente
from backend.repositories import invite as repo_invite
from backend.services.token import token_hash


@dataclass(frozen=True)
class InviteStartResult:
    token: str


async def start_attempt_from_invite(
    session: AsyncSession,
    *,
    token: str,
    nome: str,
    sobrenome: Optional[str],
    email: Optional[str],
) -> InviteStartResult:
    """
    Fluxo público do invite:
    - valida Invite via token_hash(token)
    - cria Participant + Attempt usando cliente/rodada/setor/cargo/tipo_aplicacao do Invite
    - marca Invite como OPENED (com attempt_id)
    - redireciona para /t/{token}/q/1 (reusa o mesmo token do invite)
    """
    th = token_hash(token)
    inv = await repo_invite.get_invite_by_token_hash(session, th)
    if not inv or inv.status in ("CANCELLED", "EXPIRED", "COMPLETED"):
        raise ValueError("Invalid invite")

    cliente = await repo_cliente.get_cliente_by_id(session, inv.cliente_id)
    if not cliente:
        raise ValueError("Invite without valid cliente")

    empresa_nome = str(getattr(cliente, "nome", "") or "").strip()
    if not empresa_nome:
        raise ValueError("Cliente without nome")

    # Se já usado e tem attempt_id, só seguir
    if inv.status in ("OPENED", "COMPLETED") and inv.attempt_id:
        return InviteStartResult(token=token)

    # Se já existe attempt com este token_hash, só seguir e sincronizar invite -> OPENED
    existing = await repo_attempt.get_attempt_by_token_hash(session, th)
    if existing:
        await repo_invite.mark_invite_opened(session, invite_id=inv.id, attempt_id=existing.id)
        await session.commit()
        return InviteStartResult(token=token)

    # Criar Participant + Attempt usando contexto do invite
    attempt = await repo_attempt.create_participant_and_attempt_from_invite(
        session,
        invite_id=inv.id,
        nome=nome,
        sobrenome=sobrenome,
        email=email,
        empresa_nome=empresa_nome,
        tipo_aplicacao=inv.tipo_aplicacao,
        token_hash_hex=th,
        cliente_id=inv.cliente_id,
        rodada_id=inv.rodada_id,
        setor_id=inv.setor_id,
        cargo=inv.cargo,
    )

    await repo_invite.mark_invite_opened(session, invite_id=inv.id, attempt_id=attempt.id)
    await session.commit()

    return InviteStartResult(token=token)
