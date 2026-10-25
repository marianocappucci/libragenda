"""La tabla de versión propia y el renombre `clients` → `agenda_clients` (ADR-017 y ADR-018).

Dos cosas que llegan juntas a una base de antes con `libragenda-migrar upgrade`:

1. `alembic_version` (que hasta la v0.13.0 era de LibraGenda) pasa a llamarse `alembic_version_libragenda`, sola, sin
   paso manual del operador. Si no, Alembic creería la base sin migrar y arrancaría en la `0001` contra tablas que ya
   existen.
2. `clients` pasa a `agenda_clients`, con la clave primaria renombrada (`agenda_clients_pkey`), para que las dos tablas
   de LibraCore y de LibraGenda convivan en una base sin objetos con el nombre cruzado.

Corre en SQLite y en PostgreSQL (la segunda sólo con `DATABASE_URL`, como el resto de la suite). El estado «base de
antes» se arma con la misma cadena, parada en la `0009` (que es lo que había en `develop` antes de este cambio) y con la
tabla de versión con el nombre viejo.
"""

import os
import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from libragenda import migrar

ULTIMA_ANTES = "0009_occupancy_and_history"
CABEZA = "0011_node_attendances"
NUEVA = migrar.TABLA_DE_VERSION
VIEJA = migrar.TABLA_DE_VERSION_VIEJA

DATABASE_URL = os.environ.get("DATABASE_URL")


def _url_postgres(base: str) -> str:
    return make_url(DATABASE_URL).set(database=base).render_as_string(hide_password=False)


