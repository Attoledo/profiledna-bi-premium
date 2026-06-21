# /srv/profiledna/backend/ai_analyst/models.py
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class AIInteractionLog(Base):
    """
    Auditoria obrigatória das interações da DANA.

    Base:
    - SSOT_PROFILEDNA_v2_0.md (módulo IA / AIInteractionLog)
    - ADDENDUM_20260403_DANA_AI_ANALYST.md

    Objetivos:
    - rastrear perguntas e respostas do agente;
    - registrar escopo e contexto da análise;
    - registrar tools utilizadas;
    - registrar uso de BI e docsIA;
    - apoiar auditoria, troubleshooting, compliance e controle de custo.
    """

    __tablename__ = "ai_interaction_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Admin que realizou a interação com a DANA.",
    )

    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Cliente que define o scope obrigatório da interação.",
    )

    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attempts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Attempt relacionado, quando a pergunta for sobre participante específico.",
    )

    question_sanitized: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Pergunta já sanitizada, sem PII, efetivamente usada no fluxo do agente.",
    )

    tools_called: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Registro estruturado das tools chamadas durante a interação.",
    )

    response_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Resposta final entregue ao gestor/admin.",
    )

    prompt_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Versão do prompt utilizada na interação.",
    )

    model_used: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Modelo efetivamente utilizado na chamada LLM.",
    )

    tokens_input: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Quantidade de tokens de entrada da interação.",
    )

    tokens_output: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Quantidade de tokens de saída da interação.",
    )

    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
        default=Decimal("0.000000"),
        server_default="0",
        doc="Custo estimado em USD da interação.",
    )

    duration_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Duração total da interação em milissegundos.",
    )

    analysis_scope: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc=(
            "Escopo estruturado da análise. Ex.: cliente, rodada, setor, cargo, "
            "participantes selecionados e contexto comparativo."
        ),
    )

    filters_active: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Filtros ativos no momento da pergunta.",
    )

    report_sections_used: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        doc=(
            "Seções do relatório final utilizadas para compor a resposta. "
            "Ex.: Identificação, Síntese Executiva, Top5, Bottom3, PDI etc."
        ),
    )

    docsia_documents_used: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        doc="Lista de documentos da docsIA efetivamente usados na resposta.",
    )

    docsia_chunks_used: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        doc="Lista de chunks/trechos recuperados da docsIA usados na resposta.",
    )

    bi_context_used: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Contexto de BI utilizado: recortes, métricas, comparativos e visões agregadas.",
    )

    query_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="cliente",
        server_default="cliente",
        doc=(
            "Modo principal da consulta. Valores esperados pelo addendum: "
            "participante, grupo, cliente, comparativo."
        ),
    )

    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Timestamp de criação do log de auditoria.",
    )

    __table_args__ = (
        Index("idx_ai_logs_cliente", "cliente_id"),
        Index("idx_ai_logs_user", "admin_user_id"),
        Index("idx_ai_logs_attempt", "attempt_id"),
        Index("idx_ai_logs_created", "created_at"),
        Index("idx_ai_logs_query_mode", "query_mode"),
    )
    