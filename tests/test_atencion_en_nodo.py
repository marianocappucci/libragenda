"""Atender un turno en un nodo sin conexión y aplicarlo en el central (ADR-019).

Corre en SQLite y, con `DATABASE_URL`, en PostgreSQL. Cada test arma sus bases con la cadena de migraciones real
(`libragenda-migrar`), no con `create_all`: lo que se prueba es lo que despliega el producto.

Lo que se cubre, en el orden del módulo:

1. **El nodo**: la fila propia, la operación en la misma transacción, las reglas de estado, el estado efectivo.
2. **El central, camino normal**: la transición con la hora del nodo.
3. **Idempotencia**: la misma operación dos o tres veces es un solo efecto; también entregada a la vez (PostgreSQL).
4. **Cada conflicto con la web** (cancelado, movido, ya atendido, en otro estado, inexistente): la atención igual
   queda, `extra` llega al producto y el turno va a «a revisar».
5. **La lista «a revisar»** y `marcar_revisada`.
6. **La validación de la operación** y el despachador.
7. **De punta a punta**: dos bases, la del nodo y la del central.
"""

import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from libragenda import atencion_en_nodo as atencion
from libragenda import database, migrar
from libragenda.application import AppointmentNotFound, InvalidTransition
from libragenda.domain import AppointmentStatus as S
from libragenda.sqlalchemy_repository import (
    AppliedAttendanceRow,
    AppointmentRow,
    AppointmentTransitionRow,
    BranchRow,
    ClientRow,
    NodeAttendanceRow,
    ResourceRow,
    ServiceRow,
)

DATABASE_URL = os.environ.get("DATABASE_URL")
AR = timezone(timedelta(hours=-3))
NODO = "nodo-sucursal-1"
INICIO = datetime(2026, 11, 3, 10, 0, tzinfo=AR)


def _url_postgres(base: str) -> str:
    return make_url(DATABASE_URL).set(database=base).render_as_string(hide_password=False)


@pytest.fixture(params=["sqlite", "postgresql"])
def nueva_base(request, tmp_path):
    """Una fábrica de bases vacías y migradas (`nueva_base()` → `(url, sessionmaker)`), borradas al terminar."""
    if request.param == "postgresql" and (
        not DATABASE_URL or not make_url(DATABASE_URL).drivername.startswith("postgresql")
    ):
        pytest.skip("sin DATABASE_URL de PostgreSQL")
    creadas: list[tuple[str, object]] = []
    admin = None
    if request.param == "postgresql":
        admin = create_engine(_url_postgres("postgres"), isolation_level="AUTOCOMMIT")

    def fabrica():
        if request.param == "sqlite":
            url = f"sqlite:///{tmp_path / (uuid.uuid4().hex[:8] + '.db')}"
        else:
            base = f"libragenda_pr8_{uuid.uuid4().hex[:12]}"
            with admin.connect() as c:
                c.execute(text(f'CREATE DATABASE "{base}"'))
            url = _url_postgres(base)
        migrar.upgrade(url)
        engine = create_engine(url)
        creadas.append((url, engine))
        return url, sessionmaker(engine, expire_on_commit=False)

    fabrica.motor = request.param
    yield fabrica
    for url, engine in creadas:
        engine.dispose()
        if request.param == "postgresql":
            with admin.connect() as c:
                c.execute(text(f'DROP DATABASE IF EXISTS "{make_url(url).database}" WITH (FORCE)'))
    if admin is not None:
        admin.dispose()


@pytest.fixture
def base(nueva_base):
    url, fabrica = nueva_base()
    return fabrica


@pytest.fixture(autouse=True)
def _sin_configuracion():
    atencion.configurar(None)
    yield
    atencion.configurar(None)


# ── Apoyo ────────────────────────────────────────────────────────────────────


@dataclass
class Outbox:
    """El outbox del producto, de mentira: guarda lo que se encoló. `falla` simula un outbox roto."""

    operaciones: list = field(default_factory=list)
    falla: bool = False

    def encolar(self, sesion, tipo, agregado, id_local, datos):
        if self.falla:
            raise RuntimeError("el outbox no anda")
        self.operaciones.append((tipo, agregado, id_local, datos))


@dataclass
class Operacion:
    """Lo que entrega el receptor de LibraEdge: sólo los cuatro campos que mira el aplicador."""

    node_id: str
    operation_type: str
    schema_version: int
    payload: dict


def como_nodo(outbox: Outbox | None = None, nodo: str | None = NODO) -> Outbox:
    outbox = outbox or Outbox()
    atencion.configurar(atencion.AtencionesEnNodo(nodo=lambda: nodo, encolar=outbox.encolar))
    return outbox


