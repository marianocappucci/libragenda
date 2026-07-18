"""Add branch timezone, holidays and appointment branch scoping."""
from alembic import op
import sqlalchemy as sa

revision = "0003_timezone_holidays"
down_revision = "0002_entities"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("branches", sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"))
    op.create_table("holidays", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("branch_id", sa.String(100), sa.ForeignKey("branches.id"), nullable=False), sa.Column("day", sa.Date(), nullable=False), sa.Column("name", sa.String(200), nullable=False))
    op.add_column("appointments", sa.Column("branch_id", sa.String(100), nullable=True))
    op.create_foreign_key("fk_appointments_branch", "appointments", "branches", ["branch_id"], ["id"])

def downgrade():
    op.drop_constraint("fk_appointments_branch", "appointments", type_="foreignkey")
    op.drop_column("appointments", "branch_id")
    op.drop_table("holidays")
    op.drop_column("branches", "timezone")
