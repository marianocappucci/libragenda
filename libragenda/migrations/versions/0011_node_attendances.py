"""Attending an appointment at an offline node: the node's own rows and the central's ledger (ADR-019).

Todo aditivo: dos tablas nuevas, sin tocar ninguna existente. Una base que no usa nodos las tiene vacías y no cambia en
nada.

- `agenda_node_attendances`: la fila propia del nodo. El turno es, en el nodo, una fila del espejo que no se puede
  escribir; atenderlo deja esta fila (y una operación `turno.atendido` en el outbox del producto). Sin clave foránea a
  `appointments` a propósito: el espejo reapunta y borra filas de esa tabla.
- `agenda_applied_attendances`: lo que el central ya aplicó. La clave (`atencion_id`) es lo que hace idempotente al
  aplicador, y las filas con `resultado = 'a_revisar'` sin `reviewed_at` son la lista de turnos a revisar. Tampoco tiene
  clave foránea: una atención de un turno que ya no está tiene que quedar anotada igual.

Los nombres llevan el prefijo `agenda_` (convención del ADR-018) y no chocan con los de LibraCore ni LibraAuth.

El nombre de la revisión no puede pasar de 32 caracteres (`version_num` es un varchar(32) en PostgreSQL).
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_node_attendances"
down_revision = "0010_agenda_clients"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agenda_node_attendances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("appointment_id", sa.String(100), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(200), nullable=True),
        sa.Column("seen", sa.JSON(), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("appointment_id", "orden", name="uq_agenda_node_attendances_orden"),
    )
    op.create_index(
        "ix_agenda_node_attendances_appointment_id", "agenda_node_attendances", ["appointment_id"]
    )
    op.create_table(
        "agenda_applied_attendances",
        sa.Column("atencion_id", sa.String(36), primary_key=True),
        sa.Column("node_id", sa.String(100), nullable=False),
        sa.Column("appointment_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(200), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("resultado", sa.String(20), nullable=False),
        sa.Column("motivo", sa.String(30), nullable=True),
        sa.Column("detalle", sa.Text(), nullable=True),
        sa.Column("status_before", sa.String(30), nullable=True),
        sa.Column("status_after", sa.String(30), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(200), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_agenda_applied_attendances_appointment_id", "agenda_applied_attendances", ["appointment_id"]
    )
    op.create_index("ix_agenda_applied_attendances_resultado", "agenda_applied_attendances", ["resultado"])


def downgrade():
    # Se pierden las atenciones que el nodo todavía no subió y el registro de lo aplicado: el downgrade es para una
    # base de prueba, no para un nodo con operaciones pendientes en su outbox.
    op.drop_index("ix_agenda_applied_attendances_resultado", table_name="agenda_applied_attendances")
    op.drop_index("ix_agenda_applied_attendances_appointment_id", table_name="agenda_applied_attendances")
    op.drop_table("agenda_applied_attendances")
    op.drop_index("ix_agenda_node_attendances_appointment_id", table_name="agenda_node_attendances")
    op.drop_table("agenda_node_attendances")