@pytest.fixture(params=["sqlite", "postgresql"])
def url(request, tmp_path):
    """La URL de una base vacía y propia de cada test."""
    if request.param == "sqlite":
        yield f"sqlite:///{tmp_path / 'agenda.db'}"
        return
    if not DATABASE_URL or not make_url(DATABASE_URL).drivername.startswith("postgresql"):
        pytest.skip("sin DATABASE_URL de PostgreSQL")
    base = f"libragenda_pr1_{uuid.uuid4().hex[:12]}"
    admin = create_engine(_url_postgres("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{base}"'))
    try:
        yield _url_postgres(base)
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{base}" WITH (FORCE)'))
        admin.dispose()


def _sql(url: str, *sentencias: str) -> None:
    engine = create_engine(url)
    with engine.begin() as c:
        for s in sentencias:
            c.execute(text(s))
    engine.dispose()


def _consulta(url: str, sentencia: str) -> list:
    engine = create_engine(url)
    try:
        with engine.connect() as c:
            return list(c.execute(text(sentencia)).all())
    finally:
        engine.dispose()


def _tablas(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _revisiones(url: str, tabla: str) -> list[str]:
    return [f[0] for f in _consulta(url, f"SELECT version_num FROM {tabla}")]


def _base_de_antes(url: str) -> None:
    """Una base como la dejaba la v0.13.0: cadena en la `0009`, versión en `alembic_version`, con datos."""
    migrar.upgrade(url, ULTIMA_ANTES)
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text(f"ALTER TABLE {NUEVA} RENAME TO {VIEJA}"))
        if engine.dialect.name == "postgresql":
            c.execute(text(f"ALTER TABLE {VIEJA} RENAME CONSTRAINT {NUEVA}_pkc TO {VIEJA}_pkc"))
        c.execute(text("INSERT INTO resources (id, name) VALUES ('r1', 'Sillón')"))
        c.execute(text("INSERT INTO services (id, name, duration_seconds) VALUES ('s1', 'Corte', 1800)"))
        c.execute(text("INSERT INTO clients (id, name, phone) VALUES ('c-uuid-1', 'Cliente de prueba', '123')"))
        c.execute(text(
            "INSERT INTO appointments (id, resource_id, service_id, client_id, starts_at, duration_seconds, status) "
            "VALUES ('a1', 'r1', 's1', 'c-uuid-1', '2026-11-02 12:00:00+00', 1800, 'scheduled')"
        ))
    engine.dispose()
    assert _revisiones(url, VIEJA) == [ULTIMA_ANTES]
    assert NUEVA not in _tablas(url)


# ── La tabla de versión propia ───────────────────────────────────────────


def test_una_base_nueva_usa_la_tabla_de_version_propia(url):
    migrar.upgrade(url)

    tablas = _tablas(url)
    assert NUEVA in tablas
    assert VIEJA not in tablas, "la cadena de LibraGenda escribió en la tabla de LibraCore"
    assert _revisiones(url, NUEVA) == [CABEZA]


def test_autorrenombra_la_tabla_de_version_de_una_base_de_antes(url):
    """🔴 El caso de GestioLibra y MedLibra hoy: el deploy corre `libragenda-migrar upgrade` y tiene que andar."""
    _base_de_antes(url)

    migrar.upgrade(url)

    tablas = _tablas(url)
    assert NUEVA in tablas and VIEJA not in tablas
    assert _revisiones(url, NUEVA) == [CABEZA]


def test_el_autorrenombre_se_repite_sin_efecto(url):
    _base_de_antes(url)
    migrar.upgrade(url)
    migrar.upgrade(url)

    assert _revisiones(url, NUEVA) == [CABEZA]
    assert VIEJA not in _tablas(url)


def test_no_toca_un_alembic_version_que_es_de_libracore(url):
    """🔴 En una base unida `alembic_version` es del motor: el renombre no puede llevársela."""
    _sql(
        url,
        f"CREATE TABLE {VIEJA} (version_num VARCHAR(32) NOT NULL, CONSTRAINT {VIEJA}_pkc PRIMARY KEY (version_num))",
        f"INSERT INTO {VIEJA} VALUES ('0041_algo_de_libracore')",
    )

    migrar.upgrade(url)

    assert _revisiones(url, VIEJA) == ["0041_algo_de_libracore"]
    assert _revisiones(url, NUEVA) == [CABEZA]


def test_no_toca_un_alembic_version_que_mezcla_cadenas(url):
    """Con una revisión de LibraGenda y otra ajena en la misma tabla no se adivina de quién es: no se renombra."""
    _sql(
        url,
        f"CREATE TABLE {VIEJA} (version_num VARCHAR(32) NOT NULL, CONSTRAINT {VIEJA}_pkc PRIMARY KEY (version_num))",
        f"INSERT INTO {VIEJA} VALUES ('{ULTIMA_ANTES}')",
        f"INSERT INTO {VIEJA} VALUES ('0041_algo_de_libracore')",
    )
    engine = create_engine(url)
    with engine.connect() as c:
        assert migrar.adoptar_la_tabla_de_version_vieja(c, {ULTIMA_ANTES, CABEZA}) is False
    engine.dispose()
    assert sorted(_revisiones(url, VIEJA)) == sorted([ULTIMA_ANTES, "0041_algo_de_libracore"])


def test_no_renombra_si_la_propia_ya_existe(url):
    migrar.upgrade(url)
    _sql(
        url,
        f"CREATE TABLE {VIEJA} (version_num VARCHAR(32) NOT NULL, CONSTRAINT {VIEJA}_pkc PRIMARY KEY (version_num))",
        f"INSERT INTO {VIEJA} VALUES ('{ULTIMA_ANTES}')",
    )

    migrar.upgrade(url)

    assert _revisiones(url, VIEJA) == [ULTIMA_ANTES]
    assert _revisiones(url, NUEVA) == [CABEZA]


# ── clients → agenda_clients ─────────────────────────────────────────────


def test_el_renombre_conserva_las_filas_y_las_claves_foraneas(url):
    _base_de_antes(url)

    migrar.upgrade(url)

    tablas = _tablas(url)
    assert "agenda_clients" in tablas and "clients" not in tablas
    assert _consulta(url, "SELECT id, name, phone FROM agenda_clients") == [("c-uuid-1", "Cliente de prueba", "123")]
    assert _consulta(url, "SELECT client_id FROM appointments") == [("c-uuid-1",)]
    engine = create_engine(url)
    try:
        referidas = {f["referred_table"] for f in inspect(engine).get_foreign_keys("appointments")}
    finally:
        engine.dispose()
    assert "agenda_clients" in referidas and "clients" not in referidas


def test_downgrade_y_upgrade_son_simetricos(url):
    _base_de_antes(url)
    migrar.upgrade(url)

    command.downgrade(migrar.configuracion(url), ULTIMA_ANTES)

    assert _revisiones(url, NUEVA) == [ULTIMA_ANTES]
    tablas = _tablas(url)
    assert "clients" in tablas and "agenda_clients" not in tablas
    assert _consulta(url, "SELECT id FROM clients") == [("c-uuid-1",)]
    engine = create_engine(url)
    try:
        referidas = {f["referred_table"] for f in inspect(engine).get_foreign_keys("appointments")}
        pk = inspect(engine).get_pk_constraint("clients")["name"]
    finally:
        engine.dispose()
    assert "clients" in referidas and "agenda_clients" not in referidas
    if make_url(url).get_backend_name() == "postgresql":
        assert pk == "clients_pkey"

    migrar.upgrade(url)
    assert _revisiones(url, NUEVA) == [CABEZA]
    assert _consulta(url, "SELECT id FROM agenda_clients") == [("c-uuid-1",)]


def test_si_agenda_clients_ya_existe_la_migracion_aborta_y_no_deja_nada_a_medias(url):
    """Un `create_all` con el código nuevo antes que la cadena deja `agenda_clients` al lado de `clients`.

    El mensaje tiene que decir qué pasó, y en PostgreSQL (DDL transaccional) la base queda como estaba: ni el renombre
    de la tabla de versión ni nada de la migración se aplica.
    """
    _base_de_antes(url)
    _sql(url, "CREATE TABLE agenda_clients (id VARCHAR(100) PRIMARY KEY)")

    with pytest.raises(RuntimeError, match="ya existe"):
        migrar.upgrade(url)

    if make_url(url).get_backend_name() == "postgresql":
        assert _revisiones(url, VIEJA) == [ULTIMA_ANTES]
        assert NUEVA not in _tablas(url)
    assert "clients" in _tablas(url)
    assert _consulta(url, "SELECT id FROM clients") == [("c-uuid-1",)]


def test_el_downgrade_no_pisa_la_clients_de_libracore(url):
    """En una base ya unida `clients` es la del motor: volver atrás no puede renombrar encima ni perder filas."""
    migrar.upgrade(url)
    # Primero se baja lo posterior a la `0010` (la `0011` no toca `clients`): el choque es con la `0010`.
    command.downgrade(migrar.configuracion(url), "0010_agenda_clients")
    _sql(url, "CREATE TABLE clients (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    _sql(url, "INSERT INTO clients (id, name) VALUES (1, 'Del motor')")

    with pytest.raises(RuntimeError, match="revertir la unión"):
        command.downgrade(migrar.configuracion(url), ULTIMA_ANTES)

    assert _consulta(url, "SELECT id, name FROM clients") == [(1, "Del motor")]
    assert _revisiones(url, NUEVA) == ["0010_agenda_clients"]


# ── La convivencia con LibraCore en una sola base (sólo PostgreSQL) ──────


def test_convive_con_las_tablas_de_libracore_en_la_misma_base(url):
    """🔴 Lo que justifica los dos cambios: después del upgrade, LibraCore puede crear SUS `clients` y `alembic_version`.

    Se arma con el DDL mínimo que importa (los nombres de objeto que LibraCore trae): en PostgreSQL el índice de una
    clave primaria es un objeto del schema, así que `alembic_version_pkc` no puede estar dos veces. Sin el renombre de
    la restricción de la tabla de versión el segundo `CREATE` falla (*relation "alembic_version_pkc" already exists*).
    """
    if make_url(url).get_backend_name() != "postgresql":
        pytest.skip("los nombres de índice y de restricción son globales sólo en PostgreSQL")
    _base_de_antes(url)

    migrar.upgrade(url)

    _sql(
        url,
        "CREATE TABLE clients (id SERIAL PRIMARY KEY, name TEXT NOT NULL)",
        f"CREATE TABLE {VIEJA} (version_num VARCHAR(32) NOT NULL, CONSTRAINT {VIEJA}_pkc PRIMARY KEY (version_num))",
        f"INSERT INTO {VIEJA} VALUES ('0042_cabeza_de_libracore')",
    )
    assert _revisiones(url, VIEJA) == ["0042_cabeza_de_libracore"]
    assert _revisiones(url, NUEVA) == [CABEZA]
    # Y la cadena de LibraGenda sigue andando al lado de la de LibraCore.
    migrar.upgrade(url)
    assert _revisiones(url, NUEVA) == [CABEZA]
    assert _revisiones(url, VIEJA) == ["0042_cabeza_de_libracore"]


def test_la_clave_primaria_de_la_tabla_renombrada_se_llama_como_ella(url):
    if make_url(url).get_backend_name() != "postgresql":
        pytest.skip("SQLite no nombra sus claves primarias")
    _base_de_antes(url)

    migrar.upgrade(url)

    engine = create_engine(url)
    try:
        assert inspect(engine).get_pk_constraint("agenda_clients")["name"] == "agenda_clients_pkey"
        assert inspect(engine).get_pk_constraint(NUEVA)["name"] == f"{NUEVA}_pkc"
    finally:
        engine.dispose()


def test_el_orden_de_las_cadenas_importa_libragenda_primero(url):
    """La `0002` crea `clients`: en una base donde LibraCore ya creó la suya, la cadena de LibraGenda no puede empezar.

    No es un defecto a arreglar acá (cambiar una revisión ya aplicada rompería las bases existentes): es el orden que
    el ADR-018 le pide a los consumidores, y esta prueba lo deja medido.
    """
    if make_url(url).get_backend_name() != "postgresql":
        pytest.skip("sólo PostgreSQL")
    _sql(url, "CREATE TABLE clients (id SERIAL PRIMARY KEY, name TEXT NOT NULL)")

    with pytest.raises(Exception, match="clients"):
        migrar.upgrade(url)
