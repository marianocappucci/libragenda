"""Ninguna tabla de LibraGenda puede llamarse como una de LibraCore o de LibraAuth (ADR-018).

Con **una sola base por producto** (decisión del humano del 2026-10-22), las tablas del motor de agenda viven en la misma
base que las de LibraCore y las de LibraAuth. `libracore-unir-bases` corta con cualquier nombre repetido, y una base
nueva no puede crear la segunda tabla con el nombre de la primera. Pasó con `clients`: LibraCore tiene la suya (id
entero, nueve claves foráneas que la apuntan) y LibraGenda la suya (id de texto); por eso GestioLibra y MedLibra
tuvieron dos bases hasta ahora, y por eso la de LibraGenda pasó a `agenda_clients`.

🔑 **LibraGenda no depende de LibraCore** (ver `libragenda/esquema.py`), así que el CI no puede importarlo. La lista de
abajo es una **copia**, tomada de la cadena de migraciones de `libracore` y `libraauth` en `origin/develop` el
2026-10-25 (v1.192.1 de LibraCore). Para que no envejezca en silencio hay un segundo test que, **si el entorno tiene
`libracore` instalado**, corre su cadena sobre SQLite y compara contra la copia: si el motor suma una tabla, ese test se
pone rojo en la máquina de quien lo tenga y avisa que hay que actualizar la lista.

No cubre `libracommerce`: LibraGenda comparte con él `branches`, y ningún producto usa los dos motores en una base (los
productos de agenda no usan `libracommerce`, y LibraDesk, que sí, no usa las tablas de LibraGenda). Está dicho en el
ADR-018. Si algún día se juntan, hay que renombrar una de las dos.
"""

import importlib.util

import pytest
from sqlalchemy import create_engine, inspect

from libragenda import migrar
from libragenda.sqlalchemy_repository import Base

#: Las tablas de `libracore`: las de su cadena de migraciones y las que crea en tiempo de ejecución.
TABLAS_DE_LIBRACORE = frozenset({
    "arca_config", "arca_credenciales_servicio", "auth_log", "caja_movimientos", "cajas", "categorias_egreso",
    "categorias_producto", "cc_asientos", "cc_debitos", "cc_pagos", "cierres_diarios", "cierres_diarios_medios",
    "cierres_diarios_turnos", "clients", "cola_arca", "comprobantes_pendientes", "cuentas_tesoreria", "depositos",
    "egresos", "egresos_pagos", "envios_email", "facturacion_alias", "facturas", "lista_precio_items",
    "listas_precio", "modulos", "movimientos_stock", "movimientos_tesoreria", "mp_movimientos", "mp_pagos",
    "presupuestos", "productos", "proveedores", "recibos", "reintegros_pendientes", "remitos", "turnos_caja",
    "usuarios", "ventas", "ventas_pagos",
    # Las que crea en tiempo de ejecución, no la cadena.
    "procesos_barrera", "procesos_notas", "procesos_semilla", "libracore_union_bases",
})

#: Las de `libraauth` (viven en la base del dominio o en la del core, según el producto).
TABLAS_DE_LIBRAAUTH = frozenset({
    "aceptaciones_terminos", "actividad_log", "auth_log", "demo_codigos", "libraauth_captcha_usados",
    "password_reset_tokens", "secretos_instancia", "smtp_settings", "usuarios",
})

#: Las tablas de versión de Alembic: la de LibraCore es `alembic_version` a secas.
TABLAS_DE_VERSION_AJENAS = frozenset({"alembic_version", "alembic_version_libraauth", "alembic_version_libracommerce"})

AJENAS = TABLAS_DE_LIBRACORE | TABLAS_DE_LIBRAAUTH | TABLAS_DE_VERSION_AJENAS


def _tablas_de_la_cadena(tmp_path) -> set[str]:
    """Las tablas que crea `libragenda-migrar upgrade` sobre una base vacía, la de versión incluida."""
    url = f"sqlite:///{tmp_path / 'agenda.db'}"
    migrar.upgrade(url)
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_los_modelos_no_chocan_con_las_tablas_de_libracore_ni_de_libraauth():
    propias = set(Base.metadata.tables)
    assert len(propias) >= 14, "la metadata de LibraGenda quedó vacía: el test pasaría en vacío"
    assert propias & AJENAS == set(), (
        f"Estas tablas de LibraGenda se llaman como una de LibraCore o de LibraAuth: {sorted(propias & AJENAS)}. "
        "Con una sola base por producto no pueden convivir: renombrá la de LibraGenda (prefijo `agenda_`, como "
        "`agenda_clients`) con una migración, y anotalo en el ADR-018."
    )


def test_la_cadena_de_migraciones_no_choca_con_las_tablas_de_libracore_ni_de_libraauth(tmp_path):
    """Los modelos y la cadena pueden desviarse: lo que importa en una base real es lo que crean las migraciones."""
    creadas = _tablas_de_la_cadena(tmp_path)
    assert len(creadas) >= 14
    assert creadas & AJENAS == set(), f"La cadena crea tablas que chocan con las del motor: {sorted(creadas & AJENAS)}"
    assert migrar.TABLA_DE_VERSION in creadas


def test_la_cadena_y_los_modelos_crean_las_mismas_tablas(tmp_path):
    """Sin esto, el test anterior podría estar mirando un conjunto distinto del que usa la aplicación."""
    assert _tablas_de_la_cadena(tmp_path) - {migrar.TABLA_DE_VERSION} == set(Base.metadata.tables)


def test_la_tabla_de_version_es_propia():
    assert migrar.TABLA_DE_VERSION == "alembic_version_libragenda"
    assert migrar.TABLA_DE_VERSION not in AJENAS


def test_la_lista_de_libracore_sigue_al_dia(tmp_path):
    """Si `libracore` está instalado, compara la copia de arriba con su cadena real (se saltea en el CI)."""
    if importlib.util.find_spec("libracore") is None:
        pytest.skip("libracore no está instalado en este entorno: la copia no se puede verificar")
    from libracore import migrar as migrar_libracore

    destino = tmp_path / "core.db"
    migrar_libracore.upgrade(str(destino))
    engine = create_engine(f"sqlite:///{destino}")
    try:
        reales = set(inspect(engine).get_table_names()) - TABLAS_DE_VERSION_AJENAS - {"sqlite_sequence"}
    finally:
        engine.dispose()

    assert reales, "la cadena de LibraCore no creó nada: el test pasaría en vacío"
    assert reales <= TABLAS_DE_LIBRACORE, (
        f"LibraCore tiene tablas que la copia de este test no conoce: {sorted(reales - TABLAS_DE_LIBRACORE)}. "
        "Sumalas a TABLAS_DE_LIBRACORE y comprobá que ninguna se llame como una de LibraGenda."
    )
    propias = set(Base.metadata.tables)
    assert propias & reales == set()

