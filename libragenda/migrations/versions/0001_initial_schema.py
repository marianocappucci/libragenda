"""Create core LibraGenda scheduling tables."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("resources", sa.Column("id", sa.String(100), primary_key=True), sa.Column("name", sa.String(200), nullable=False), sa.Column("branch_id", sa.String(100)), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("services", sa.Column("id", sa.String(100), primary_key=True), sa.Column("name", sa.String(200), nullable=False), sa.Column("duration_seconds", sa.Integer(), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("availability", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("resource_id", sa.String(100), sa.ForeignKey("resources.id"), nullable=False), sa.Column("weekday", sa.Integer(), nullable=False), sa.Column("starts_at", sa.Time(), nullable=False), sa.Column("ends_at", sa.Time(), nullable=False))
    op.create_table("appointments", sa.Column("id", sa.String(100), primary_key=True), sa.Column("resource_id", sa.String(100), sa.ForeignKey("resources.id"), nullable=False), sa.Column("service_id", sa.String(100), sa.ForeignKey("services.id"), nullable=False), sa.Column("client_id", sa.String(100), nullable=False), sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False), sa.Column("duration_seconds", sa.Integer(), nullable=False), sa.Column("status", sa.String(30), nullable=False))

def downgrade():
    op.drop_table("appointments")
    op.drop_table("availability")
    op.drop_table("services")
    op.drop_table("resources")
