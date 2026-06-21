from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class ComputedResult(Base):
    """
    SSOT 6.11 (result.py):
    computed_results (imutável):
      id, attempt_id UNIQUE,
      scores JSONB, bands JSONB, top3 JSONB, top5 JSONB, bottom3 JSONB,
      interpretations JSONB, premium_data JSONB
    """
    __tablename__ = "computed_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attempts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    scores: Mapped[dict] = mapped_column(JSONB, nullable=False)
    bands: Mapped[dict] = mapped_column(JSONB, nullable=False)

    top3: Mapped[dict] = mapped_column(JSONB, nullable=False)
    top5: Mapped[dict] = mapped_column(JSONB, nullable=False)
    bottom3: Mapped[dict] = mapped_column(JSONB, nullable=False)

    interpretations: Mapped[dict] = mapped_column(JSONB, nullable=False)
    premium_data: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ReportSnapshot(Base):
    """
    SSOT 6.11 (result.py):
    report_snapshots:
      id, attempt_id UNIQUE, html_content TEXT, pdf_path, generated_at
    """
    __tablename__ = "report_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attempts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    html_content: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PremiumReportSnapshot(Base):
    """
    Addendum 2026-05-10:
    snapshot premium separado do snapshot técnico.

    Regras:
      - 1 attempt_id -> 1 snapshot premium
      - html_content e pdf_path independentes do técnico
      - preserva histórico por attempt
    """
    __tablename__ = "premium_report_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attempts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    html_content: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
