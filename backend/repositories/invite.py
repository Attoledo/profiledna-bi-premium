from __future__ import annotations

import sqlalchemy as sa

from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.invite import Invite


async def create_invite(
    session: AsyncSession,
    *,
    token_hash: str,
    cliente_id,
    rodada_id,
    setor_id,
    cargo: Optional[str],
    tipo_aplicacao: str,
    criado_por,
) -> Invite:
    inv = Invite(
        token_hash=token_hash,
        cliente_id=cliente_id,
        rodada_id=rodada_id,
        setor_id=setor_id,
        cargo=cargo,
        tipo_aplicacao=tipo_aplicacao,
        status="PENDING",
        criado_por=criado_por,
        ativo=True,
    )
    session.add(inv)
    await session.flush()
    return inv


async def list_invites_by_rodada(
    session: AsyncSession,
    *,
    rodada_id,
    limit: int = 200,
) -> List[Invite]:
    res = await session.execute(
        select(Invite)
        .where(Invite.rodada_id == rodada_id)
        .order_by(Invite.criado_em.desc())
        .limit(limit)
    )
    return list(res.scalars().all())


async def get_invite_by_id(session: AsyncSession, invite_id) -> Optional[Invite]:
    res = await session.execute(select(Invite).where(Invite.id == invite_id))
    return res.scalar_one_or_none()


async def revoke_invite(session: AsyncSession, *, invite_id, admin_id) -> None:
    # simples: marca como REVOKED e inativo
    await session.execute(
        update(Invite)
        .where(Invite.id == invite_id)
        .values(status="CANCELLED", ativo=False, atualizado_em=sa.func.now())
    )


async def get_invite_by_token_hash(session: AsyncSession, token_hash: str) -> Optional[Invite]:
    res = await session.execute(select(Invite).where(Invite.token_hash == token_hash))
    return res.scalar_one_or_none()


async def mark_invite_used(session: AsyncSession, *, invite_id, attempt_id) -> None:
    # marca como USED e salva vínculo com attempt
    await session.execute(
        update(Invite)
        .where(Invite.id == invite_id)
        .values(status="USED", ativo=False, attempt_id=attempt_id, usado_em=sa.func.now())
    )


async def mark_invite_opened(session: AsyncSession, *, invite_id, attempt_id) -> None:
    # SSOT: PENDING -> OPENED ao criar Attempt; vincula attempt_id e marca inativo
    await session.execute(
        update(Invite)
        .where(Invite.id == invite_id)
        .values(
            status="OPENED",
            ativo=False,
            attempt_id=attempt_id,
            usado_em=sa.func.now(),
            atualizado_em=sa.func.now(),
        )
    )


async def mark_invite_completed(session: AsyncSession, *, invite_id) -> None:
    # SSOT 7.3: OPENED -> COMPLETED quando attempt é submetido
    await session.execute(
        update(Invite)
        .where(Invite.id == invite_id)
        .values(status="COMPLETED", ativo=False, atualizado_em=sa.func.now())
    )
