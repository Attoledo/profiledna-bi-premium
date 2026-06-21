from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.result import ComputedResult, PremiumReportSnapshot, ReportSnapshot


# --- computed_results ---

async def get_computed_result_by_attempt_id(
    session: AsyncSession,
    attempt_id,
) -> ComputedResult | None:
    res = await session.execute(select(ComputedResult).where(ComputedResult.attempt_id == attempt_id))
    return res.scalar_one_or_none()


async def upsert_computed_result(
    session: AsyncSession,
    *,
    attempt_id,
    scores: dict,
    bands: dict,
    top3: list,
    top5: list,
    bottom3: list,
    interpretations: dict,
    premium_data: dict | None = None,
) -> ComputedResult:
    """
    Idempotente por attempt_id.
    """
    existing = await get_computed_result_by_attempt_id(session, attempt_id)
    if existing:
        existing.scores = scores
        existing.bands = bands
        existing.top3 = {"top3": top3}
        existing.top5 = {"top5": top5}
        existing.bottom3 = {"bottom3": bottom3}
        existing.interpretations = interpretations
        if premium_data is not None:
            existing.premium_data = premium_data
        session.add(existing)
        return existing

    cr = ComputedResult(
        attempt_id=attempt_id,
        scores=scores,
        bands=bands,
        top3={"top3": top3},
        top5={"top5": top5},
        bottom3={"bottom3": bottom3},
        interpretations=interpretations,
        premium_data=premium_data or {},
    )
    session.add(cr)
    return cr


# --- report_snapshots ---

async def get_report_snapshot_by_attempt_id(
    session: AsyncSession,
    attempt_id,
) -> ReportSnapshot | None:
    res = await session.execute(select(ReportSnapshot).where(ReportSnapshot.attempt_id == attempt_id))
    return res.scalar_one_or_none()


async def ensure_report_snapshot(
    session: AsyncSession,
    attempt_id,
    html_content: str,
) -> None:
    """
    Snapshot idempotente: se já existe, não recria.
    """
    existing = await get_report_snapshot_by_attempt_id(session, attempt_id)
    if existing:
        return
    snap = ReportSnapshot(attempt_id=attempt_id, html_content=html_content, pdf_path=None)
    session.add(snap)


# --- premium_report_snapshots ---

async def get_premium_report_snapshot_by_attempt_id(
    session: AsyncSession,
    attempt_id,
) -> PremiumReportSnapshot | None:
    res = await session.execute(
        select(PremiumReportSnapshot).where(PremiumReportSnapshot.attempt_id == attempt_id)
    )
    return res.scalar_one_or_none()


async def ensure_premium_report_snapshot(
    session: AsyncSession,
    attempt_id,
    html_content: str,
) -> None:
    """
    Snapshot premium idempotente: se já existe, não recria.

    Importante:
    - separado do snapshot técnico
    - vinculado por attempt_id
    - preserva congelamento do artefato premium
    """
    existing = await get_premium_report_snapshot_by_attempt_id(session, attempt_id)
    if existing:
        return
    snap = PremiumReportSnapshot(
        attempt_id=attempt_id,
        html_content=html_content,
        pdf_path=None,
    )
    session.add(snap)
