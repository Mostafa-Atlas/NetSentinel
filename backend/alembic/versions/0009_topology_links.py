"""Owner supplied topology links.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topology_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("note", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "target_id", name="uq_topology_link_pair"),
        sa.CheckConstraint("source_id < target_id", name="ck_topology_link_order"),
    )
    op.create_index("ix_topology_links_source_id", "topology_links", ["source_id"])
    op.create_index("ix_topology_links_target_id", "topology_links", ["target_id"])


def downgrade() -> None:
    op.drop_table("topology_links")
