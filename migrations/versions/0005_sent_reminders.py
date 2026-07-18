"""Add sent_reminders ledger to track reminders already delivered."""
from alembic import op
import sqlalchemy as sa

revision = "0005_sent_reminders"
down_revision = "0004_appointment_series"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "sent_reminders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("appointment_id", sa.String(100), sa.ForeignKey("appointments.id"), nullable=False),
        sa.Column("policy_id", sa.String(100), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sent_reminders_appointment_id", "sent_reminders", ["appointment_id"])
    op.create_unique_constraint(
        "uq_sent_reminders_appointment_policy", "sent_reminders", ["appointment_id", "policy_id"]
    )

def downgrade():
    op.drop_constraint("uq_sent_reminders_appointment_policy", "sent_reminders", type_="unique")
    op.drop_index("ix_sent_reminders_appointment_id", table_name="sent_reminders")
    op.drop_table("sent_reminders")
