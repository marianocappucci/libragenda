"""Add nullable reason column to appointments (cancel/reschedule note)."""
from alembic import op
import sqlalchemy as sa

revision = "0007_appointment_reason"
down_revision = "0006_deposits"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("appointments", sa.Column("reason", sa.Text(), nullable=True))

def downgrade():
    op.drop_column("appointments", "reason")
