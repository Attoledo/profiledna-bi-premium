"""add ai interaction logs

Revision ID: 20260406_01
Revises: 20260329_01
Create Date: 2026-04-06 10:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260406_01"
down_revision = "20260329_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_interaction_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "admin_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "cliente_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "attempt_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("question_sanitized", sa.Text(), nullable=False),
        sa.Column(
            "tools_called",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("model_used", sa.String(length=128), nullable=False),
        sa.Column(
            "tokens_input",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "tokens_output",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(12, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "duration_ms",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "analysis_scope",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "filters_active",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "report_sections_used",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "docsia_documents_used",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "docsia_chunks_used",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "bi_context_used",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "query_mode",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'cliente'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["admin_users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cliente_id"],
            ["clientes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("idx_ai_logs_cliente", "ai_interaction_logs", ["cliente_id"], unique=False)
    op.create_index("idx_ai_logs_user", "ai_interaction_logs", ["admin_user_id"], unique=False)
    op.create_index("idx_ai_logs_attempt", "ai_interaction_logs", ["attempt_id"], unique=False)
    op.create_index("idx_ai_logs_created", "ai_interaction_logs", ["created_at"], unique=False)
    op.create_index("idx_ai_logs_query_mode", "ai_interaction_logs", ["query_mode"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_ai_logs_query_mode", table_name="ai_interaction_logs")
    op.drop_index("idx_ai_logs_created", table_name="ai_interaction_logs")
    op.drop_index("idx_ai_logs_attempt", table_name="ai_interaction_logs")
    op.drop_index("idx_ai_logs_user", table_name="ai_interaction_logs")
    op.drop_index("idx_ai_logs_cliente", table_name="ai_interaction_logs")
    op.drop_table("ai_interaction_logs")
