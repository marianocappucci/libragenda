"""Add appointments.series_id to group recurring occurrences."""
from alembic import op
import sqlalchemy as sa

revision = "0004_appointment_series"
down_revision = "0003_timezone_holidays"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("appointments", sa.Column("series_id", sa.String(100), nullable=True))
    op.create_index("ix_appointments_series_id", "appointments", ["series_id"])

def downgrade():
    op.drop_index("ix_appointments_series_id", table_name="appointments")
    op.drop_column("appointments", "series_id")
