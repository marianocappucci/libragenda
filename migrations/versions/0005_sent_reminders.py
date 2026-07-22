"""Add sent_reminders ledger to track reminders already delivered."""
from alembic import op
import sqlalchemy as sa

revision = "0005_sent_reminders"
down_revision = "0004_appointment_series"
branch_labels = None
depends_on = None

def upgrade():
    # Unique constraint declared at create_table time (not a later ALTER):
    # SQLite can't ALTER a constraint onto a live table, only bake it in
    # at creation -- also just cleaner than a separate ALTER either way.
    op.create_table(
        "sent_reminders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("appointment_id", sa.String(100), sa.ForeignKey("appointments.id"), nullable=False),
        sa.Column("policy_id", sa.String(100), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("appointment_id", "policy_id", name="uq_sent_reminders_appointment_policy"),
    )
    op.create_index("ix_sent_reminders_appointment_id", "sent_reminders", ["appointment_id"])

def downgrade():
    # No need to drop the unique constraint separately -- drop_table below
    # takes it with it on every dialect, and SQLite can't ALTER a
    # constraint off a live table (only add it via create_table).
    op.drop_index("ix_sent_reminders_appointment_id", table_name="sent_reminders")
    op.drop_table("sent_reminders")
