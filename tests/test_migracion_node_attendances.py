"""La migración `0011_node_attendances`: las dos tablas de atender en un nodo (ADR-019).

Aditiva y con downgrade. Corre en SQLite y, con `DATABASE_URL`, en PostgreSQL. Parte de una base como la dejaba la
v0.14.0 (cadena en la `0010`, con datos) y verifica que: sube sin tocar nada de lo que había, las tablas son las del
modelo, baja dejando la base exactamente como estaba, y vuelve a subir.
"""

import os
import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from libragenda import migrar
from libragenda.sqlalchemy_repository import AppliedAttendanceRow, Base, NodeAttendanceRow

ANTES = "0010_agenda_clients"
CABEZA = "0011_node_attendances"
TABLAS_NUEVAS = {"agenda_node_attendances", "agenda_applied_attendances"}

DATABASE_URL = os.environ.get("DATABASE_URL")


def _url_postgres(base: str) -> str:
    return make_url(DATABASE_URL).set(database=base).render_as_string(hide_password=False)


@pytest.fixture(params=["sqlite", "postgresql"])
def url(request, tmp_path):
    if request.param == "sqlite":
        yield f"sqlite:///{tmp_path / 'agenda.db'}"
        return
    if not DATABASE_URL or not make_url(DATABASE_URL).drivername.startswith("postgresql"):
        pytest.skip("sin DATABASE_URL de PostgreSQL")
    base = f"libragenda_pr8m_{uuid.uuid4().hex[:12]}"
    admin = create_engine(_url_postgres("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{base}"'))
    try:
        yield _url_postgres(base)
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{base}" WITH (FORCE)'))
        admin.dispose()


def _consulta(url: str, sentencia: str) -> list:
    engine = create_engine(url)
    try:
        with engine.connect() as c:
            return list(c.execute(text(sentencia)).all())
    finally:
        engine.dispose()


def _inspeccion(url: str, tabla: str) -> dict:
    engine = create_engine(url)
    try:
        insp = inspect(engine)
        return {
            "columnas": {c["name"]: c for c in insp.get_columns(tabla)},
            "indices": {i["name"]: i for i in insp.get_indexes(tabla)},
            "unicas": {u["name"]: u for u in insp.get_unique_constraints(tabla)},
            "pk": insp.get_pk_constraint(tabla)["constrained_columns"],
            "fks": insp.get_foreign_keys(tabla),
        }
    finally:
        engine.dispose()


def _tablas(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _base_v014(url: str) -> None:
    """Una base de la v0.14.0, con un turno."""
    migrar.upgrade(url, ANTES)
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO resources (id, name) VALUES ('r1', 'Sillón')"))
        c.execute(text("INSERT INTO services (id, name, duration_seconds) VALUES ('s1', 'Corte', 1800)"))
        c.execute(text("INSERT INTO agenda_clients (id, name) VALUES ('c1', 'Cliente de prueba')"))
        c.execute(text(
            "INSERT INTO appointments (id, resource_id, service_id, client_id, starts_at, duration_seconds, status) "
            "VALUES ('a1', 'r1', 's1', 'c1', '2026-11-02 12:00:00+00', 1800, 'confirmed')"
        ))
    engine.dispose()
    assert not TABLAS_NUEVAS & _tablas(url)


def test_sube_sin_tocar_lo_que_habia(url):
    _base_v014(url)
    antes = _consulta(url, "SELECT id, status, client_id FROM appointments")

    migrar.upgrade(url)

    assert TABLAS_NUEVAS <= _tablas(url)
    assert _consulta(url, f"SELECT version_num FROM {migrar.TABLA_DE_VERSION}") == [(CABEZA,)]
    assert _consulta(url, "SELECT id, status, client_id FROM appointments") == antes
    assert _consulta(url, "SELECT count(*) FROM agenda_node_attendances") == [(0,)]
    assert _consulta(url, "SELECT count(*) FROM agenda_applied_attendances") == [(0,)]


@pytest.mark.parametrize(("tabla", "modelo"), [
    ("agenda_node_attendances", NodeAttendanceRow),
    ("agenda_applied_attendances", AppliedAttendanceRow),
])
def test_la_migracion_y_el_modelo_dicen_lo_mismo(url, tabla, modelo):
    """Lo que `create_all` crearía y lo que crea la cadena: mismas columnas, mismo null, misma clave, mismos índices."""
    migrar.upgrade(url)
    real = _inspeccion(url, tabla)

    esperado = modelo.__table__
    assert set(real["columnas"]) == {c.name for c in esperado.columns}
    for columna in esperado.columns:
        assert real["columnas"][columna.name]["nullable"] == columna.nullable, columna.name
    assert real["pk"] == [c.name for c in esperado.primary_key.columns]
    assert real["fks"] == []                       # sin claves foráneas, a propósito
    indices_modelo = {i.name for i in esperado.indexes}
    assert indices_modelo <= set(real["indices"])
    for i in esperado.indexes:
        assert real["indices"][i.name]["column_names"] == [c.name for c in i.columns]


def test_la_unicidad_del_orden_existe_y_funciona(url):
    migrar.upgrade(url)
    real = _inspeccion(url, "agenda_node_attendances")
    assert real["unicas"]["uq_agenda_node_attendances_orden"]["column_names"] == ["appointment_id", "orden"]

    engine = create_engine(url)
    fila = (
        "INSERT INTO agenda_node_attendances (id, appointment_id, orden, status, at, seen, created_at) "
        "VALUES (:id, 'a1', :orden, 'completed', '2026-11-02 12:00:00+00', '{}', '2026-11-02 12:00:00+00')"
    )
    with engine.begin() as c:
        c.execute(text(fila), {"id": "x1", "orden": 1})
    with pytest.raises(Exception, match="(?i)unique|duplic"), engine.begin() as c:
        c.execute(text(fila), {"id": "x2", "orden": 1})
    engine.dispose()


def test_baja_y_deja_la_base_como_estaba(url):
    _base_v014(url)
    migrar.upgrade(url)
    # Con datos en las tablas nuevas: bajar las borra (es para una base de prueba, está dicho en la migración).
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO agenda_applied_attendances (atencion_id, node_id, appointment_id, status, at, resultado, "
            "applied_at) VALUES ('u1', 'nodo-1', 'a1', 'completed', '2026-11-02 12:00:00+00', 'aplicada', "
            "'2026-11-02 12:00:00+00')"
        ))
    engine.dispose()

    command.downgrade(migrar.configuracion(url), "-1")

    assert not TABLAS_NUEVAS & _tablas(url)
    assert _consulta(url, f"SELECT version_num FROM {migrar.TABLA_DE_VERSION}") == [(ANTES,)]
    # Lo que había sigue ahí.
    assert _consulta(url, "SELECT id, status FROM appointments") == [("a1", "confirmed")]
    assert _consulta(url, "SELECT id FROM agenda_clients") == [("c1",)]
    # Y los índices de las tablas nuevas se fueron con ellas (PostgreSQL los tiene como objetos del schema).
    if make_url(url).drivername.startswith("postgresql"):
        quedan = _consulta(url, "SELECT indexname FROM pg_indexes WHERE indexname LIKE '%agenda_%attendances%'")
        assert quedan == []


def test_baja_y_vuelve_a_subir(url):
    migrar.upgrade(url)
    command.downgrade(migrar.configuracion(url), "-1")
    assert not TABLAS_NUEVAS & _tablas(url)
    migrar.upgrade(url)
    assert TABLAS_NUEVAS <= _tablas(url)
    assert _consulta(url, f"SELECT version_num FROM {migrar.TABLA_DE_VERSION}") == [(CABEZA,)]


def test_subir_dos_veces_no_hace_nada(url):
    migrar.upgrade(url)
    migrar.upgrade(url)
    assert _consulta(url, f"SELECT version_num FROM {migrar.TABLA_DE_VERSION}") == [(CABEZA,)]


def test_create_all_y_la_cadena_dejan_las_mismas_tablas(url, tmp_path):
    """Un producto que todavía llama a `create_all` en el arranque tiene que obtener las mismas dos tablas."""
    migrar.upgrade(url)
    por_cadena = TABLAS_NUEVAS & _tablas(url)

    otra = f"sqlite:///{tmp_path / 'create_all.db'}"
    engine = create_engine(otra)
    Base.metadata.create_all(engine)
    por_create_all = TABLAS_NUEVAS & set(inspect(engine).get_table_names())
    engine.dispose()

    assert por_cadena == por_create_all == TABLAS_NUEVAS
