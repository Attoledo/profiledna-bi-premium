from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.attempt import Attempt
from backend.repositories import attempt as repo_attempt


async def get_attempt_by_token(session: AsyncSession, token: str) -> Optional[Attempt]:
    """
    Compat wrapper (routers chamam isso hoje).
    Implementação SSOT: service não faz query; delega ao repository.
    """
    return await repo_attempt.get_attempt_by_token(session, token)


async def upsert_answer(
    session: AsyncSession,
    attempt_id,
    question_number: int,
    choice: str,
    letter_scored: str,
) -> None:
    """
    Compat wrapper.
    """
    await repo_attempt.upsert_answer(
        session,
        attempt_id=attempt_id,
        question_number=int(question_number),
        choice=choice,
        letter_scored=letter_scored,
    )


async def recompute_progress(session: AsyncSession, attempt: Attempt) -> int:
    """
    Compat wrapper.
    """
    return await repo_attempt.recompute_progress(session, attempt)