def operacion(datos: dict, node_id: str = NODO) -> Operacion:
    return Operacion(node_id, atencion.TIPO_TURNO_ATENDIDO, atencion.SCHEMA_VERSION, datos)


def datos_de(estado: S = S.COMPLETED, **cambios) -> dict:
    """Los `datos` de un `turno.atendido` bien formado, como los arma `atender_en_nodo`."""
    datos = {
        "version": 1, "atencion_id": str(uuid.uuid4()), "turno_id": "t1", "estado": estado.value,
        "at": datetime(2026, 11, 3, 10, 40, tzinfo=AR).isoformat(), "actor": "recepcion",
        "visto": {
            "estado": "confirmed", "starts_at": INICIO.astimezone(UTC).isoformat(), "duration_seconds": 3600,
            "resource_id": "r1",
        },
        "extra": {"pagos": [{"medio": "efectivo", "monto": "15000.00"}]},
    }
    datos.update(cambios)
    return datos


def sembrar(fabrica, estado: S = S.CONFIRMED, turno: str | None = "t1", **cambios) -> None:
    with fabrica.begin() as s:
        if s.get(BranchRow, "b1") is None:
            s.add_all([
                BranchRow(id="b1", name="Sucursal"),
                ClientRow(id="c1", name="Cliente Ficticia"),
                ResourceRow(id="r1", name="Profesional", branch_id="b1"),
                ResourceRow(id="r2", name="Otro profesional", branch_id="b1"),
                ServiceRow(id="s1", name="Servicio", duration_seconds=3600),
            ])
            s.flush()
        if turno is not None:
            s.add(AppointmentRow(
                id=turno, resource_id="r1", service_id="s1", client_id="c1", starts_at=INICIO, duration_seconds=3600,
                status=estado.value, branch_id="b1", overbooked=False,
            ))
            for campo, valor in cambios.items():
                setattr(s.get(AppointmentRow, turno), campo, valor)


def web(fabrica, turno: str = "t1", **cambios) -> None:
    """Lo que alguien hizo en la web mientras el nodo estaba sin conexión."""
    with fabrica.begin() as s:
        fila = s.get(AppointmentRow, turno)
        for campo, valor in cambios.items():
            setattr(fila, campo, valor)


def aplicar(fabrica, datos: dict, **kw) -> atencion.AtencionAplicada:
    with fabrica.begin() as s:
        return atencion.aplicar_turno_atendido(s, operacion(datos), **kw)


def estado(fabrica, turno: str = "t1") -> str:
    with fabrica() as s:
        return s.get(AppointmentRow, turno).status


def transiciones(fabrica, turno: str = "t1") -> list[AppointmentTransitionRow]:
    with fabrica() as s:
        return list(s.scalars(
            select(AppointmentTransitionRow).where(AppointmentTransitionRow.appointment_id == turno)
            .order_by(AppointmentTransitionRow.id)
        ))


def cuantas(fabrica, modelo) -> int:
    with fabrica() as s:
        return s.scalar(select(func.count()).select_from(modelo))


# ── 1. El nodo ───────────────────────────────────────────────────────────────


def test_atender_deja_la_fila_propia_y_encola_en_la_misma_transaccion(base):
    sembrar(base)
    outbox = como_nodo()
    with base.begin() as s:
        hecha = atencion.atender_en_nodo(
            s, "t1", S.COMPLETED, at=datetime(2026, 11, 3, 10, 40, tzinfo=AR), actor="  recepcion ",
            extra={"pagos": [{"medio": "efectivo", "monto": "15000.00"}]},
        )

    assert hecha.estado is S.COMPLETED and hecha.orden == 1 and hecha.actor == "recepcion"
    assert cuantas(base, NodeAttendanceRow) == 1
    # El turno es una fila del espejo: el nodo NO la escribe.
    assert estado(base) == "confirmed"
    assert transiciones(base) == []

    assert len(outbox.operaciones) == 1
    tipo, agregado, id_local, datos = outbox.operaciones[0]
    assert (tipo, agregado, id_local) == ("turno.atendido", "turno", "t1")
    assert datos["version"] == 1 and datos["atencion_id"] == hecha.id and datos["turno_id"] == "t1"
    assert datos["estado"] == "completed" and datos["actor"] == "recepcion"
    # La hora viaja con zona, y el turno tal como el nodo lo veía.
    assert datetime.fromisoformat(datos["at"]) == datetime(2026, 11, 3, 13, 40, tzinfo=UTC)
    assert datos["visto"] == {
        "estado": "confirmed", "starts_at": INICIO.astimezone(UTC).isoformat(), "duration_seconds": 3600,
        "resource_id": "r1",
    }
    assert datos["extra"] == {"pagos": [{"medio": "efectivo", "monto": "15000.00"}]}


