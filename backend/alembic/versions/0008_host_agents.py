"""Scoped host agent enrollment and replay records.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_enrollments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_agent_enrollments_device_id", "agent_enrollments", ["device_id"])
    op.create_table(
        "agent_nonces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "enrollment_id", sa.Integer(), sa.ForeignKey("agent_enrollments.id", ondelete="CASCADE")
        ),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("enrollment_id", "nonce", name="uq_agent_nonce"),
    )
    op.create_index("ix_agent_nonces_enrollment_id", "agent_nonces", ["enrollment_id"])
    op.create_table(
        "agent_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "enrollment_id", sa.Integer(), sa.ForeignKey("agent_enrollments.id", ondelete="CASCADE")
        ),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE")),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("os_name", sa.String(100), nullable=False),
        sa.Column("load_1m", sa.Float()),
        sa.Column("containers_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_agent_reports_enrollment_id", "agent_reports", ["enrollment_id"])
    op.create_index("ix_agent_reports_device_id", "agent_reports", ["device_id"])


def downgrade() -> None:
    op.drop_table("agent_reports")
    op.drop_table("agent_nonces")
    op.drop_table("agent_enrollments")
