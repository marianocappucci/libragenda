"""Add branches, clients, blocks and availability exceptions."""
from alembic import op
import sqlalchemy as sa

revision = "0002_entities"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("branches", sa.Column("id", sa.String(100), primary_key=True), sa.Column("name", sa.String(200), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("clients", sa.Column("id", sa.String(100), primary_key=True), sa.Column("name", sa.String(200), nullable=False), sa.Column("phone", sa.String(50)), sa.Column("email", sa.String(254)), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("time_blocks", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("resource_id", sa.String(100), sa.ForeignKey("resources.id"), nullable=False), sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False), sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False), sa.Column("reason", sa.Text(), nullable=False, server_default=""))
    op.create_table("availability_exceptions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("resource_id", sa.String(100), sa.ForeignKey("resources.id"), nullable=False), sa.Column("day", sa.Date(), nullable=False), sa.Column("starts_at", sa.Time(), nullable=False), sa.Column("ends_at", sa.Time(), nullable=False), sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_foreign_key("fk_resources_branch", "resources", "branches", ["branch_id"], ["id"])
    op.create_foreign_key("fk_appointments_client", "appointments", "clients", ["client_id"], ["id"])

def downgrade():
    op.drop_constraint("fk_appointments_client", "appointments", type_="foreignkey")
    op.drop_constraint("fk_resources_branch", "resources", type_="foreignkey")
    op.drop_table("availability_exceptions")
    op.drop_table("time_blocks")
    op.drop_table("clients")
    op.drop_table("branches")