def test_si_el_outbox_falla_la_atencion_no_queda(base):
    sembrar(base)
    como_nodo(Outbox(falla=True))
    with pytest.raises(RuntimeError), base.begin() as s:
        atencion.atender_en_nodo(s, "t1", S.COMPLETED)
    assert cuantas(base, NodeAttendanceRow) == 0


def test_en_curso_y_despues_completado_con_estado_efectivo(base):
    sembrar(base)
    outbox = como_nodo()
    with base.begin() as s:
        atencion.atender_en_nodo(s, "t1", S.IN_PROGRESS)
        assert atencion.estado_efectivo(s, "t1") is S.IN_PROGRESS
    with base.begin() as s:
        segunda = atencion.atender_en_nodo(s, "t1", S.COMPLETED, extra={"pagos": []})
    assert segunda.orden == 2
    with base() as s:
        assert atencion.estado_efectivo(s, "t1") is S.COMPLETED
        assert s.get(AppointmentRow, "t1").status == "confirmed"        # el espejo sigue como vino
        ultimas = atencion.atenciones_del_nodo(s)
    assert [o[3]["estado"] for o in outbox.operaciones] == ["in_progress", "completed"]
    assert ultimas["t1"].estado is S.COMPLETED and ultimas["t1"].orden == 2


@pytest.mark.parametrize(("origen", "pedido"), [
    (S.PENDING, S.COMPLETED),        # sin confirmar no se atiende
    (S.CANCELLED, S.COMPLETED),
    (S.COMPLETED, S.NO_SHOW),
    (S.NO_SHOW, S.COMPLETED),
    (S.IN_PROGRESS, S.NO_SHOW),      # empezó: ya no es «no vino»
    (S.IN_PROGRESS, S.IN_PROGRESS),
])
def test_las_reglas_de_estado_son_las_de_libragenda(base, origen, pedido):
    sembrar(base, estado=origen)
    outbox = como_nodo()
    with pytest.raises(InvalidTransition), base.begin() as s:
        atencion.atender_en_nodo(s, "t1", pedido)
    assert cuantas(base, NodeAttendanceRow) == 0 and outbox.operaciones == []


def test_no_vino_se_carga_sin_conexion(base):
    sembrar(base)
    outbox = como_nodo()
    with base.begin() as s:
        atencion.atender_en_nodo(s, "t1", S.NO_SHOW)
    assert outbox.operaciones[0][3]["estado"] == "no_show"
    with base.begin() as s, pytest.raises(InvalidTransition):
        atencion.atender_en_nodo(s, "t1", S.COMPLETED)           # ya quedó «no vino» en el nodo


def test_el_estado_efectivo_cuenta_las_atenciones_del_nodo_no_solo_el_espejo(base):
    sembrar(base)
    como_nodo()
    with base.begin() as s:
        atencion.atender_en_nodo(s, "t1", S.COMPLETED)
    with base.begin() as s, pytest.raises(InvalidTransition):
        atencion.atender_en_nodo(s, "t1", S.IN_PROGRESS)         # el espejo dice confirmed, pero el nodo lo completó


def test_desde_un_nodo_no_se_cancela_ni_se_confirma(base):
    sembrar(base)
    como_nodo()
    for pedido in (S.CANCELLED, S.CONFIRMED, S.PENDING):
        with base.begin() as s, pytest.raises(atencion.EstadoNoAtendible):
            atencion.atender_en_nodo(s, "t1", pedido)


def test_fuera_de_un_nodo_se_niega(base):
    sembrar(base)
    with base.begin() as s, pytest.raises(atencion.NoEsUnNodo):       # sin configurar
        atencion.atender_en_nodo(s, "t1", S.COMPLETED)
    como_nodo(nodo=None)                                              # configurada, pero el central
    assert not atencion.en_un_nodo()
    with base.begin() as s, pytest.raises(atencion.NoEsUnNodo):
        atencion.atender_en_nodo(s, "t1", S.COMPLETED)


def test_entradas_invalidas(base):
    sembrar(base)
    como_nodo()
    with base.begin() as s:
        with pytest.raises(AppointmentNotFound):
            atencion.atender_en_nodo(s, "no-existe", S.COMPLETED)
        with pytest.raises(ValueError, match="zona"):
            atencion.atender_en_nodo(s, "t1", S.COMPLETED, at=datetime(2026, 11, 3, 10, 40))
        with pytest.raises(ValueError, match="serializable"):
            atencion.atender_en_nodo(s, "t1", S.COMPLETED, extra={"monto": object()})
        with pytest.raises(TypeError):
            atencion.atender_en_nodo(s, "t1", S.COMPLETED, extra=["no", "es", "dict"])
    assert cuantas(base, NodeAttendanceRow) == 0


