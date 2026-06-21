from __future__ import annotations

import sqlalchemy as sa

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Participant(Base):
    """
    SSOT 6.11 (attempt.py):
    participants: id, nome, sobrenome, email, empresa_nome, tipo_aplicacao
    """
    __tablename__ = "participants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    sobrenome: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    empresa_nome: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # SSOT: tipo_aplicacao (ex.: "pessoal" | "empresa") — manter como string e validar via schema/serviço
    tipo_aplicacao: Mapped[str] = mapped_column(String(32), nullable=False)

    attempts: Mapped[List["Attempt"]] = relationship(
        back_populates="participant",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Attempt(Base):
    """
    SSOT 6.11 (attempt.py):
    attempts:
      id, token_hash UNIQUE, participant_id, cliente_id, rodada_id, setor_id,
      cargo, status, progress, data_inicio, data_conclusao, testdef_version
    """
    __tablename__ = "attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    rodada_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rodadas_aplicacao.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    setor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("setores_empresa.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    cargo: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # SSOT: status (enum no schema). Aqui: string persistida.
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # SSOT: progress (0..100). Aqui: int persistido.
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    data_inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    data_conclusao: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    testdef_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")

    # SSOT 7.1/7.4: vínculo opcional com Invite (1:1 quando originado de convite)
    invite_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invites.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )

    participant: Mapped["Participant"] = relationship(back_populates="attempts")

    answers: Mapped[List["Answer"]] = relationship(
        back_populates="attempt",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Answer(Base):
    """
    SSOT 6.11 (attempt.py):
    answers:
      id, attempt_id, question_number, choice, letter_scored, answered_at
      UNIQUE(attempt_id, question_number)
    """
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_number", name="uq_answers_attempt_question"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    question_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # SSOT: choice = "A" | "B" (validar via schema)
    choice: Mapped[str] = mapped_column(String(1), nullable=False)

    # SSOT: letter_scored (A..T) calculada no autosave via gabarito
    letter_scored: Mapped[str] = mapped_column(String(2), nullable=False)

    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    attempt: Mapped["Attempt"] = relationship(back_populates="answers")
