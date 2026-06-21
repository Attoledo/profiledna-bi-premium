"""invites table fix

Revision ID: inv829178527
Revises: 9283a14f4850
Create Date: 2026-03-17 00:00:00

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "inv829178527"
down_revision = "9283a14f4850"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("cliente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clientes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("rodada_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rodadas_aplicacao.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("setor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("setores_empresa.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cargo", sa.String(length=255), nullable=True),
        sa.Column("tipo_aplicacao", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="NEW"),
        sa.Column("criado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("usado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("attempts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_index("ix_invites_token_hash", "invites", ["token_hash"], unique=True)
    op.create_index("ix_invites_cliente_id", "invites", ["cliente_id"], unique=False)
    op.create_index("ix_invites_rodada_id", "invites", ["rodada_id"], unique=False)
    op.create_index("ix_invites_setor_id", "invites", ["setor_id"], unique=False)
    op.create_index("ix_invites_status", "invites", ["status"], unique=False)
    op.create_index("ix_invites_ativo", "invites", ["ativo"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_invites_ativo", table_name="invites")
    op.drop_index("ix_invites_status", table_name="invites")
    op.drop_index("ix_invites_setor_id", table_name="invites")
    op.drop_index("ix_invites_rodada_id", table_name="invites")
    op.drop_index("ix_invites_cliente_id", table_name="invites")
    op.drop_index("ix_invites_token_hash", table_name="invites")
    op.drop_table("invites")