def test_dos_pestanas_a_la_vez_la_segunda_se_rechaza_sin_romper_la_transaccion(base, monkeypatch):
    sembrar(base)
    como_nodo()
    with base.begin() as s:
        atencion.atender_en_nodo(s, "t1", S.IN_PROGRESS)           # la otra pestaña, ya commiteada
    # La segunda pestaña leyó antes de que la primera commiteara: no vio ninguna atención y le toca `orden = 1`.
    monkeypatch.setattr(atencion, "_ultima_del_nodo", lambda sesion, turno: None)
    with base.begin() as s:
        with pytest.raises(InvalidTransition, match="a la vez"):
            atencion.atender_en_nodo(s, "t1", S.COMPLETED)
        assert s.scalar(select(func.count()).select_from(NodeAttendanceRow)) == 1     # la transacción sigue viva
    assert cuantas(base, NodeAttendanceRow) == 1


def test_atenciones_del_nodo_con_lista_vacia_y_filtro(base):
    sembrar(base)
    sembrar(base, turno="t2")
    como_nodo()
    with base.begin() as s:
        atencion.atender_en_nodo(s, "t1", S.COMPLETED)
    with base() as s:
        assert atencion.atenciones_del_nodo(s, []) == {}
        assert set(atencion.atenciones_del_nodo(s, ["t1", "t2"])) == {"t1"}
        assert atencion.atenciones_del_nodo(s, ["t2"]) == {}


def test_encolar_en_nodo_es_la_costura_para_lo_propio_del_producto(base):
    sembrar(base)
    with base.begin() as s:                                            # sin configurar: no hace nada
        assert atencion.encolar_en_nodo(s, "walkin.registrado", "walkin", "w1", {"x": 1}) is False
    como_nodo(nodo=None)
    with base.begin() as s:                                            # el central: tampoco
        assert atencion.encolar_en_nodo(s, "walkin.registrado", "walkin", "w1", {"x": 1}) is False
    outbox = como_nodo()
    with base.begin() as s:
        assert atencion.encolar_en_nodo(s, "walkin.registrado", "walkin", "w1", {"x": 1}) is True
    assert outbox.operaciones == [("walkin.registrado", "walkin", "w1", {"x": 1})]


def test_configurar_exige_el_tipo():
    with pytest.raises(TypeError):
        atencion.configurar(object())                                  # type: ignore[arg-type]


# ── 2. El central, camino normal ─────────────────────────────────────────────


def test_la_transicion_normal_cambia_el_turno_con_la_hora_del_nodo(base):
    sembrar(base)
    hooks = []
    datos = datos_de(S.COMPLETED)
    hecha = aplicar(base, datos, al_aplicar=lambda s, a: hooks.append(a))

    assert hecha.resultado == "aplicada" and hecha.motivo is None and not hecha.a_revisar and not hecha.repetida
    assert hecha.estado_antes is S.CONFIRMED and hecha.estado_despues is S.COMPLETED
    assert estado(base) == "completed"
    (transicion,) = transiciones(base)
    assert (transicion.from_status, transicion.to_status, transicion.actor) == ("confirmed", "completed", "recepcion")
    assert transicion.at == datetime.fromisoformat(datos["at"]).astimezone(UTC)       # la hora del nodo, no la de ahora
    assert NODO in transicion.reason
    assert [h.extra for h in hooks] == [datos["extra"]]
    assert cuantas(base, AppliedAttendanceRow) == 1


@pytest.mark.parametrize(("origen", "pedido"), [
    (S.CONFIRMED, S.IN_PROGRESS), (S.CONFIRMED, S.COMPLETED), (S.CONFIRMED, S.NO_SHOW), (S.IN_PROGRESS, S.COMPLETED),
])
def test_cada_transicion_valida_se_aplica(base, origen, pedido):
    sembrar(base, estado=origen)
    hecha = aplicar(base, datos_de(pedido, visto={**datos_de()["visto"], "estado": origen.value}))
    assert hecha.resultado == "aplicada" and estado(base) == pedido.value


def test_en_curso_y_completado_en_orden_dejan_las_dos_transiciones(base):
    sembrar(base)
    uno = aplicar(base, datos_de(S.IN_PROGRESS, at=datetime(2026, 11, 3, 10, 5, tzinfo=AR).isoformat()))
    dos = aplicar(base, datos_de(S.COMPLETED))
    assert (uno.resultado, dos.resultado) == ("aplicada", "aplicada")
    assert estado(base) == "completed"
    assert [(t.from_status, t.to_status) for t in transiciones(base)] == [
        ("confirmed", "in_progress"), ("in_progress", "completed")]


