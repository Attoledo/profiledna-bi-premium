"""invites table (stub)

Revision ID: 9283a14f4850
Revises: e482c64a233a
Create Date: 2026-03-17 00:00:00

"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "9283a14f4850"
down_revision = "e482c64a233a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Este arquivo existe para manter o grafo consistente.
    # A criação real da tabela invites ocorre na migration seguinte (inv829...).
    pass


def downgrade() -> None:
    pass
