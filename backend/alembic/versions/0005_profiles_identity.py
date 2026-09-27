"""Named network profiles and address provenance for identity review.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "network_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        "INSERT INTO network_profiles (id, name, description, created_at) "
        "VALUES (1, 'Default', 'Existing approved ranges', CURRENT_TIMESTAMP)"
    )
    with op.batch_alter_table(
        "network_scopes", naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"}
    ) as batch:
        batch.add_column(
            sa.Column(
                "profile_id",
                sa.Integer(),
                sa.ForeignKey("network_profiles.id", name="fk_network_scopes_profile_id"),
            )
        )
        batch.drop_constraint("uq_network_scopes_cidr", type_="unique")
        batch.create_unique_constraint("uq_scope_profile_cidr", ["profile_id", "cidr"])
    op.execute("UPDATE network_scopes SET profile_id = 1")
    op.create_index("ix_network_scopes_profile_id", "network_scopes", ["profile_id"])
    with op.batch_alter_table("devices") as batch:
        batch.add_column(
            sa.Column(
                "profile_id",
                sa.Integer(),
                sa.ForeignKey("network_profiles.id", name="fk_devices_profile_id"),
            )
        )
    op.execute("UPDATE devices SET profile_id = 1")
    op.create_index("ix_devices_profile_id", "devices", ["profile_id"])
    op.add_column("observations", sa.Column("ip", sa.String(45)))


def downgrade() -> None:
    op.drop_column("observations", "ip")
    op.drop_index("ix_devices_profile_id", "devices")
    with op.batch_alter_table("devices") as batch:
        batch.drop_column("profile_id")
    op.drop_index("ix_network_scopes_profile_id", "network_scopes")
    with op.batch_alter_table("network_scopes") as batch:
        batch.drop_constraint("uq_scope_profile_cidr", type_="unique")
        batch.create_unique_constraint("uq_network_scopes_cidr", ["cidr"])
        batch.drop_column("profile_id")
    op.drop_table("network_profiles")