def test_sin_visto_no_se_puede_decir_que_se_movio(base):
    sembrar(base, starts_at=INICIO + timedelta(days=1))
    assert aplicar(base, datos_de(S.COMPLETED, visto=None)).resultado == "aplicada"


# ── 3. Idempotencia ──────────────────────────────────────────────────────────


def test_la_misma_operacion_dos_veces_es_un_solo_efecto(base):
    sembrar(base)
    hooks = []
    datos = datos_de(S.COMPLETED)
    primera = aplicar(base, datos, al_aplicar=lambda s, a: hooks.append(a))
    segunda = aplicar(base, datos, al_aplicar=lambda s, a: hooks.append(a))
    tercera = aplicar(base, dict(datos), al_aplicar=lambda s, a: hooks.append(a))

    assert (primera.repetida, segunda.repetida, tercera.repetida) == (False, True, True)
    assert segunda.resultado == primera.resultado == "aplicada"
    assert (segunda.estado_antes, segunda.estado_despues) == (S.CONFIRMED, S.COMPLETED)   # lo que pasó la primera vez
    assert len(hooks) == 1                                    # el hook (el cobro, el envío) corre una sola vez
    assert len(transiciones(base)) == 1 and cuantas(base, AppliedAttendanceRow) == 1


def test_repetir_una_operacion_a_revisar_tampoco_duplica(base):
    sembrar(base, estado=S.CANCELLED)
    hooks = []
    datos = datos_de(S.COMPLETED)
    aplicar(base, datos, al_aplicar=lambda s, a: hooks.append(a))
    otra = aplicar(base, datos, al_aplicar=lambda s, a: hooks.append(a))
    assert otra.repetida and otra.motivo == "cancelado"
    assert len(hooks) == 1 and cuantas(base, AppliedAttendanceRow) == 1


def test_el_mismo_atencion_id_con_otro_contenido_no_se_pisa(base):
    sembrar(base)
    datos = datos_de(S.IN_PROGRESS)
    aplicar(base, datos)
    with pytest.raises(atencion.AtencionInvalida, match="otro contenido"), base.begin() as s:
        atencion.aplicar_turno_atendido(s, operacion({**datos, "estado": "completed"}))
    assert estado(base) == "in_progress" and cuantas(base, AppliedAttendanceRow) == 1


def test_dos_entregas_a_la_vez_un_solo_efecto(nueva_base):
    """Sólo PostgreSQL: SQLite serializa las escrituras sola. La segunda espera el turno, la primera commitea y la
    segunda choca con la clave de la atención y devuelve lo anotado."""
    if nueva_base.motor != "postgresql":
        pytest.skip("la carrera necesita trabas de fila")
    _, fabrica = nueva_base()
    sembrar(fabrica)
    datos = datos_de(S.COMPLETED)
    hooks, resultados = [], {}
    aplicada, permiso = threading.Event(), threading.Event()

    def primera():
        with fabrica.begin() as s:
            resultados["a"] = atencion.aplicar_turno_atendido(
                s, operacion(datos), al_aplicar=lambda ses, a: hooks.append("a"))
            aplicada.set()
            assert permiso.wait(20)                 # sostiene la transacción abierta con el turno trabado

    def segunda():
        with fabrica.begin() as s:
            resultados["b"] = atencion.aplicar_turno_atendido(
                s, operacion(datos), al_aplicar=lambda ses, a: hooks.append("b"))

    hilo_a = threading.Thread(target=primera)
    hilo_a.start()
    assert aplicada.wait(20)
    hilo_b = threading.Thread(target=segunda)
    hilo_b.start()
    hilo_b.join(1.0)
    assert hilo_b.is_alive(), "la segunda tendría que estar esperando el candado del turno"
    permiso.set()
    hilo_a.join(20)
    hilo_b.join(20)

    assert not resultados["a"].repetida and resultados["b"].repetida
    assert hooks == ["a"]
    assert len(transiciones(fabrica)) == 1 and cuantas(fabrica, AppliedAttendanceRow) == 1
    assert estado(fabrica) == "completed"


# ── 4. Cada conflicto con la web: la atención igual vale ─────────────────────


def test_cancelado_en_la_web_la_atencion_vale_y_el_turno_va_a_revisar(base):
    sembrar(base, estado=S.CANCELLED)
    hooks = []
    datos = datos_de(S.COMPLETED)
    hecha = aplicar(base, datos, al_aplicar=lambda s, a: hooks.append(a))

    assert hecha.resultado == "a_revisar" and hecha.motivo == "cancelado" and hecha.a_revisar
    assert "cancelado" in hecha.detalle
    assert estado(base) == "cancelled"                         # cancelado es terminal: no se resucita solo
    assert transiciones(base) == []
    # La atención quedó anotada entera, con lo cobrado, y el producto la recibió.
    with base() as s:
        fila = s.get(AppliedAttendanceRow, datos["atencion_id"])
        assert (fila.status, fila.actor, fila.extra) == ("completed", "recepcion", datos["extra"])
        assert datetime.fromisoformat(datos["at"]) == fila.at
    assert [h.extra for h in hooks] == [datos["extra"]] and hooks[0].a_revisar


