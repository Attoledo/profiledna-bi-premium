"""add cliente pj fields

Revision ID: 20260329_01
Revises: 9f1b6d2a4c31
Create Date: 2026-03-29 10:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260329_01"
down_revision = "9f1b6d2a4c31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clientes",
        sa.Column("razao_social", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "clientes",
        sa.Column("cnpj", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "clientes",
        sa.Column("endereco", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "clientes",
        sa.Column("setor_responsavel", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clientes", "setor_responsavel")
    op.drop_column("clientes", "endereco")
    op.drop_column("clientes", "cnpj")
    op.drop_column("clientes", "razao_social")
