"""Los dos caminos que escriben sobre el mismo hueco, corridos a la vez.

**Que cubria este repo antes, y que no.** El alta ya estaba cubierta por los
dos lados: `test_application.py` corre dos `create()` a la vez contra un
repositorio de memoria con barrera, y `test_postgres_real.py` verifica que la
rama del `SELECT ... FOR UPDATE` **se ejecute** contra PostgreSQL. Lo que
faltaba es el cruce de las dos cosas --dos escrituras simultaneas contra un
motor que implementa locks de fila de verdad-- y, sobre todo, el otro camino.

Porque `reschedule()` --mover un turno ya guardado-- validaba el choque y
despues escribia con `save()`, **fuera** de esa transaccion. Es la misma
carrera que `reserve()` cierra, viva en el camino espejo: dos reagendados hacia
el mismo hueco libre validan los dos contra un estado sin el otro, y guardan
los dos. Gestiolibra y MedLibra lo exponen como
`POST /appointments/{id}/reschedule`, asi que se alcanza por HTTP.

**Como se hace deterministica** una carrera, sin dormir y cruzar los dedos: el
validador del primer hilo avisa que ya leyo y recien ahi arranca el segundo,
mientras el primero sigue adentro de su transaccion. Sin lock el segundo lee un
estado que no tiene al primero; con lock se queda esperando la fila del recurso
hasta que el primero comitea, y entonces si lo ve.

La contraprueba de todo el archivo es `test_el_camino_sin_lock_SI_duplica`: sin
ella, un `relocate` que no escribiera nada pasaria igual, y el verde no probaria
que el arnes es capaz de detectar el doble booking que dice prevenir.

Se saltea sin `LIBRAGENDA_PG_URL`/`DATABASE_URL`: SQLite acepta
`FOR UPDATE` y lo ignora, asi que sobre SQLite estos tests no dicen nada.
"""
import os
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from libragenda.domain import Appointment, AppointmentStatus
from libragenda.sqlalchemy_repository import (
    AppointmentRow,
    Base,
    BranchRow,
    ClientRow,
    ResourceRow,
    ServiceRow,
    SqlAlchemyAppointmentRepository,
)

PG_URL = os.environ.get("LIBRAGENDA_PG_URL") or os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not PG_URL.startswith("postgresql"),
    reason="sin PostgreSQL real no hay locks de fila: SQLite acepta FOR UPDATE y lo ignora",
)

#: El hueco libre al que los dos turnos quieren mudarse.
DESTINO = datetime(2026, 8, 12, 11, 0, tzinfo=UTC)

#: Cuanto espera el segundo hilo a que el primero lo desbloquee. Es un tope de
#: falla, no una espera esperada: con el lock puesto el desbloqueo llega apenas
#: comitea el primero.
TOPE = 15.0

#: Lo que el primer hilo se queda adentro de la ventana, para que el segundo
#: corra de verdad en paralelo y no despues.
RETENER = 1.0


class Choque(Exception):
    """Lo que levanta el validador de estos tests al ver el hueco ocupado."""


def _turno(n: int, cuando: datetime) -> Appointment:
    return Appointment(
        id=f"a{n}", resource_id="r1", service_id="s1", client_id="c1",
        starts_at=cuando, duration=timedelta(minutes=30),
        status=AppointmentStatus.CONFIRMED, branch_id="b1",
    )


@pytest.fixture
def repo():
    engine = create_engine(PG_URL)
    # La base sobrevive entre modulos en CI: filas de otra corrida harian que
    # el conteo final midiera contra datos ajenos.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    with Session.begin() as s:
        s.add(BranchRow(id="b1", name="Sucursal"))
        s.add(ClientRow(id="c1", name="Cliente"))
        s.add(ResourceRow(id="r1", name="Recurso"))
        s.add(ServiceRow(id="s1", name="Servicio", duration_seconds=1800))
    repo = SqlAlchemyAppointmentRepository(Session)
    # Dos turnos en huecos distintos; el destino queda libre para los dos.
    repo.add(_turno(1, datetime(2026, 8, 12, 8, 0, tzinfo=UTC)))
    repo.add(_turno(2, datetime(2026, 8, 12, 9, 0, tzinfo=UTC)))
    return repo


def _en_destino(session_factory) -> list[str]:
    with session_factory() as s:
        filas = s.scalars(select(AppointmentRow).where(AppointmentRow.starts_at == DESTINO)).all()
        return sorted(fila.id for fila in filas)


