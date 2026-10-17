"""Crear el esquema con dos procesos arrancando a la vez (`libragenda.crear_esquema`, ADR-015).

MedLibra y Gestiolibra crean sus tablas en el arranque con `Base.metadata.create_all(get_engine())`, y con
`uvicorn --workers 2` ese arranque corre dos veces, juntas. `create_all` primero mira qué tablas faltan y después las crea:
los dos contestan «faltan todas» antes de que ninguno cree y el segundo `CREATE TABLE` choca.

**Cómo se hace determinista**: un evento `before_create` del `MetaData` duerme `VENTANA` segundos justo después de que
`create_all` miró y antes de que cree, que es la ventana de la carrera. En una máquina rápida esa ventana dura milisegundos
y dos hilos casi nunca la pisan; ensancharla es lo que hace que el test se ponga rojo sin el candado. Lo que se mide sigue
siendo el código de la librería.

La contraprueba (`*_sin_el_candado_chocan`) es la que cuida al resto: sin ella, un `crear_esquema` que no creara nada pasaría
igual, y el verde no probaría que el arnés es capaz de ver el choque que dice prevenir.

PostgreSQL con `LIBRAGENDA_PG_URL`/`DATABASE_URL`; los de SQLite corren siempre (archivo temporal).
"""
import os
import threading
import time

import pytest
from sqlalchemy import Column, Engine, Integer, MetaData, String, Table, create_engine, event, inspect, text

from libragenda import crear_esquema
from libragenda import esquema as modulo
from libragenda.sqlalchemy_repository import Base, SqlAlchemyAppointmentRepository, SqlAlchemyTransitionLog

PG_URL = os.environ.get("LIBRAGENDA_PG_URL") or os.environ.get("DATABASE_URL", "")
HAY_PG = PG_URL.startswith("postgresql")

#: Lo que `create_all` se queda entre «miré» y «creo». Con el candado el segundo proceso espera esto mismo, entero.
VENTANA = 1.0

TABLAS = tuple(f"prueba_esquema_{n}" for n in "abc")


def _metadata() -> MetaData:
    metadata = MetaData()
    for nombre in TABLAS:
        Table(nombre, metadata, Column("id", Integer, primary_key=True), Column("valor", String(20)))
    event.listen(metadata, "before_create", lambda *a, **k: time.sleep(VENTANA))
    return metadata


def _en_paralelo(motores: list[Engine], trabajo) -> list[BaseException | None]:
    """Un hilo por motor (cada uno con su propia conexión), que arrancan JUNTOS. Devuelve la excepción de cada uno."""
    barrera = threading.Barrier(len(motores))
    errores: list[BaseException | None] = [None] * len(motores)

    def correr(i: int) -> None:
        barrera.wait()
        try:
            trabajo(motores[i])
        except BaseException as e:  # noqa: BLE001 - se devuelve para que el test lo vea, no se pierde en el hilo
            errores[i] = e

    hilos = [threading.Thread(target=correr, args=(i,)) for i in range(len(motores))]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    return errores


@pytest.fixture
def pg():
    motores = [create_engine(PG_URL), create_engine(PG_URL)]
    with motores[0].begin() as c:
        for t in TABLAS:
            c.execute(text(f"DROP TABLE IF EXISTS {t}"))
    yield motores
    with motores[0].begin() as c:
        for t in TABLAS:
            c.execute(text(f"DROP TABLE IF EXISTS {t}"))
    for m in motores:
        m.dispose()


@pytest.fixture
def sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'agenda.db'}"
    motores = [create_engine(url, connect_args={"timeout": 30}), create_engine(url, connect_args={"timeout": 30})]
    yield motores
    for m in motores:
        m.dispose()


def _tablas(motor: Engine) -> set[str]:
    return set(inspect(motor).get_table_names()) & set(TABLAS)


@pytest.mark.skipif(not HAY_PG, reason="sin PostgreSQL real no hay catálogo que choque")
def test_postgres_dos_procesos_crean_el_esquema_a_la_vez(pg):
    metadata = _metadata()

    errores = _en_paralelo(pg, lambda motor: crear_esquema(motor, metadata))

    assert errores == [None, None], errores
    assert _tablas(pg[0]) == set(TABLAS)


@pytest.mark.skipif(not HAY_PG, reason="sin PostgreSQL real no hay catálogo que choque")
def test_postgres_sin_el_candado_chocan(pg):
    """La contraprueba: el mismo arnés, con `create_all` pelado, SÍ choca. Sin esto el verde de arriba no prueba nada."""
    metadata = _metadata()

    errores = _en_paralelo(pg, lambda motor: metadata.create_all(motor))

    assert any(errores), "create_all pelado no chocó: la ventana no se está pisando y el test de arriba no cuida nada"


