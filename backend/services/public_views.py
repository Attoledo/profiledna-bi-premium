from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.attempt import Attempt
from backend.repositories import attempt as repo_attempt
from backend.repositories import result as repo_result
from backend.reports.pdf import ensure_pdf_cached
from backend.services.submit import (
    _build_attempt_payload,
    _build_gestor_rh_payload,
    _build_nota_tecnica_payload,
    _build_paineis_area_payload,
    _build_participant_payload,
    _build_pdi_competencias_payload,
    _build_sintese_executiva_payload,
    _load_dimensions_map,
)


class PublicFlowNotFound(Exception):
    pass


@dataclass(frozen=True)
class ReviewContext:
    attempt: Attempt
    answered_count: int
    progress: int
    next_question: int
    is_submitted: bool


@dataclass(frozen=True)
class ReportContext:
    attempt: Attempt
    participant: Dict[str, Any]
    attempt_payload: Dict[str, Any]
    scores: Dict[str, Any]
    bands: Dict[str, Any]
    ranking: Dict[str, Any]
    interpretations: Dict[str, Any]
    sintese_executiva: Dict[str, Any]
    paineis_area: List[Dict[str, Any]]
    pdi_competencias: List[Dict[str, Any]]
    gestor_rh: Dict[str, Any]
    nota_tecnica: Dict[str, Any]
    report_template: str


async def _get_attempt_or_404(session: AsyncSession, token: str) -> Attempt:
    attempt = await repo_attempt.get_attempt_by_token(session, token)
    if not attempt:
        raise PublicFlowNotFound("Invalid token")
    return attempt


async def build_review_context(session: AsyncSession, token: str) -> ReviewContext:
    attempt = await _get_attempt_or_404(session, token)

    answers = await repo_attempt.list_answers_by_attempt_id(session, attempt.id)
    answered_count = len(answers)

    raw_progress = int(attempt.progress or 0)
    progress = 100 if answered_count >= 100 else raw_progress

    answered_numbers = {int(answer.question_number) for answer in answers}
    next_q = 1
    for i in range(1, 101):
        if i not in answered_numbers:
            next_q = i
            break
    else:
        next_q = 100

    is_submitted = str(attempt.status or "").upper() == "SUBMITTED"

    return ReviewContext(
        attempt=attempt,
        answered_count=answered_count,
        progress=progress,
        next_question=next_q,
        is_submitted=is_submitted,
    )


async def build_report_context(session: AsyncSession, token: str) -> ReportContext:
    attempt = await _get_attempt_or_404(session, token)

    computed = await repo_result.get_computed_result_by_attempt_id(session, attempt.id)
    if not computed:
        raise PublicFlowNotFound("No computed result yet")

    ranking = {
        "top3": (computed.top3 or {}).get("top3", []),
        "top5": (computed.top5 or {}).get("top5", []),
        "bottom3": (computed.bottom3 or {}).get("bottom3", []),
    }

    participant_payload = await _build_participant_payload(session, attempt)
    attempt_payload = _build_attempt_payload(attempt)
    dims = _load_dimensions_map()

    interpretations = computed.interpretations or {}
    scores = computed.scores or {}
    bands = computed.bands or {}

    sintese_executiva = _build_sintese_executiva_payload(
        participant_payload=participant_payload,
        ranking=ranking,
        interpretations=interpretations,
        dims=dims,
    )
    paineis_area = _build_paineis_area_payload(
        scores=scores,
        bands=bands,
        interpretations=interpretations,
        dims=dims,
    )
    pdi_competencias = _build_pdi_competencias_payload(
        ranking=ranking,
        interpretations=interpretations,
        dims=dims,
    )
    gestor_rh = _build_gestor_rh_payload(
        participant_payload=participant_payload,
        ranking=ranking,
        interpretations=interpretations,
        dims=dims,
    )
    nota_tecnica = _build_nota_tecnica_payload()

    return ReportContext(
        attempt=attempt,
        participant=participant_payload,
        attempt_payload=attempt_payload,
        scores=scores,
        bands=bands,
        ranking=ranking,
        interpretations=interpretations,
        sintese_executiva=sintese_executiva,
        paineis_area=paineis_area,
        pdi_competencias=pdi_competencias,
        gestor_rh=gestor_rh,
        nota_tecnica=nota_tecnica,
        report_template="reports/report_full.html",
    )


async def ensure_report_pdf(session: AsyncSession, token: str) -> tuple[str, str]:
    """
    Retorna (attempt_id_str, pdf_path).

    Regras do fluxo:
      - precisa existir ReportSnapshot (criado no submit)
      - gera/cacheia PDF
    """
    attempt = await _get_attempt_or_404(session, token)

    snapshot = await repo_result.get_report_snapshot_by_attempt_id(session, attempt.id)
    if not snapshot:
        raise PublicFlowNotFound("No report snapshot yet")

    pdf_path = await ensure_pdf_cached(session, str(attempt.id))
    return (str(attempt.id), pdf_path)