def _validador(mi_id: str, aviso: threading.Event | None = None, retener: float = 0.0):
    """Rechaza el destino si lo ve ocupado por otro turno.

    `existentes` ya viene leido, asi que la foto que mira este validador es la
    de antes de dormir. `aviso` le da el turno al otro hilo y `retener` deja
    este **sin terminar** mientras el otro corre: es lo que abre la ventana
    entre validar y escribir, que es exactamente donde vive la carrera.

    Sin `retener` los dos tests de abajo pasarian por casualidad --el primer
    hilo alcanza a comitear antes de que el segundo lea-- y el verde no diria
    nada del lock.
    """
    def validar(existentes):
        ocupado = [t for t in existentes if t.id != mi_id and t.starts_at == DESTINO]
        if aviso is not None:
            aviso.set()
        if retener:
            time.sleep(retener)
        if ocupado:
            raise Choque(f"{DESTINO} ya lo tiene {ocupado[0].id}")
        return _turno(int(mi_id[1:]), DESTINO)
    return validar


def _correr_los_dos(primero, segundo):
    """Corre `primero` y, apenas avise que leyo, `segundo`. Devuelve sus errores."""
    leyo = threading.Event()
    errores: dict[str, BaseException | None] = {"primero": None, "segundo": None}

    def envolver(clave, fn):
        def correr():
            try:
                fn()
            except BaseException as exc:      # noqa: BLE001 - se reporta tal cual
                errores[clave] = exc
        return correr

    hilo_a = threading.Thread(target=envolver("primero", lambda: primero(leyo)))
    hilo_a.start()
    assert leyo.wait(TOPE), "el primer hilo nunca llego a leer: el arnes no probo nada"
    hilo_b = threading.Thread(target=envolver("segundo", segundo))
    hilo_b.start()
    hilo_a.join(TOPE)
    hilo_b.join(TOPE)
    assert not hilo_a.is_alive() and not hilo_b.is_alive(), "un hilo quedo colgado"
    return errores


def test_dos_reagendados_al_mismo_hueco_no_entran_los_dos(repo):
    """🔴 El defecto que cierra `relocate`: mover dos turnos al mismo hueco.

    Es la carrera que `reserve()` cierra para el alta, en el camino espejo.
    """
    def primero(leyo):
        repo.relocate(_turno(1, DESTINO), _validador("a1", aviso=leyo, retener=RETENER))

    def segundo():
        repo.relocate(_turno(2, DESTINO), _validador("a2"))

    errores = _correr_los_dos(primero, segundo)

    fallaron = [k for k, v in errores.items() if v is not None]
    assert fallaron == ["segundo"], f"errores: {errores}"
    assert isinstance(errores["segundo"], Choque), errores["segundo"]
    assert _en_destino(repo.session_factory) == ["a1"]


def test_el_camino_sin_lock_SI_duplica(repo):
    """La contraprueba: el arnes detecta el doble booking que el otro previene.

    Reproduce a mano lo que hacia `reschedule()` antes --leer y validar por un
    lado, escribir con `save()` por otro-- y verifica que los dos turnos
    terminan en el mismo hueco. Sin este test, el verde del anterior no
    distinguiria "el lock funciona" de "estos dos hilos nunca se cruzaron".
    """
    def sin_lock(mi_id: str, aviso: threading.Event | None = None):
        validar = _validador(mi_id, aviso=aviso, retener=RETENER if aviso else 0.0)
        movido = validar(repo.list())          # leer y validar, fuera de la transaccion
        repo.save(movido)                      # y recien despues escribir

    errores = _correr_los_dos(
        lambda leyo: sin_lock("a1", aviso=leyo),
        lambda: sin_lock("a2"),
    )

    assert errores == {"primero": None, "segundo": None}, errores
    assert _en_destino(repo.session_factory) == ["a1", "a2"], (
        "el arnes no reprodujo el doble booking, asi que el test hermano no prueba nada"
    )


def test_relocate_exige_que_el_turno_exista(repo):
    """`relocate` mueve lo que ya esta guardado; no es un alta encubierta."""
    with pytest.raises(KeyError):
        repo.relocate(_turno(99, DESTINO), _validador("a99"))
    assert _en_destino(repo.session_factory) == []
