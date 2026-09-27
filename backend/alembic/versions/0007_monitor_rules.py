"""Per-device service rule settings and scan-backed checks.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitor_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE")),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("failure_threshold", sa.Integer(), nullable=False),
        sa.Column("quiet_start_hour", sa.Integer()),
        sa.Column("quiet_end_hour", sa.Integer()),
        sa.Column("maintenance_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("device_id", "port", name="uq_monitor_rule_device_port"),
    )
    op.create_index("ix_monitor_rules_device_id", "monitor_rules", ["device_id"])
    op.create_table(
        "monitor_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("monitor_rules.id", ondelete="CASCADE")),
        sa.Column("scan_run_id", sa.Integer(), sa.ForeignKey("scan_runs.id", ondelete="CASCADE")),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("suppressed", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("rule_id", "scan_run_id", name="uq_monitor_check_run"),
    )
    op.create_index("ix_monitor_checks_rule_id", "monitor_checks", ["rule_id"])


def downgrade() -> None:
    op.drop_table("monitor_checks")
    op.drop_table("monitor_rules")
