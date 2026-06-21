from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.attempt import Answer, Attempt, Participant


async def create_participant_and_attempt_default_seed(
    session: AsyncSession,
    *,
    nome: str,
    sobrenome: Optional[str],
    email: Optional[str],
    empresa_nome: Optional[str] = None,
    tipo_aplicacao: str,
    token_hash_hex: str,
    testdef_version: str = "v1",
) -> Attempt:
    """
    Cria Participant + Attempt usando os DEFAULT_* do ambiente atual.
    """
    p = Participant(
        nome=nome,
        sobrenome=sobrenome,
        email=email,
        empresa_nome=empresa_nome,
        tipo_aplicacao=tipo_aplicacao,
    )
    session.add(p)
    await session.flush()

    # Bootstrap atual do MVP: usa 1 cliente/rodada/setor seeded.
    # Mantido como no runtime atual.
    from backend.models.cliente import Cliente, RodadaAplicacao, SetorEmpresa

    cliente = (
        await session.execute(
            select(Cliente).order_by(Cliente.criado_em.asc()).limit(1)
        )
    ).scalar_one()

    rodada = (
        await session.execute(
            select(RodadaAplicacao)
            .where(RodadaAplicacao.cliente_id == cliente.id)
            .order_by(RodadaAplicacao.data_inicio.asc())
            .limit(1)
        )
    ).scalar_one()

    setor = (
        await session.execute(
            select(SetorEmpresa)
            .where(SetorEmpresa.cliente_id == cliente.id)
            .order_by(SetorEmpresa.nome.asc())
            .limit(1)
        )
    ).scalar_one_or_none()

    attempt = Attempt(
        token_hash=token_hash_hex,
        participant_id=p.id,
        cliente_id=cliente.id,
        rodada_id=rodada.id,
        setor_id=setor.id if setor else None,
        cargo=None,
        status="IN_PROGRESS",
        progress=0,
        testdef_version=testdef_version,
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def get_attempt_by_token_hash(session: AsyncSession, token_hash_hex: str) -> Optional[Attempt]:
    res = await session.execute(
        select(Attempt).where(Attempt.token_hash == token_hash_hex)
    )
    return res.scalar_one_or_none()


async def get_attempt_by_token(session: AsyncSession, token: str) -> Optional[Attempt]:
    from backend.services.token import token_hash

    th = token_hash(token)
    return await get_attempt_by_token_hash(session, th)


async def list_answers_by_attempt_id(session: AsyncSession, attempt_id) -> list[Answer]:
    res = await session.execute(
        select(Answer)
        .where(Answer.attempt_id == attempt_id)
        .order_by(Answer.question_number.asc())
    )
    return list(res.scalars().all())


async def upsert_answer(
    session: AsyncSession,
    *,
    attempt_id,
    question_number: int,
    choice: str,
    letter_scored: str,
) -> None:
    res = await session.execute(
        select(Answer).where(
            Answer.attempt_id == attempt_id,
            Answer.question_number == int(question_number),
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        existing.choice = choice
        existing.letter_scored = letter_scored
        session.add(existing)
        return

    ans = Answer(
        attempt_id=attempt_id,
        question_number=int(question_number),
        choice=choice,
        letter_scored=letter_scored,
    )
    session.add(ans)


async def count_answers_by_attempt_id(session: AsyncSession, attempt_id) -> int:
    res = await session.execute(
        select(func.count(Answer.id)).where(Answer.attempt_id == attempt_id)
    )
    return int(res.scalar_one() or 0)


def clamp_progress(answered_count: int) -> int:
    """
    SSOT: progress é 0..100 e, como são 100 questões, progress == answered_count (%).
    """
    if answered_count < 0:
        return 0
    if answered_count > 100:
        return 100
    return answered_count


async def recompute_progress(session: AsyncSession, attempt: Attempt) -> int:
    answered_count = await count_answers_by_attempt_id(session, attempt.id)
    attempt.progress = clamp_progress(answered_count)
    session.add(attempt)
    return int(attempt.progress or 0)


async def get_tipo_aplicacao_by_attempt(session: AsyncSession, attempt: Attempt) -> str:
    """
    Fonte: Participant.tipo_aplicacao (SSOT).
    """
    try:
        part = getattr(attempt, "participant", None)
        if part is not None:
            t = getattr(part, "tipo_aplicacao", None)
            if isinstance(t, str) and t.strip():
                return t.strip().lower()
    except Exception:
        pass

    res = await session.execute(
        select(Participant.tipo_aplicacao).where(Participant.id == attempt.participant_id)
    )
    t = res.scalar_one_or_none()
    if isinstance(t, str) and t.strip():
        return t.strip().lower()
    return "pessoal"


async def create_participant_and_attempt_from_invite(
    session: AsyncSession,
    *,
    nome: str,
    sobrenome: Optional[str],
    email: Optional[str],
    empresa_nome: Optional[str] = None,
    tipo_aplicacao: str,
    token_hash_hex: str,
    cliente_id,
    rodada_id,
    setor_id,
    cargo: Optional[str],
    invite_id,
    testdef_version: str = "v1",
) -> Attempt:
    """
    Cria Participant + Attempt usando o contexto vindo do Invite.
    """
    p = Participant(
        nome=nome,
        sobrenome=sobrenome,
        email=email,
        empresa_nome=empresa_nome,
        tipo_aplicacao=tipo_aplicacao,
    )
    session.add(p)
    await session.flush()

    attempt = Attempt(
        invite_id=invite_id,
        token_hash=token_hash_hex,
        participant_id=p.id,
        cliente_id=cliente_id,
        rodada_id=rodada_id,
        setor_id=setor_id,
        cargo=cargo,
        status="IN_PROGRESS",
        progress=0,
        testdef_version=testdef_version,
    )
    session.add(attempt)
    await session.flush()
    return attempt
