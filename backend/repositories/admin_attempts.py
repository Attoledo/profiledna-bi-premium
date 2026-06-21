from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.attempt import Attempt, Participant


@dataclass(frozen=True)
class AttemptListRow:
    id: str
    status: str
    progress: int
    data_inicio: str
    data_conclusao: Optional[str]
    participant_nome: str
    participant_email: Optional[str]
    cargo: Optional[str]
    setor_id: Optional[str]


async def list_attempts_by_rodada(
    session: AsyncSession,
    rodada_id,
    setor_id: Optional[str] = None,
    limit: int = 500,
) -> List[AttemptListRow]:
    q = (
        select(Attempt)
        .options(selectinload(Attempt.participant))
        .where(Attempt.rodada_id == rodada_id)
        .order_by(Attempt.data_inicio.desc())
        .limit(limit)
    )
    if setor_id:
        q = q.where(Attempt.setor_id == setor_id)

    res = await session.execute(q)
    attempts = list(res.scalars().all())

    out: List[AttemptListRow] = []
    for a in attempts:
        p: Participant = a.participant
        nome = p.nome if getattr(p, "nome", None) else "(sem nome)"
        email = getattr(p, "email", None)
        out.append(
            AttemptListRow(
                id=str(a.id),
                status=str(a.status),
                progress=int(a.progress),
                data_inicio=str(a.data_inicio),
                data_conclusao=str(a.data_conclusao) if a.data_conclusao else None,
                participant_nome=nome,
                participant_email=email,
                cargo=getattr(a, "cargo", None),
                setor_id=str(a.setor_id) if a.setor_id else None,
            )
        )
    return out
