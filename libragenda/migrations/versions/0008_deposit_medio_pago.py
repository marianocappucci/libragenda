"""Add nullable medio_pago column to deposits."""
from alembic import op
import sqlalchemy as sa

revision = "0008_deposit_medio_pago"
down_revision = "0007_appointment_reason"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("deposits", sa.Column("medio_pago", sa.String(length=50), nullable=True))

def downgrade():
    with op.batch_alter_table("deposits") as batch_op:
        batch_op.drop_column("medio_pago")
