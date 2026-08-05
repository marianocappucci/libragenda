"""Secondary resources, agenda policies, availability validity and history.

Everything here is additive: existing rows keep behaving exactly as before,
since an appointment with no secondary resource competes only for its own
one, an availability window with no validity applies always, and a resource
with no policy books back-to-back and refuses overbooking.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_agenda_occupancy_and_history"
down_revision = "0008_deposit_medio_pago"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("availability", sa.Column("valid_from", sa.Date(), nullable=True))
    op.add_column("availability", sa.Column("valid_to", sa.Date(), nullable=True))
    # server_default is required, not cosmetic: without it the NOT NULL column
    # cannot be added to a table that already has rows.
    op.add_column(
        "appointments",
        sa.Column("overbooked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "appointment_resources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "appointment_id", sa.String(100),
            sa.ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "resource_id", sa.String(100), sa.ForeignKey("resources.id"), nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "appointment_id", "resource_id", name="uq_appointment_resources_pair",
        ),
    )
    op.create_index(
        "ix_appointment_resources_appointment_id", "appointment_resources", ["appointment_id"],
    )
    op.create_index(
        "ix_appointment_resources_resource_id", "appointment_resources", ["resource_id"],
    )

    op.create_table(
        "appointment_transitions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "appointment_id", sa.String(100),
            sa.ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("from_status", sa.String(30), nullable=True),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(200), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_appointment_transitions_appointment_id", "appointment_transitions",
        ["appointment_id"],
    )
    op.create_index(
        "ix_appointment_transitions_to_status", "appointment_transitions", ["to_status"],
    )
    op.create_index("ix_appointment_transitions_at", "appointment_transitions", ["at"])

    op.create_table(
        "agenda_policies",
        sa.Column(
            "resource_id", sa.String(100), sa.ForeignKey("resources.id"), primary_key=True,
        ),
        sa.Column("slot_interval_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "max_overbookings_per_day", sa.Integer(), nullable=False, server_default="0",
        ),
    )

def downgrade():
    op.drop_table("agenda_policies")
    op.drop_index("ix_appointment_transitions_at", table_name="appointment_transitions")
    op.drop_index(
        "ix_appointment_transitions_to_status", table_name="appointment_transitions",
    )
    op.drop_index(
        "ix_appointment_transitions_appointment_id", table_name="appointment_transitions",
    )
    op.drop_table("appointment_transitions")
    op.drop_index(
        "ix_appointment_resources_resource_id", table_name="appointment_resources",
    )
    op.drop_index(
        "ix_appointment_resources_appointment_id", table_name="appointment_resources",
    )
    op.drop_table("appointment_resources")
    # SQLite has no ALTER DROP COLUMN, so the table is rebuilt copy-and-move;
    # on PostgreSQL this is a plain ALTER with the same outcome.
    with op.batch_alter_table("appointments") as batch_op:
        batch_op.drop_column("overbooked")
    with op.batch_alter_table("availability") as batch_op:
        batch_op.drop_column("valid_to")
        batch_op.drop_column("valid_from")
