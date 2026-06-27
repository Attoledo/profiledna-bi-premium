"""add role, requires_reset and permissions to admin_users

Revision ID: 20260625_01
Revises: 20260510_01
Create Date: 2026-06-25 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260625_01"
down_revision = "20260510_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("role", sa.String(length=50), nullable=False, server_default="admin"),
    )
    op.add_column(
        "admin_users",
        sa.Column(
            "requires_reset",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "admin_users",
        sa.Column(
            "permissions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("admin_users", "permissions")
    op.drop_column("admin_users", "requires_reset")
    op.drop_column("admin_users", "role")