@pytest.mark.parametrize(("cambio", "lo_que_dice"), [
    ({"starts_at": INICIO + timedelta(days=2)}, "empezaba"),
    ({"resource_id": "r2"}, "recurso"),
    ({"duration_seconds": 5400}, "duraba"),
])
def test_movido_en_la_web_la_atencion_se_aplica_y_el_turno_va_a_revisar(base, cambio, lo_que_dice):
    sembrar(base)
    web(base, **cambio)
    hooks = []
    hecha = aplicar(base, datos_de(S.COMPLETED), al_aplicar=lambda s, a: hooks.append(a))

    assert hecha.resultado == "a_revisar" and hecha.motivo == "movido" and lo_que_dice in hecha.detalle
    assert estado(base) == "completed"                         # la atención vale: el turno movido queda completado
    assert hecha.estado_antes is S.CONFIRMED and hecha.estado_despues is S.COMPLETED
    assert len(transiciones(base)) == 1 and len(hooks) == 1


def test_el_mismo_instante_en_otra_zona_no_es_un_movimiento(base):
    sembrar(base)
    visto = {**datos_de()["visto"], "starts_at": INICIO.isoformat()}          # -03:00, el mismo instante que UTC
    assert aplicar(base, datos_de(S.COMPLETED, visto=visto)).resultado == "aplicada"


@pytest.mark.parametrize(("en_la_web", "pedido", "mismo"), [
    (S.COMPLETED, S.COMPLETED, True),       # los dos lo completaron: puede haberse cobrado dos veces
    (S.COMPLETED, S.NO_SHOW, False),
    (S.NO_SHOW, S.COMPLETED, False),
    (S.IN_PROGRESS, S.NO_SHOW, False),
    (S.IN_PROGRESS, S.IN_PROGRESS, True),
])
def test_ya_atendido_distinto_la_atencion_vale_y_va_a_revisar(base, en_la_web, pedido, mismo):
    sembrar(base, estado=en_la_web)
    hooks = []
    hecha = aplicar(base, datos_de(pedido), al_aplicar=lambda s, a: hooks.append(a))

    assert hecha.resultado == "a_revisar" and hecha.motivo == "ya_atendido"
    assert ("(el mismo)" in hecha.detalle) is mismo
    assert estado(base) == en_la_web.value and transiciones(base) == []
    assert len(hooks) == 1                                     # lo cobrado en el mostrador llega al producto igual


def test_la_web_lo_empezo_y_el_nodo_lo_completa_no_es_conflicto(base):
    sembrar(base, estado=S.IN_PROGRESS)
    hecha = aplicar(base, datos_de(S.COMPLETED))               # el nodo lo veía confirmed; la transición es válida
    assert hecha.resultado == "aplicada" and estado(base) == "completed"


def test_sin_confirmar_en_el_central_es_transicion_invalida(base):
    sembrar(base, estado=S.PENDING)
    hecha = aplicar(base, datos_de(S.COMPLETED))
    assert hecha.resultado == "a_revisar" and hecha.motivo == "transicion_invalida"
    assert estado(base) == "pending"


def test_turno_inexistente_la_atencion_queda_anotada(base):
    sembrar(base, turno=None)
    hooks = []
    datos = datos_de(S.COMPLETED, turno_id="borrado")
    hecha = aplicar(base, datos, al_aplicar=lambda s, a: hooks.append(a))
    assert hecha.motivo == "turno_inexistente" and hecha.estado_antes is None and hecha.estado_despues is None
    assert len(hooks) == 1 and cuantas(base, AppliedAttendanceRow) == 1
    assert aplicar(base, datos).repetida


def test_cancelado_en_la_web_y_dos_atenciones_del_nodo_quedan_las_dos_a_revisar(base):
    sembrar(base, estado=S.CANCELLED)
    aplicar(base, datos_de(S.IN_PROGRESS))
    aplicar(base, datos_de(S.COMPLETED))
    with base() as s:
        pendientes = atencion.turnos_a_revisar(s)
    assert {(p.estado, p.motivo) for p in pendientes} == {(S.IN_PROGRESS, "cancelado"), (S.COMPLETED, "cancelado")}
    assert len(pendientes) == 2