@pytest.mark.skipif(not HAY_PG, reason="el candado asesor es de PostgreSQL")
def test_postgres_si_otro_lo_tiene_y_no_termina_el_arranque_lo_dice(pg):
    metadata = _metadata()
    with pg[1].begin() as otro:
        modulo.serializar_esquema(otro)                       # lo tiene otro proceso, en una transacción abierta
        with pytest.raises(TimeoutError, match="candado del esquema"):
            crear_esquema(pg[0], metadata, espera=0.5)
    assert _tablas(pg[0]) == set()                            # no creó nada a medias


def test_sqlite_dos_procesos_crean_el_esquema_a_la_vez(sqlite):
    metadata = _metadata()

    errores = _en_paralelo(sqlite, lambda motor: crear_esquema(motor, metadata))

    assert errores == [None, None], errores
    assert _tablas(sqlite[0]) == set(TABLAS)


def test_sqlite_sin_el_candado_chocan(sqlite):
    metadata = _metadata()

    errores = _en_paralelo(sqlite, lambda motor: metadata.create_all(motor))

    assert any(errores), "create_all pelado no chocó: la ventana no se está pisando y el test de arriba no cuida nada"


def test_en_memoria_no_toma_ningun_candado():
    motor = create_engine("sqlite:///:memory:")
    with motor.begin() as conexion:
        assert modulo.serializar_esquema(conexion) is False


def test_sin_metadata_crea_las_tablas_de_libragenda(tmp_path):
    motor = create_engine(f"sqlite:///{tmp_path / 'agenda.db'}")

    crear_esquema(motor)

    assert set(Base.metadata.tables) <= set(inspect(motor).get_table_names())
    crear_esquema(motor)          # idempotente: es el create_all de siempre, con candado


@pytest.mark.parametrize("repositorio", [SqlAlchemyAppointmentRepository, SqlAlchemyTransitionLog])
def test_from_url_crea_el_esquema_con_el_candado(repositorio, tmp_path, monkeypatch):
    visto = []
    original = modulo.serializar_esquema
    monkeypatch.setattr(modulo, "serializar_esquema", lambda *a, **k: visto.append(1) or original(*a, **k))

    repositorio.from_url(f"sqlite:///{tmp_path / 'agenda.db'}")

    assert visto == [1]


# ── Sin PostgreSQL a mano: las ramas que el CI de SQLite no ve de otro modo ─────────────────────────────────────────────

def test_la_clave_del_candado_es_estable_y_entra_en_un_bigint():
    clave = modulo._clave(modulo.CANDADO_DEL_ESQUEMA)
    assert clave == modulo._clave(modulo.CANDADO_DEL_ESQUEMA)
    assert 0 < clave < 2 ** 56
    assert clave != modulo._clave("otro")


def test_sqlite_si_otro_tiene_la_base_y_no_suelta_el_arranque_lo_dice(tmp_path):
    """Otro proceso con `BEGIN IMMEDIATE` tomado: el arranque reintenta y, vencida la espera, `TimeoutError` con el motivo."""
    import sqlite3

    ruta = tmp_path / "agenda.db"
    otro = sqlite3.connect(ruta, timeout=0, isolation_level=None)
    otro.execute("BEGIN IMMEDIATE")
    try:
        motor = create_engine(f"sqlite:///{ruta}", connect_args={"timeout": 0})
        with pytest.raises(TimeoutError, match="SQLite"):
            crear_esquema(motor, _metadata(), espera=0.3)
    finally:
        otro.execute("ROLLBACK")
        otro.close()


class _Dialecto:
    def __init__(self, nombre):
        self.name = nombre


class _ConexionFalsa:
    """Lo mínimo de una `Connection` para recorrer la rama de PostgreSQL sin un servidor."""

    def __init__(self, nombre, respuestas=()):
        self.dialect = _Dialecto(nombre)
        self._respuestas = list(respuestas)
        self.pedidos = []

    def execute(self, sentencia, params=None):
        self.pedidos.append((str(sentencia), params))
        valor = self._respuestas.pop(0)
        return type("R", (), {"scalar": lambda _self: valor})()


def test_postgres_reintenta_hasta_tomar_el_candado(monkeypatch):
    monkeypatch.setattr(modulo, "_PASO", 0)
    conexion = _ConexionFalsa("postgresql", [False, False, True])

    assert modulo.serializar_esquema(conexion) is True
    assert len(conexion.pedidos) == 3
    assert all("pg_try_advisory_xact_lock" in s for s, _ in conexion.pedidos)
    assert conexion.pedidos[0][1] == {"clave": modulo._clave(modulo.CANDADO_DEL_ESQUEMA)}


def test_un_motor_desconocido_no_toma_candado():
    assert modulo.serializar_esquema(_ConexionFalsa("mysql")) is False
