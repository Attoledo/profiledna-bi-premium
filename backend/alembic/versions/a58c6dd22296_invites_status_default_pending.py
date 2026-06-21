"""invites status default pending

Revision ID: a58c6dd22296
Revises: 62c94b832e6b
Create Date: 2026-03-19 20:14:32+0000

"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "a58c6dd22296"
down_revision = "62c94b832e6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SSOT: novos invites devem nascer como PENDING
    op.alter_column("invites", "status", server_default="PENDING")


def downgrade() -> None:
    op.alter_column("invites", "status", server_default="NEW")
