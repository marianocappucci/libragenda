"""Add deposits table (one deposit per appointment)."""
from alembic import op
import sqlalchemy as sa

revision = "0006_deposits"
down_revision = "0005_sent_reminders"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "deposits",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("appointment_id", sa.String(100), sa.ForeignKey("appointments.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
    )
    op.create_index("ix_deposits_appointment_id", "deposits", ["appointment_id"], unique=True)
    op.create_index("ix_deposits_status", "deposits", ["status"])

def downgrade():
    op.drop_index("ix_deposits_status", table_name="deposits")
    op.drop_index("ix_deposits_appointment_id", table_name="deposits")
    op.drop_table("deposits")
