"""Aplicar las migraciones de LibraGenda desde el paquete instalado.

Hasta la `v0.10.0` las migraciones **no viajaban en el wheel**: vivían en
`migrations/` en la raíz del repo, fuera de `packages = ["libragenda"]`. La
única forma de aplicarlas era `scripts/run_migrations.sh`, que **clona el repo**
en el tag pineado, arma un venv y corre alembic.

🔴 **Eso las dejaba fuera del alcance de un contenedor.** Un consumidor
(Gestiolibra, MedLibra) instala LibraGenda con pip dentro de su imagen y ahí no
hay repo que clonar, ni git, ni red saliente garantizada. Resultado medido el
2026-08-24: **ninguna instancia de esos dos productos tenía las migraciones
aplicadas** —ni la tabla `alembic_version`— y su esquema lo creaba
`Base.metadata.create_all()` en el arranque. El CI las corría clonando, así que
el verde no decía nada sobre las instancias.

Ahora `migrations/` vive **adentro del paquete** y esto es lo que las corre:

    libragenda-migrar                 # consola, desde cualquier lado
    python -m libragenda.migrar       # equivalente
    from libragenda.migrar import upgrade; upgrade()   # desde código

La URL sale de `DATABASE_URL` —igual que en `env.py`, que ya la leía— o del
argumento explícito.

🔴 **La tabla de versión es `alembic_version_libragenda`** (ADR-017), no
`alembic_version`. Ese nombre pelado es el de la cadena de LibraCore, y con una
sola base por producto las dos cadenas migran en la misma: dos cadenas sobre una
tabla de versión se pisan la revisión. Una base de antes tiene la revisión de
LibraGenda en `alembic_version`; `adoptar_la_tabla_de_version_vieja` la renombra
sola, adentro de la transacción de la migración.

🔑 **`script_location` se resuelve desde `__file__`, no desde el cwd.** Es la
diferencia entre andar en el repo y andar en `/usr/local/lib/python3.12/
site-packages`: un `alembic.ini` con ruta relativa sólo funciona parado en la
raíz del repo, que es justo donde el contenedor no está.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

#: El directorio de migraciones **dentro del paquete**. Es lo que hace que esto
#: funcione desde una instalación de pip y no sólo desde el repo.
DIRECTORIO = Path(__file__).parent / "migrations"


#: 🔴 **La tabla de versión es PROPIA, no `alembic_version`** (ADR-017). Es la que lee `migrations/env.py`.
TABLA_DE_VERSION = "alembic_version_libragenda"

#: El nombre que tenía hasta la v0.13.0, y que sigue teniendo cada base que no se migró desde entonces.
TABLA_DE_VERSION_VIEJA = "alembic_version"


class SinURL(RuntimeError):
    """No hay `DATABASE_URL` ni URL explícita: no hay contra qué migrar."""


def normalizar_url(url: str) -> str:
    """`postgresql://` → `postgresql+psycopg://`.

    🔴 **Sin esto el caso más obvio falla con un error que no nombra la causa.**
    SQLAlchemy resuelve `postgresql://` a **psycopg2**, y este paquete declara
    `psycopg[binary]` —psycopg **3**— y nada más. El resultado, medido:
    `ModuleNotFoundError: No module named 'psycopg2'` en medio de un deploy, que
    manda a instalar el driver equivocado.

    Sólo toca el prefijo pelado: `postgresql+psycopg2://` explícito se respeta,
    por si alguien lo instaló a propósito.

    🔑 **La llaman los DOS lados, y hace falta que sea así.** `migrations/env.py`
    lee `DATABASE_URL` del entorno por su cuenta y **no mira** la opción que
    `configuracion()` pone en el `Config` — normalizar en un solo lado deja el
    camino real sin arreglar. Se descubrió corriendo el end-to-end: los tests
    unitarios pasaban porque afirmaban sobre el valor que este módulo setea, no
    sobre el que termina usando alembic.
    """
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def adoptar_la_tabla_de_version_vieja(connection, revisiones_propias: set[str]) -> bool:
    """Renombra `alembic_version` a `alembic_version_libragenda` si ahí está la cadena de LibraGenda.

    **Autorrenombre**: una base de antes tiene la revisión de LibraGenda en `alembic_version`. Con la tabla nueva y la
    vieja, Alembic no encontraría revisión, creería la base sin migrar y arrancaría en la `0001` contra tablas que ya
    existen: el deploy abortaría. Por eso el renombre es parte de la migración y no un paso manual del operador.

    Se llama **adentro de `begin_transaction()`** (ver `migrations/env.py`): el renombre y las migraciones viajan en la
    misma transacción y, si algo falla, la base queda como estaba (en PostgreSQL el DDL es transaccional).

    Sólo renombra si hace falta y si la tabla es de acá. No toca nada cuando:

    - ya existe `alembic_version_libragenda`: no hay nada que adoptar;
    - no existe `alembic_version`: base nueva, la crea Alembic;
    - `alembic_version` está vacía: no se sabe de quién es;
    - `alembic_version` guarda alguna revisión que NO es de esta cadena. Es la de LibraCore (en una base unida, o en una
      donde los dos motores comparten tabla): esa tabla es del motor y no se toca.

    Devuelve si renombró.
    """
    tablas = set(inspect(connection).get_table_names())
    if TABLA_DE_VERSION in tablas or TABLA_DE_VERSION_VIEJA not in tablas:
        return False
    revisiones = set(connection.execute(text(f"SELECT version_num FROM {TABLA_DE_VERSION_VIEJA}")).scalars())
    if not revisiones or not revisiones <= revisiones_propias:
        return False
    connection.execute(text(f"ALTER TABLE {TABLA_DE_VERSION_VIEJA} RENAME TO {TABLA_DE_VERSION}"))
    # Un RENAME de tabla **no renombra sus restricciones**: la clave primaria seguiría llamándose `alembic_version_pkc`,
    # el nombre de cualquier cadena sin sufijo, y PostgreSQL no admite dos restricciones con el mismo nombre en un
    # schema (su índice es un objeto del schema). Con eso la cadena del motor moriría al crear SU `alembic_version` en
    # la misma base (*relation "alembic_version_pkc" already exists*, medido en LibraCargo el 2026-10-05). SQLite no
    # tiene `RENAME CONSTRAINT` y no necesita el cambio: sus nombres de restricción no son globales.
    if connection.dialect.name == "postgresql":
        clave = inspect(connection).get_pk_constraint(TABLA_DE_VERSION).get("name")
        if clave and clave != f"{TABLA_DE_VERSION}_pkc":
            connection.execute(
                text(f'ALTER TABLE {TABLA_DE_VERSION} RENAME CONSTRAINT "{clave}" TO {TABLA_DE_VERSION}_pkc')
            )
    return True


def configuracion(database_url: str | None = None) -> Config:
    """El `Config` de Alembic apuntado al paquete instalado.

    No lee `alembic.ini`: ese archivo es del repo y no viaja en el wheel. Se
    arma en memoria con las dos opciones que importan.
    """
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise SinURL(
            "Falta DATABASE_URL (o el argumento `database_url`): no hay base "
            "contra la cual aplicar las migraciones de LibraGenda."
        )
    cfg = Config()
    cfg.set_main_option("script_location", str(DIRECTORIO))
    normalizada = normalizar_url(url)
    cfg.set_main_option("sqlalchemy.url", normalizada)
    # 🔴 **La que manda de verdad.** `env.py` prefiere `DATABASE_URL` del
    # entorno por sobre `sqlalchemy.url`, así que sin esta opción propia el
    # argumento `database_url` **se ignoraba en silencio**: con la variable
    # puesta, `upgrade("…/otra_base")` migraba la del entorno y devolvía éxito.
    cfg.set_main_option("libragenda.url", normalizada)
    return cfg


def upgrade(database_url: str | None = None, revision: str = "head") -> None:
    """Aplica las migraciones. Es lo que corre el deploy de un consumidor."""
    command.upgrade(configuracion(database_url), revision)


def stamp(database_url: str | None = None, revision: str = "head") -> None:
    """Marca la base en una revisión **sin ejecutar** las migraciones.

    🔴 Es para el caso de las bases que ya existen con el esquema puesto por
    `create_all()` y sin `alembic_version`. Estampar declara «esta base está en
    esta revisión»: si no lo está, la próxima migración corre sobre un esquema
    que no es el que espera. **Verificar antes de usarlo.**
    """
    command.stamp(configuracion(database_url), revision)


def current(database_url: str | None = None) -> None:
    command.current(configuracion(database_url))


def heads(database_url: str | None = None) -> None:
    command.heads(configuracion(database_url))


def main(argv: list[str] | None = None) -> int:
    """CLI: `libragenda-migrar [upgrade|stamp|current|heads] [revision]`."""
    argv = list(sys.argv[1:] if argv is None else argv)
    accion = argv[0] if argv else "upgrade"
    acciones = {"upgrade": upgrade, "stamp": stamp, "current": current, "heads": heads}
    if accion in ("-h", "--help") or accion not in acciones:
        print(main.__doc__)
        print(f"  migraciones en: {DIRECTORIO}")
        # 🔑 Código 0 si la pidieron, 2 si el comando no existe: un typo no
        # puede leerse como éxito desde un pipeline.
        return 0 if accion in ("-h", "--help") else 2

    fn = acciones[accion]
    try:
        if accion in ("upgrade", "stamp") and len(argv) > 1:
            fn(revision=argv[1])
        else:
            fn()
    except SinURL as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
