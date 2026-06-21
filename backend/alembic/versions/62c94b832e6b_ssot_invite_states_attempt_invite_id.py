"""SSOT invite states + attempt invite_id

Revision ID: 62c94b832e6b
Revises: inv829178527
Create Date: 2026-03-19 20:07:52+0000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "62c94b832e6b"
down_revision = "inv829178527"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # invites: add SSOT fields
    op.add_column("invites", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "invites",
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # attempts: add invite_id (FK + UNIQUE)
    op.add_column("attempts", sa.Column("invite_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_unique_constraint("uq_attempts_invite_id", "attempts", ["invite_id"])
    op.create_foreign_key(
        "fk_attempts_invite_id",
        "attempts",
        "invites",
        ["invite_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- data migration: old -> SSOT statuses ---
    # NEW     -> PENDING
    # REVOKED -> CANCELLED
    # USED    -> OPENED (and if attempt is SUBMITTED => COMPLETED)
    op.execute("UPDATE invites SET status='PENDING'   WHERE status='NEW';")
    op.execute("UPDATE invites SET status='CANCELLED' WHERE status='REVOKED';")
    op.execute("UPDATE invites SET status='OPENED'    WHERE status='USED';")

    op.execute(
        """
        UPDATE invites i
        SET status='COMPLETED', ativo=false, atualizado_em=now()
        FROM attempts a
        WHERE i.attempt_id = a.id
          AND a.status = 'SUBMITTED'
          AND i.status = 'OPENED';
        """
    )

    # keep ativo consistent (compat field)
    op.execute("UPDATE invites SET ativo=false, atualizado_em=now() WHERE status IN ('CANCELLED','EXPIRED','COMPLETED');")
    op.execute("UPDATE invites SET ativo=true,  atualizado_em=now() WHERE status IN ('PENDING','OPENED');")

    # backfill atualizado_em for old rows
    op.execute("UPDATE invites SET atualizado_em = COALESCE(atualizado_em, now());")


def downgrade() -> None:
    op.drop_constraint("fk_attempts_invite_id", "attempts", type_="foreignkey")
    op.drop_constraint("uq_attempts_invite_id", "attempts", type_="unique")
    op.drop_column("attempts", "invite_id")

    op.drop_column("invites", "atualizado_em")
    op.drop_column("invites", "expires_at")

    # conservative reverse mapping
    op.execute("UPDATE invites SET status='NEW' WHERE status='PENDING';")
    op.execute("UPDATE invites SET status='REVOKED' WHERE status='CANCELLED';")
    op.execute("UPDATE invites SET status='USED' WHERE status IN ('OPENED','COMPLETED','EXPIRED');")