def test_si_el_hook_falla_no_queda_nada_y_se_puede_reintentar(base):
    sembrar(base)
    datos = datos_de(S.COMPLETED)

    def roto(sesion, atencion_):
        raise RuntimeError("ContaLibra no contesta")

    with pytest.raises(RuntimeError):
        aplicar(base, datos, al_aplicar=roto)
    assert estado(base) == "confirmed" and cuantas(base, AppliedAttendanceRow) == 0 and transiciones(base) == []
    hecha = aplicar(base, datos)                                # el receptor reintenta la misma operación
    assert hecha.resultado == "aplicada" and estado(base) == "completed"


# ── 5. La lista «a revisar» ──────────────────────────────────────────────────


def test_turnos_a_revisar_y_marcar_revisada(base):
    sembrar(base, estado=S.CANCELLED)
    sembrar(base, turno="t2")
    sembrar(base, turno="t3")
    web(base, "t3", starts_at=INICIO + timedelta(hours=5))
    primera = datos_de(S.COMPLETED, at=datetime(2026, 11, 3, 10, 40, tzinfo=AR).isoformat())
    aplicar(base, primera)
    aplicar(base, datos_de(S.COMPLETED, turno_id="t2"))                              # sin conflicto: no está en la lista
    aplicar(base, datos_de(S.NO_SHOW, turno_id="t3", at=datetime(2026, 11, 3, 11, 0, tzinfo=AR).isoformat()))

    with base() as s:
        lista = atencion.turnos_a_revisar(s)
        assert [(a.appointment_id, a.motivo) for a in lista] == [("t1", "cancelado"), ("t3", "movido")]
        assert [a.appointment_id for a in atencion.turnos_a_revisar(s, appointment_id="t3")] == ["t3"]

    with base.begin() as s:
        hecha = atencion.marcar_revisada(
            s, primera["atencion_id"], por="admin", nota="la clienta vino igual, se cobró",
            at=datetime(2026, 11, 4, 9, 0, tzinfo=UTC),
        )
    assert not hecha.a_revisar and hecha.revisada_por == "admin" and hecha.nota_revision.startswith("la clienta")

    with base.begin() as s:
        otra = atencion.marcar_revisada(s, primera["atencion_id"], por="otro", nota="pisa?")   # no pisa la primera
    assert otra.revisada_por == "admin" and otra.nota_revision.startswith("la clienta")
    with base() as s:
        assert [a.appointment_id for a in atencion.turnos_a_revisar(s)] == ["t3"]
        todas = atencion.turnos_a_revisar(s, incluir_revisadas=True)
        assert [a.appointment_id for a in todas] == ["t1", "t3"]
        # La atención revisada sigue registrada, entera.
        assert s.get(AppliedAttendanceRow, primera["atencion_id"]).extra == primera["extra"]


def test_marcar_revisada_de_una_aplicada_no_hace_nada_y_de_una_que_no_existe_falla(base):
    sembrar(base)
    limpia = datos_de(S.COMPLETED)
    aplicar(base, limpia)
    with base.begin() as s:
        hecha = atencion.marcar_revisada(s, limpia["atencion_id"], por="admin")
        assert hecha.revisada_at is None and hecha.resultado == "aplicada"
        with pytest.raises(atencion.AtencionNotFound):
            atencion.marcar_revisada(s, "no-existe")


# ── 6. La validación y el despachador ────────────────────────────────────────


@pytest.mark.parametrize(("arma", "dice"), [
    (lambda: Operacion(NODO, "turno.otra", 1, datos_de()), "se esperaba"),
    (lambda: Operacion(NODO, atencion.TIPO_TURNO_ATENDIDO, 2, datos_de()), "schema 2"),
    (lambda: operacion({**datos_de(), "version": 2}), "versión"),
    (lambda: operacion({**datos_de(), "estado": "cancelled"}), "no se puede dar en un nodo"),
    (lambda: operacion({**datos_de(), "estado": "volando"}), "desconocido"),
    (lambda: operacion({**datos_de(), "at": "2026-11-03T10:40:00"}), "zona"),
    (lambda: operacion({**datos_de(), "at": "ayer"}), "ISO"),
    (lambda: operacion({**datos_de(), "atencion_id": ""}), "atencion_id"),
    (lambda: operacion({**datos_de(), "turno_id": None}), "turno_id"),
    (lambda: operacion({**datos_de(), "extra": ["no"]}), "extra"),
    (lambda: operacion({**datos_de(), "visto": "raro"}), "visto"),
    (lambda: operacion({**datos_de(), "visto": {"starts_at": "2026-11-03T10:00:00"}}), "zona"),
    (lambda: operacion({**datos_de(), "visto": {"duration_seconds": "1h"}}), "entero"),
    (lambda: operacion(datos_de(), node_id=""), "nodo"),
    (lambda: Operacion(NODO, atencion.TIPO_TURNO_ATENDIDO, 1, None), "versión"),     # type: ignore[arg-type]
])
def test_una_operacion_mal_formada_se_rechaza_sin_escribir_nada(base, arma, dice):
    sembrar(base)
    with pytest.raises(atencion.AtencionInvalida, match=dice), base.begin() as s:
        atencion.aplicar_turno_atendido(s, arma())
    assert isinstance(atencion.AtencionInvalida("x"), ValueError)       # el receptor la manda a revisión manual
    assert estado(base) == "confirmed" and cuantas(base, AppliedAttendanceRow) == 0


