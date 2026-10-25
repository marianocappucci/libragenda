"""Rename clients to agenda_clients: `clients` is also a LibraCore table (ADR-018).

LibraCore declara su propia `clients` (id entero, 9 claves foráneas que la apuntan) y LibraGenda la suya (id de texto).
Con dos bases por producto no se veían; con una sola (decisión del humano del 2026-10-22) tienen que convivir, y
`libracore-unir-bases` corta con cualquier nombre repetido. Se renombra la de LibraGenda: la del motor la usan todos los
productos.

Es un RENAME y nada más: no copia ni borra una sola fila.

- Las claves foráneas que apuntan a la tabla (la de `appointments` y las de los productos: `client_billing`, `patients`,
  `walkins`) **siguen a la tabla** en PostgreSQL y en SQLite >= 3.26; no hay que tocarlas.
- Lo que un RENAME de tabla NO renombra es su clave primaria: seguiría llamándose `clients_pkey` aunque la tabla ya no
  sea `clients`. No es un choque (medido: PostgreSQL le pone `clients_pkey1` a la clave sin nombre de la `clients` de
  LibraCore), pero deja dos claves con el nombre cruzado, y quien cree la suya con un nombre explícito sí choca. Se
  renombra a `agenda_clients_pkey` para que cada objeto lleve el nombre de su tabla.
- La tabla no tiene secuencia (el id es texto) ni más índices.

El nombre de la revisión no puede pasar de 32 caracteres (`version_num` es un varchar(32) en PostgreSQL).
"""
from alembic import context, op
from sqlalchemy import inspect

revision = "0010_agenda_clients"
down_revision = "0009_occupancy_and_history"
branch_labels = None
depends_on = None


def _renombrar(origen: str, destino: str, consejo: str) -> None:
    postgres = context.get_context().dialect.name == "postgresql"
    if context.is_offline_mode():
        # `--sql`: no hay base que mirar. Se genera el DDL con el nombre que PostgreSQL le da a una clave sin nombre.
        clave = f"{origen}_pkey" if postgres else None
    else:
        conexion = op.get_bind()
        if destino in set(inspect(conexion).get_table_names()):
            raise RuntimeError(f"No se puede renombrar {origen!r} a {destino!r}: {destino!r} ya existe. {consejo}")
        clave = inspect(conexion).get_pk_constraint(origen).get("name") if postgres else None
    op.rename_table(origen, destino)
    if clave and clave != f"{destino}_pkey":
        op.execute(f'ALTER TABLE {destino} RENAME CONSTRAINT "{clave}" TO {destino}_pkey')


def upgrade():
    # Un arranque con el código nuevo y la cadena sin correr (`create_all` crea las tablas que faltan) deja un
    # `agenda_clients` vacío al lado de `clients`. Renombrar encima no se puede; borrar a ciegas, tampoco.
    _renombrar(
        "clients", "agenda_clients",
        "Suele pasar si la aplicación arrancó con el código nuevo (`create_all`) antes de correr `libragenda-migrar "
        "upgrade`. Revisá si `agenda_clients` tiene filas: si está vacía, borrala y reintentá; si no, resolvelo a mano.",
    )


def downgrade():
    # En una base ya unida con LibraCore, `clients` es la del motor (id entero): no se puede volver atrás sin pisarla.
    _renombrar(
        "agenda_clients", "clients",
        "Si la base ya se unió con la de LibraCore, `clients` es la del motor y el downgrade no se puede hacer: "
        "primero hay que revertir la unión (`libracore-unir-bases revertir`).",
    )
