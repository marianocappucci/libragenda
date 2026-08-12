"""El repositorio, EJECUTADO contra los dos motores y comparado.

**Que cubria este repo antes.** Ocho archivos de test corren contra
`sqlite:///:memory:` y dos usan `DATABASE_URL` para PostgreSQL real -- pero
esos dos prueban **migraciones y schema**: que el DDL se aplique. Ninguno
ejecuta una lectura del repositorio contra PostgreSQL.

Es exactamente el hueco que el piloto de LibraDesk midio el 2026-08-09: tres
gates en verde -- la app arranca, el schema se crea entero, el traductor
transforma bien el texto del SQL -- y 5 de 7 lecturas rotas, porque ninguno
ejecutaba una consulta.

La regla que sigue este archivo: *sembrar filas, ejecutar las lecturas y
comparar el resultado ENTERO entre los dos motores*, con la contraprueba de que
trajo filas -- sobre tablas vacias, dos listas vacias comparan iguales.

Se saltea sin `LIBRAGENDA_PG_URL`. En CI la pone el workflow.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from libragenda.domain import Appointment, AppointmentStatus
from libragenda.sqlalchemy_repository import (
    Base, BranchRow, ClientRow, ResourceRow, ServiceRow,
    SqlAlchemyAppointmentRepository,
)

PG_URL = os.environ.get("LIBRAGENDA_PG_URL") or os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not PG_URL.startswith("postgresql"),
    reason="sin PostgreSQL real: no hay contra que comparar",
)

#: Offset de Argentina. NO es decorativo: es lo unico que distingue "guardo el
#: instante" de "guardo la hora de pared". Con datetimes en UTC los dos motores
#: coinciden pase lo que pase y la comparacion no prueba nada.
AR = timezone(timedelta(hours=-3))


def _repo(url: str) -> SqlAlchemyAppointmentRepository:
    engine = create_engine(url)
    # `drop_all` primero: la base de CI sobrevive entre modulos, y filas de otra
    # corrida harian que las comparaciones midan contra datos ajenos.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    with Session.begin() as s:
        s.add(BranchRow(id="b1", name="Sucursal"))
        s.add(ClientRow(id="c1", name="Cliente"))
        s.add(ResourceRow(id="r1", name="Recurso"))
        s.add(ResourceRow(id="r2", name="Recurso secundario"))
        s.add(ServiceRow(id="s1", name="Servicio", duration_seconds=1800))
    return SqlAlchemyAppointmentRepository(Session)


def _turno(n: int, cuando: datetime) -> Appointment:
    return Appointment(
        id=f"a{n}", resource_id="r1", service_id="s1", client_id="c1",
        starts_at=cuando, duration=timedelta(minutes=30),
        status=AppointmentStatus.CONFIRMED, branch_id="b1",
    )


#: Tres turnos con offset local, a proposito fuera de orden de alta.
CUANDO = [
    datetime(2026, 8, 10, 9, 0, tzinfo=AR),
    datetime(2026, 8, 10, 8, 0, tzinfo=AR),
    datetime(2026, 8, 10, 23, 30, tzinfo=AR),   # cruza el dia en UTC
]


@pytest.fixture
def dos_motores(tmp_path):
    pg = _repo(PG_URL)
    lite = _repo(f"sqlite:///{tmp_path}/libragenda.db")
    for i, cuando in enumerate(CUANDO):
        for repo in (pg, lite):
            repo.add(_turno(i, cuando))
    return pg, lite


def test_un_turno_con_offset_local_guarda_EL_MISMO_INSTANTE_en_los_dos(dos_motores):
    """🔴 El defecto que encontro la F3, medido el 2026-08-09.

    Un turno a las `09:00-03:00` son las 12:00 UTC. Antes de `UtcDateTime`:

    | Motor | Volvia |
    |---|---|
    | PostgreSQL | `12:00+00:00` -- el instante correcto |
    | SQLite | `09:00+00:00` -- **corrido 3 horas** |

    SQLite no tiene tipo con zona: recibia el datetime tal cual, perdia el
    offset y guardaba la hora de pared. `ensure_utc` no puede repararlo al
    leer, porque para entonces el offset ya no existe.

    Importa porque **SQLite es lo que corre en produccion hoy** en los seis
    productos: el hueco no era "PostgreSQL va a romper", era "SQLite ya estaba
    mal". Y `Appointment` no normaliza `starts_at` -- valida ids y duracion --,
    asi que lo que manda el producto llega intacto al repositorio.
    """
    pg, lite = dos_motores

    for i, cuando in enumerate(CUANDO):
        a_pg, a_lite = pg.get(f"a{i}"), lite.get(f"a{i}")
        assert a_pg is not None and a_lite is not None, f"falta a{i}"
        esperado = cuando.astimezone(timezone.utc)
        assert a_pg.starts_at == esperado, f"PostgreSQL movio a{i}"
        assert a_lite.starts_at == esperado, f"SQLite movio a{i}"
        assert a_pg.starts_at == a_lite.starts_at


def test_list_devuelve_lo_mismo_y_en_el_mismo_orden(dos_motores):
    """`list()` ordena por `starts_at`, que es la columna del defecto de
    arriba: si un motor guarda la hora de pared y el otro el instante, el
    ORDEN tambien puede cambiar, no solo los valores. Por eso se compara la
    tupla entera y no un conjunto."""
    pg, lite = dos_motores

    filas_pg, filas_lite = pg.list(), lite.list()

    # Contraprueba: sin esto la comparacion pasa con las dos vacias.
    assert len(filas_pg) == len(CUANDO), filas_pg
    assert filas_pg == filas_lite

    # Y que el orden sea el cronologico de verdad, no el de alta.
    assert [a.id for a in filas_pg] == ["a1", "a0", "a2"], [a.id for a in filas_pg]


def test_reserve_corre_el_camino_de_POSTGRES_y_no_solo_el_de_sqlite(dos_motores):
    """🔴 `reserve()` tiene una rama explicita por dialecto.

        if session.bind.dialect.name == "sqlite":
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        ...
        select(ResourceRow).where(...).with_for_update()

    O sea que los dos motores toman **caminos de codigo distintos**, y hasta
    ahora ningun test ejecutaba el de PostgreSQL: el `SELECT ... FOR UPDATE`
    nunca habia corrido contra un motor que lo implemente de verdad. SQLite lo
    acepta y lo ignora, asi que un test sobre SQLite no dice nada del otro
    camino.
    """
    pg, lite = dos_motores
    nuevo = datetime(2026, 8, 11, 10, 0, tzinfo=AR)

    for repo in (pg, lite):
        guardado = repo.reserve(_turno(99, nuevo), validator=lambda existentes: _turno(99, nuevo))
        assert guardado.starts_at == nuevo.astimezone(timezone.utc)

    assert pg.get("a99") is not None
    assert pg.get("a99").starts_at == lite.get("a99").starts_at

    # La contraprueba: reservar el mismo id dos veces tiene que fallar en los
    # dos motores. Sin esto, un `reserve` que no escribiera nada pasaria igual.
    for repo in (pg, lite):
        with pytest.raises(ValueError):
            repo.reserve(_turno(99, nuevo), validator=lambda existentes: _turno(99, nuevo))


def test_un_datetime_naive_se_toma_como_utc_en_los_dos(dos_motores):
    """El unico caso donde los dos motores ya coincidian antes del arreglo, y
    por eso `UtcDateTime` lo deja como estaba: cambiarlo moveria datos que ya
    estan guardados."""
    pg, lite = dos_motores
    naive = datetime(2026, 8, 12, 15, 0)

    for repo in (pg, lite):
        repo.add(_turno(77, naive))

    esperado = naive.replace(tzinfo=timezone.utc)
    assert pg.get("a77").starts_at == esperado
    assert lite.get("a77").starts_at == esperado
