from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# ComputedResult
# ---------------------------------------------------------------------------

class ComputedResultResponse(BaseModel):
    """
    SSOT 6.11 (result.py): computed_results (imutável).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attempt_id: UUID
    scores: dict[str, Any]
    bands: dict[str, Any]
    top3: dict[str, Any]
    top5: dict[str, Any]
    bottom3: dict[str, Any]
    interpretations: dict[str, Any]
    premium_data: dict[str, Any]


# ---------------------------------------------------------------------------
# ReportSnapshot
# ---------------------------------------------------------------------------

class ReportSnapshotResponse(BaseModel):
    """
    SSOT 6.11 (result.py): report_snapshots.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attempt_id: UUID
    html_content: str
    pdf_path: Optional[str] = None
    generated_at: datetime


# ---------------------------------------------------------------------------
# PremiumReportSnapshot
# ---------------------------------------------------------------------------

class PremiumReportSnapshotResponse(BaseModel):
    """
    Addendum 2026-05-10: snapshot premium separado do snapshot técnico.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attempt_id: UUID
    html_content: str
    pdf_path: Optional[str] = None
    generated_at: datetime
