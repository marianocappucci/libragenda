"""Crear el esquema de LibraGenda de a un proceso por vez (ADR-015).

Con `uvicorn --workers N` cada worker corre el arranque del producto, y MedLibra y Gestiolibra crean sus tablas con
`Base.metadata.create_all(get_engine())`. `create_all` primero **mira** qué tablas faltan y después las **crea**, y en
PostgreSQL esas dos cosas no son atómicas: dos procesos que arrancan juntos sobre una base sin las tablas contestan los
dos «falta» y chocan en el catálogo (`duplicate key … pg_type_typname_nsp_index` / `relation "…" already exists`). En una
instancia migrada con `libragenda-migrar` las tablas están y `create_all` no hace nada, así que el defecto aparece sólo
con una tabla que la cadena no trae: justo cuando nadie lo está mirando.

`crear_esquema(engine)` es la costura: toma un candado **bloqueante** antes de mirar y lo suelta al terminar, así que el
segundo proceso espera al primero y, cuando entra, ya encuentra las tablas. Mismo criterio que
`libracore.candados.esperar_candado_de_transaccion` y `libracommerce.db.candado.serializar_esquema` (ADR-053 y ADR-062
de esos motores), **sin depender de libracore**: LibraGenda no lo tiene como dependencia.

| Motor | Candado | Dura |
|---|---|---|
| PostgreSQL | `pg_try_advisory_xact_lock` en la transacción del DDL, reintentado cada 0,1 s | hasta el `commit` de esa transacción |
| SQLite (archivo) | `BEGIN IMMEDIATE`: el candado de escritura de la base | hasta el `commit` |
| SQLite `:memory:` | nada: una base en memoria no se comparte entre procesos | |

La clave de un candado asesor de PostgreSQL es un entero de 64 bits; se deriva del nombre con SHA-256 (56 bits), igual que
en los motores, y no con `hashtext()`. Dos nombres distintos que choquen serían un falso «ocupado», nunca un falso «libre».

🔴 **El candado no reemplaza a las migraciones**: `libragenda-migrar upgrade` sigue siendo el camino del deploy (antes de
uvicorn, un solo proceso). Esto cubre el `create_all` que los productos dejaron en el arranque.
"""
from __future__ import annotations

import hashlib
import time

from sqlalchemy import Engine, MetaData, text
from sqlalchemy.exc import OperationalError

#: Cuánto espera el segundo proceso al primero. Crear el esquema tarda segundos; si pasaron dos minutos, el que tiene el
#: candado está colgado y es mejor que el arranque lo diga a quedarse esperando en silencio. Igual que el motor.
ESPERA_AL_ARRANCAR = 120.0

#: Cada cuánto reintenta mientras espera.
_PASO = 0.1

#: El nombre del candado. Uno solo para todo el DDL de LibraGenda.
CANDADO_DEL_ESQUEMA = "libragenda.esquema"

_PREFIJO = "libragenda-candado:"


def _clave(nombre: str) -> int:
    """El entero de 64 bits (positivo, 56 bits usados) que identifica a `nombre` en los candados asesores."""
    return int.from_bytes(hashlib.sha256((_PREFIJO + nombre).encode()).digest()[:7], "big")


def _esperar(intentar, espera: float, que: str) -> None:
    limite = time.monotonic() + espera
    while not intentar():
        if time.monotonic() >= limite:
            raise TimeoutError(
                f"{que}: no se pudo tomar el candado del esquema en {espera:.0f} s: otro proceso lo tiene y no termina."
            )
        time.sleep(_PASO)


def serializar_esquema(conexion, *, espera: float = ESPERA_AL_ARRANCAR) -> bool:
    """Toma el candado del esquema en `conexion` (una `Connection` de SQLAlchemy dentro de su transacción).

    Devuelve `True` si lo tomó y `False` si no hacía falta (SQLite en memoria). `TimeoutError` si pasan `espera` segundos.

    🔴 **Va lo primero de la transacción**: un candado tomado a mitad de camino no protege lo que ya se tocó. Y se suelta
    con el `commit` o el `rollback` de la transacción, no antes.
    """
    dialecto = conexion.dialect.name
    if dialecto == "postgresql":
        clave = _clave(CANDADO_DEL_ESQUEMA)
        _esperar(
            lambda: bool(conexion.execute(text("SELECT pg_try_advisory_xact_lock(:clave)"), {"clave": clave}).scalar()),
            espera, "PostgreSQL",
        )
        return True
    if dialecto == "sqlite":
        if conexion.engine.url.database in (None, "", ":memory:"):
            return False

        def inmediato() -> bool:
            try:
                conexion.exec_driver_sql("BEGIN IMMEDIATE")
            except OperationalError as e:   # `database is locked`: otro proceso escribe; cualquier otro error sube
                if "locked" not in str(e).lower() and "busy" not in str(e).lower():
                    raise
                return False
            return True

        _esperar(inmediato, espera, "SQLite")
        return True
    return False


def crear_esquema(engine: Engine, metadata: MetaData | None = None, *, espera: float = ESPERA_AL_ARRANCAR) -> None:
    """`metadata.create_all(engine)`, de a un proceso por vez. Sin `metadata`, las tablas de LibraGenda (`Base.metadata`,
    a la que los productos suman las suyas).

    Todo ocurre en UNA transacción: el candado primero, después lo que `create_all` mira y crea, y el `commit` que lo
    suelta. En PostgreSQL el DDL es transaccional, así que un arranque que falla a la mitad no deja tablas sueltas.
    """
    if metadata is None:
        from .sqlalchemy_repository import Base

        metadata = Base.metadata
    with engine.begin() as conexion:
        serializar_esquema(conexion, espera=espera)
        metadata.create_all(conexion)
