"""Discovery jobs and immutable network observations.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope_id", sa.Integer(), sa.ForeignKey("network_scopes.id"), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("host_count", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.String(500)),
    )
    op.create_index("ix_scan_runs_scope_id", "scan_runs", ["scope_id"])
    op.create_index("ix_scan_runs_status", "scan_runs", ["status"])
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("identity_confidence", sa.String(20), nullable=False),
        sa.Column("known_state", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "device_addresses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("mac", sa.String(17)),
        sa.Column("hostname", sa.String(255)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_device_addresses_device_id", "device_addresses", ["device_id"])
    op.create_index("ix_device_addresses_ip", "device_addresses", ["ip"])
    op.create_index("ix_device_addresses_mac", "device_addresses", ["mac"])
    op.create_table(
        "observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scan_run_id",
            sa.Integer(),
            sa.ForeignKey("scan_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("reachable", sa.Boolean()),
        sa.Column("latency_ms", sa.Float()),
        sa.Column("raw_summary", sa.String(255), nullable=False),
    )
    op.create_index("ix_observations_device_id", "observations", ["device_id"])
    op.create_index("ix_observations_scan_run_id", "observations", ["scan_run_id"])
    op.create_index("ix_observations_observed_at", "observations", ["observed_at"])
    op.create_table(
        "service_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scan_run_id",
            sa.Integer(),
            sa.ForeignKey("scan_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.String(8), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_service_observations_device_id", "service_observations", ["device_id"])
    op.create_index("ix_service_observations_scan_run_id", "service_observations", ["scan_run_id"])
    op.create_index("ix_service_observations_observed_at", "service_observations", ["observed_at"])


def downgrade() -> None:
    for table in (
        "service_observations",
        "observations",
        "device_addresses",
        "devices",
        "scan_runs",
    ):
        op.drop_table(table)
