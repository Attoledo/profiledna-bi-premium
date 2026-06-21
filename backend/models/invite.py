from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Nunca armazenar token em claro: guardar hash (64 hex).
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

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

    tipo_aplicacao: Mapped[str] = mapped_column(String(32), nullable=False)

    # SSOT states: PENDING | OPENED | COMPLETED | CANCELLED | EXPIRED
    # DB default já é PENDING
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="PENDING", index=True)

    criado_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    usado_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attempts.id", ondelete="SET NULL"),
        nullable=True,
    )

    ativo: Mapped[bool] = mapped_column(Boolean(), nullable=False, server_default="true")

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
