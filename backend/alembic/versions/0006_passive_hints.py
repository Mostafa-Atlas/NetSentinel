"""Opt-in passive mDNS/SSDP hints.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "network_scopes",
        sa.Column("passive_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "device_hints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE")),
        sa.Column("scan_run_id", sa.Integer(), sa.ForeignKey("scan_runs.id", ondelete="CASCADE")),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_device_hints_device_id", "device_hints", ["device_id"])


def downgrade() -> None:
    op.drop_table("device_hints")
    op.drop_column("network_scopes", "passive_enabled")
