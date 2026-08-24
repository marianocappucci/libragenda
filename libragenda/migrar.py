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

#: El directorio de migraciones **dentro del paquete**. Es lo que hace que esto
#: funcione desde una instalación de pip y no sólo desde el repo.
DIRECTORIO = Path(__file__).parent / "migrations"


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
