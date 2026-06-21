from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Cliente(Base):
    """
    SSOT 7.1 + decisão operacional atual:
    clientes
        id,
        nome,
        razao_social,
        cnpj,
        endereco,
        setor_mercado,
        responsavel,
        setor_responsavel,
        email_responsavel,
        ativo,
        criado_em

    Regra vigente:
    - Cliente representa somente empresa contratante (PJ)
    - Não há suporte a pessoa física neste modelo
    """

    __tablename__ = "clientes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    razao_social: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cnpj: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    endereco: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    setor_mercado: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    responsavel: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    setor_responsavel: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email_responsavel: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    ativo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    setores: Mapped[List["SetorEmpresa"]] = relationship(
        back_populates="cliente",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    rodadas: Mapped[List["RodadaAplicacao"]] = relationship(
        back_populates="cliente",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SetorEmpresa(Base):
    """
    SSOT 7.1:
    setores_empresa
        id, cliente_id (FK→clientes), nome
    """

    __tablename__ = "setores_empresa"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    cliente: Mapped["Cliente"] = relationship(back_populates="setores")


class RodadaAplicacao(Base):
    """
    SSOT 7.1:
    rodadas_aplicacao
        id, cliente_id (FK→clientes), nome, data_inicio, data_encerramento, criado_por (FK→admin_users)
    """

    __tablename__ = "rodadas_aplicacao"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    data_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    data_encerramento: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    criado_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    cliente: Mapped["Cliente"] = relationship(back_populates="rodadas")
