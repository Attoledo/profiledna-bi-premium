"""create premium_report_snapshots

Revision ID: 20260510_01
Revises: 
Create Date: 2026-05-10 15:20:00

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260510_01"
down_revision = "20260406_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "premium_report_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "attempt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("html_content", sa.Text(), nullable=False),
        sa.Column("pdf_path", sa.Text(), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("attempt_id", name="uq_premium_report_snapshots_attempt_id"),
    )

    op.create_index(
        "ix_premium_report_snapshots_attempt_id",
        "premium_report_snapshots",
        ["attempt_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_premium_report_snapshots_attempt_id",
        table_name="premium_report_snapshots",
    )
    op.drop_table("premium_report_snapshots")
