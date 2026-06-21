"""add empresa_nome to participants

Revision ID: 9f1b6d2a4c31
Revises: a58c6dd22296
Create Date: 2026-03-22 09:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9f1b6d2a4c31"
down_revision = "a58c6dd22296"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "participants",
        sa.Column("empresa_nome", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("participants", "empresa_nome")