def test_registrar_en_registra_el_tipo_y_aplica_en_una_sesion_propia(nueva_base):
    url, fabrica = nueva_base()
    sembrar(fabrica)
    database.configure(url)
    try:
        class Despachador:
            def __init__(self):
                self.registrados = {}

            def registrar(self, tipo, version, manejador):
                self.registrados[(tipo, version)] = manejador

        despachador = Despachador()
        hooks = []
        assert atencion.registrar_en(despachador, al_aplicar=lambda s, a: hooks.append(a)) is despachador
        manejador = despachador.registrados[("turno.atendido", 1)]

        datos = datos_de(S.COMPLETED)
        manejador(object(), operacion(datos))
        manejador(object(), operacion(datos))                            # el outbox entrega al menos una vez
        assert estado(fabrica) == "completed" and len(hooks) == 1
        assert cuantas(fabrica, AppliedAttendanceRow) == 1
    finally:
        database.reset()


def test_abrir_sesion_propia_del_producto(base):
    sembrar(base)
    visto = []

    def abrir(conexion):
        visto.append(conexion)
        return base.begin()

    manejador = atencion.aplicadores(abrir_sesion=abrir)["turno.atendido"]
    manejador("la-conexion-del-receptor", operacion(datos_de(S.NO_SHOW)))
    assert visto == ["la-conexion-del-receptor"] and estado(base) == "no_show"


# ── 7. De punta a punta: la base del nodo y la del central ───────────────────


def test_del_nodo_al_central_aunque_la_web_cancelo_el_turno(nueva_base):
    _, nodo_db = nueva_base()
    _, central_db = nueva_base()
    sembrar(nodo_db)
    sembrar(central_db)
    outbox = como_nodo()

    # En el nodo, sin conexión: se atiende, se cobra, se marca completado.
    with nodo_db.begin() as s:
        atencion.atender_en_nodo(s, "t1", S.IN_PROGRESS, at=datetime(2026, 11, 3, 10, 5, tzinfo=AR), actor="ana")
    with nodo_db.begin() as s:
        atencion.atender_en_nodo(
            s, "t1", S.COMPLETED, at=datetime(2026, 11, 3, 10, 50, tzinfo=AR), actor="ana",
            extra={"pagos": [{"medio": "efectivo", "monto": "15000.00"}]},
        )
    # Mientras tanto, en la web: la cancelaron.
    web(central_db, status="cancelled")

    # Vuelve la conexión: el central recibe lo que el nodo encoló (con serialización, como el outbox real).
    import json
    recibidas = [json.loads(json.dumps(o[3])) for o in outbox.operaciones]
    hooks = []
    resultados = [
        aplicar(central_db, d, al_aplicar=lambda s, a: hooks.append(a)) for d in recibidas
    ]
    assert [r.motivo for r in resultados] == ["cancelado", "cancelado"]
    assert estado(central_db) == "cancelled"
    # Todo lo cobrado llegó al producto, y la entrega repetida no lo duplica.
    assert [h.extra for h in hooks][1] == {"pagos": [{"medio": "efectivo", "monto": "15000.00"}]}
    aplicar(central_db, recibidas[1], al_aplicar=lambda s, a: hooks.append(a))
    assert len(hooks) == 2
    with central_db() as s:
        assert [a.estado for a in atencion.turnos_a_revisar(s, appointment_id="t1")] == [S.IN_PROGRESS, S.COMPLETED]


def test_del_nodo_al_central_sin_cambios_en_la_web(nueva_base):
    _, nodo_db = nueva_base()
    _, central_db = nueva_base()
    sembrar(nodo_db)
    sembrar(central_db)
    outbox = como_nodo()
    with nodo_db.begin() as s:
        atencion.atender_en_nodo(s, "t1", S.NO_SHOW, at=datetime(2026, 11, 3, 10, 30, tzinfo=AR))
    (_, _, _, datos), = outbox.operaciones
    hecha = aplicar(central_db, datos)
    assert hecha.resultado == "aplicada" and estado(central_db) == "no_show"
    with central_db() as s:
        assert atencion.turnos_a_revisar(s) == []
