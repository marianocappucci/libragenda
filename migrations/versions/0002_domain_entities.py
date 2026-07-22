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
    # batch_alter_table: SQLite doesn't support ALTER-ing in a constraint on
    # an existing table (only a copy-and-move rebuild does) -- batch mode
    # picks the right strategy per dialect, plain ALTER on Postgres.
    with op.batch_alter_table("resources") as batch_op:
        batch_op.create_foreign_key("fk_resources_branch", "branches", ["branch_id"], ["id"])
    with op.batch_alter_table("appointments") as batch_op:
        batch_op.create_foreign_key("fk_appointments_client", "clients", ["client_id"], ["id"])

def downgrade():
    with op.batch_alter_table("appointments") as batch_op:
        batch_op.drop_constraint("fk_appointments_client", type_="foreignkey")
    with op.batch_alter_table("resources") as batch_op:
        batch_op.drop_constraint("fk_resources_branch", type_="foreignkey")
    op.drop_table("availability_exceptions")
    op.drop_table("time_blocks")
    op.drop_table("clients")
    op.drop_table("branches")
