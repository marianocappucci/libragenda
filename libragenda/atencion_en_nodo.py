"""Atender un turno en un nodo sin conexión, y su vuelta en el central (ADR-019).

Un local sin internet también atiende (decisión del humano, 2026-10-21 y 2026-10-25): la agenda del nodo es de **sólo
consulta** —no se dan, mueven ni cancelan turnos—, pero un turno ya dado se puede marcar **en curso**, **completado** o
**«no vino»**, y lo cobrado en el mostrador cuenta. El nodo es la copia local del producto que corre en la PC del local
(LibraEdge). Lo que se atiende ahí tiene que subir al central **sin perderse**, aunque la web haya tocado el turno
mientras tanto.

## El reparto

| Dónde | Qué hay | Quién lo escribe |
|---|---|---|
| Nodo | `appointments` y el resto de la agenda: filas del **espejo**, de sólo lectura (la guarda de LibraEdge, LE001) | el espejo |
| Nodo | `agenda_node_attendances`: la **fila propia del nodo**, una por atención | `atender_en_nodo` |
| Nodo → central | la operación `turno.atendido` en el outbox del producto, en la **misma transacción** | `atender_en_nodo` |
| Central | `agenda_applied_attendances`: lo que se aplicó (idempotencia) y la lista **«a revisar»** | `aplicar_turno_atendido` |

El nodo muestra la agenda con su fila encima (`atenciones_del_nodo`, `estado_efectivo`): el turno que el espejo trae
`confirmed` y el nodo atendió se ve `completed`.

## `turno.atendido` (versión 1)

`aggregate_type = "turno"`, `aggregate_id = "<node_id>:turno:<id del turno>"`. Los `datos`:

| Campo | Qué es |
|---|---|
| `version` | 1. El central rechaza la que no entiende |
| `atencion_id` | uuid4 que genera el nodo. **Es la clave de idempotencia**: la misma operación dos veces es un solo efecto |
| `turno_id` | el id del turno (el del central: el nodo no da turnos, así que nunca es provisorio) |
| `estado` | `in_progress`, `completed` o `no_show` |
| `at` | cuándo ocurrió, ISO 8601 **con zona**. Es la hora que queda en el historial del turno |
| `actor` | quién lo atendió, como lo nombra el producto |
| `visto` | cómo veía el nodo el turno (`estado`, `starts_at`, `duration_seconds`, `resource_id`). Con eso el central sabe si lo movieron |
| `extra` | **campo libre del producto** (`dict` serializable): los pagos en GestioLibra y MedLibra, lo que el producto quiera. Libragenda lo guarda y lo devuelve, no lo mira. La plata, como texto |

## Qué hace el central (`aplicar_turno_atendido`)

Aplica la transición con **las mismas reglas de estado** que el resto del motor (`application.can_transition`) y en la
transacción de quien lo llama. **La atención siempre queda anotada**: si el turno cambió en la web, no se descarta ni se
rechaza —sube igual y el turno pasa a la lista **«a revisar»** (`turnos_a_revisar`)—.

| El turno en el central… | Qué pasa | Resultado |
|---|---|---|
| está como lo vio el nodo y la transición es válida | se aplica | `aplicada` |
| se **movió** (otra hora, otro recurso o otra duración) y la transición es válida | se aplica sobre el turno movido | `a_revisar`, motivo `movido` |
| está **cancelado** | no se toca (cancelado es terminal) | `a_revisar`, motivo `cancelado` |
| ya está **atendido** (en curso, completado o «no vino») y la transición no es válida o es la misma | no se toca | `a_revisar`, motivo `ya_atendido` |
| está en otro estado desde el que no se puede (p. ej. `pending`) | no se toca | `a_revisar`, motivo `transicion_invalida` |
| **ya no existe** | nada que tocar | `a_revisar`, motivo `turno_inexistente` |

Lo cobrado **se conserva siempre**: `extra` queda en el registro, el hook `al_aplicar` lo recibe aun cuando el turno
quedó a revisar, y la caja del producto sube por su camino.

## Lo que NO hace

- No depende de LibraEdge. El producto pasa la función que encola (`AtencionesEnNodo.encolar`), igual que LibraClub con
  sus reservas, y registra el aplicador en su despachador del central (`registrar_en`).
- No cobra, no factura, no manda nada a ningún lado: eso es del producto, con `extra` y `al_aplicar`.
- No resuelve la revisión: la pantalla es de otro PR. Acá están la lista y `marcar_revisada`.
- No da turnos ni los mueve en el nodo.

## Cómo lo cablea el producto

```python
from libragenda import atencion_en_nodo as atencion

# Nodo y central, una vez al armar la app:
atencion.configurar(atencion.AtencionesEnNodo(
    nodo=lambda: OUTBOX.nodo().node_id if OUTBOX.nodo() else None,
    encolar=encolar_en_el_outbox,      # (sesion, tipo, agregado, id_local, datos) -> None, EN la transacción de la sesión
))

# Sólo el central, al armar el despachador (el mismo donde están los de caja y clientes):
atencion.registrar_en(despachador, abrir_sesion=..., al_aplicar=mandar_a_contalibra)   # MedLibra

# En el endpoint de «atender» (en un nodo; en el central se usa el scheduler de siempre):
with session_factory.begin() as sesion:
    atencion.atender_en_nodo(sesion, turno_id, AppointmentStatus.COMPLETED, actor=usuario, extra={"pagos": [...]})
```

Sin `configurar()`, o con un `nodo()` que devuelve `None`, `en_un_nodo()` es falso y `atender_en_nodo` se niega.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .application import (
    AppointmentNotFound,
    InvalidTransition,
    ScheduleError,
    can_transition,
)
from .domain import AppointmentStatus
from .sqlalchemy_repository import (
    AppliedAttendanceRow,
    AppointmentRow,
    AppointmentTransitionRow,
    NodeAttendanceRow,
)

#: La forma de los `datos` de la operación. Si cambia, sube: el central rechaza lo que no entiende.
VERSION = 1
#: El `schema_version` de la `OutboxOperation`: el mismo que usan las operaciones de LibraClub y LibraCommerce.
SCHEMA_VERSION = 1

TIPO_TURNO_ATENDIDO = "turno.atendido"
#: El `aggregate_type` (el `aggregate_id` lo arma el outbox: `<node_id>:turno:<id>`).
AGREGADO_TURNO = "turno"

#: Los estados a los que se puede llevar un turno desde un nodo. `cancelled` y `pending`/`confirmed` no: la agenda del
#: nodo es de sólo consulta.
ESTADOS_ATENDIBLES = (
    AppointmentStatus.IN_PROGRESS,
    AppointmentStatus.COMPLETED,
    AppointmentStatus.NO_SHOW,
)

RESULTADO_APLICADA = "aplicada"
RESULTADO_A_REVISAR = "a_revisar"

MOTIVO_MOVIDO = "movido"
MOTIVO_CANCELADO = "cancelado"
MOTIVO_YA_ATENDIDO = "ya_atendido"
MOTIVO_TRANSICION_INVALIDA = "transicion_invalida"
MOTIVO_TURNO_INEXISTENTE = "turno_inexistente"
MOTIVOS = (
    MOTIVO_MOVIDO,
    MOTIVO_CANCELADO,
    MOTIVO_YA_ATENDIDO,
    MOTIVO_TRANSICION_INVALIDA,
    MOTIVO_TURNO_INEXISTENTE,
)


class NoEsUnNodo(ScheduleError):
    """Se intentó atender «en el nodo» desde una instancia que no es un nodo (el central, una instalación común)."""


class EstadoNoAtendible(ScheduleError):
    """Desde un nodo sólo se puede pasar un turno a `in_progress`, `completed` o `no_show`."""


class AtencionNotFound(ScheduleError):
    """No hay una atención aplicada con ese id."""


class AtencionInvalida(ValueError):
    """Una operación `turno.atendido` que el central no puede aplicar. Es un `ValueError` a propósito: el receptor de
    LibraEdge lo manda a revisión manual y el nodo no traba la cola (ADR-020 de LibraEdge)."""


# ── La configuración: qué es un nodo y cómo se encola ────────────────────────


@dataclass(frozen=True)
class AtencionesEnNodo:
    """Lo que LibraGenda necesita saber del nodo para atender un turno ahí. Inmutable.

    - `nodo`: el id de este nodo, o `None` si la instancia no es un nodo.
    - `encolar`: `(sesion, tipo, agregado, id_local, datos) -> None`. Corre **adentro de la transacción de la sesión**:
      si levanta, la atención no queda (una atención que no sube es plata cobrada que el central no ve). Lo normal es
      encolar en el outbox de LibraEdge con la conexión de esa misma sesión. `agregado` es `"turno"` e `id_local` el id
      del turno; el outbox arma el `aggregate_id`.
    """

    nodo: Callable[[], str | None]
    encolar: Callable[[Session, str, str, str, dict], None]


_configuracion: AtencionesEnNodo | None = None


def configurar(atenciones: AtencionesEnNodo | None) -> None:
    """Registra la `AtencionesEnNodo` del proceso (o la saca, con `None`). La llama el producto al armar la app, una
    vez. Es global y del proceso, como `reservas_nodo.configurar` de LibraClub."""
    global _configuracion
    if atenciones is not None and not isinstance(atenciones, AtencionesEnNodo):
        raise TypeError(f"se esperaba una AtencionesEnNodo, llegó {type(atenciones).__name__}")
    _configuracion = atenciones


def configuracion() -> AtencionesEnNodo | None:
    return _configuracion


def nodo_actual() -> str | None:
    """El id del nodo si esta instancia es un nodo **y** hay configuración; si no, `None`. Se lee en cada llamada."""
    if _configuracion is None:
        return None
    return _configuracion.nodo() or None


def en_un_nodo() -> bool:
    return nodo_actual() is not None


def encolar_en_nodo(sesion: Session, tipo: str, agregado: str, id_local: str, datos: Mapping[str, Any]) -> bool:
    """Encola una operación **propia del producto** por la misma costura (p. ej. la demanda espontánea de MedLibra,
    `walkin.registrado`), en la transacción de `sesion`. Devuelve si encoló: fuera de un nodo no hace nada y devuelve
    `False`, para que el producto la llame siempre sin preguntar antes."""
    if _configuracion is None or nodo_actual() is None:
        return False
    _configuracion.encolar(sesion, tipo, agregado, id_local, dict(datos))
    return True


# ── Lo que se ve ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AtencionEnNodo:
    """Una atención tomada en este nodo (una fila de `agenda_node_attendances`)."""

    id: str
    appointment_id: str
    orden: int
    estado: AppointmentStatus
    at: datetime
    actor: str | None
    visto: dict
    extra: dict | None


@dataclass(frozen=True)
class AtencionAplicada:
    """Una atención que el central aplicó (una fila de `agenda_applied_attendances`).

    `repetida` es `True` cuando la operación ya estaba aplicada y esta llamada no hizo nada (no se guarda: es el aviso
    de la llamada, no un dato de la fila).
    """

    atencion_id: str
    node_id: str
    appointment_id: str
    estado: AppointmentStatus
    at: datetime
    actor: str | None
    extra: dict | None
    resultado: str
    motivo: str | None
    detalle: str | None
    estado_antes: AppointmentStatus | None
    estado_despues: AppointmentStatus | None
    aplicada_at: datetime
    revisada_at: datetime | None = None
    revisada_por: str | None = None
    nota_revision: str | None = None
    repetida: bool = False

    @property
    def a_revisar(self) -> bool:
        """Si espera a que alguien la mire: `a_revisar` y todavía sin marcar como revisada."""
        return self.resultado == RESULTADO_A_REVISAR and self.revisada_at is None


def _atencion_aplicada(fila: AppliedAttendanceRow, *, repetida: bool = False) -> AtencionAplicada:
    return AtencionAplicada(
        atencion_id=fila.atencion_id, node_id=fila.node_id, appointment_id=fila.appointment_id,
        estado=AppointmentStatus(fila.status), at=fila.at, actor=fila.actor, extra=fila.extra,
        resultado=fila.resultado, motivo=fila.motivo, detalle=fila.detalle,
        estado_antes=AppointmentStatus(fila.status_before) if fila.status_before else None,
        estado_despues=AppointmentStatus(fila.status_after) if fila.status_after else None,
        aplicada_at=fila.applied_at, revisada_at=fila.reviewed_at, revisada_por=fila.reviewed_by,
        nota_revision=fila.review_note, repetida=repetida,
    )


def _atencion_en_nodo(fila: NodeAttendanceRow) -> AtencionEnNodo:
    return AtencionEnNodo(
        id=fila.id, appointment_id=fila.appointment_id, orden=fila.orden, estado=AppointmentStatus(fila.status),
        at=fila.at, actor=fila.actor, visto=dict(fila.seen), extra=fila.extra,
    )


# ── En el nodo ───────────────────────────────────────────────────────────────


def _ultima_del_nodo(sesion: Session, appointment_id: str) -> NodeAttendanceRow | None:
    return sesion.scalars(
        select(NodeAttendanceRow)
        .where(NodeAttendanceRow.appointment_id == appointment_id)
        .order_by(NodeAttendanceRow.orden.desc())
        .limit(1)
    ).first()


def _insertar_una_vez(sesion: Session, modelo: type, valores: dict, unicas: list[str]) -> bool:
    """Inserta una fila y dice si fue **ésta** la que la puso: `False` si ya había una con la misma clave `unicas`.

    `INSERT … ON CONFLICT DO NOTHING` y no «insertar y atrapar el `IntegrityError`» a propósito: es atómico, sin
    `SAVEPOINT`. Con `pysqlite` un `SAVEPOINT` abierto antes de la primera escritura de la transacción **la confirma al
    soltarse** (el driver no hace el `BEGIN` hasta el primer `INSERT`), y la atención quedaría escrita aunque lo que
    el producto hace después en la misma transacción falle. En PostgreSQL, si otra transacción tiene la misma clave sin
    confirmar, espera a que termine y recién ahí contesta.

    Para otro motor, sin `ON CONFLICT`, cae al camino con `SAVEPOINT`."""
    dialecto = sesion.get_bind().dialect.name
    if dialecto == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialecto == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        try:
            with sesion.begin_nested():
                sesion.add(modelo(**valores))
                sesion.flush()
        except IntegrityError:
            return False
        return True
    tabla = modelo.__table__
    sentencia = insert(tabla).values(**valores).on_conflict_do_nothing(index_elements=unicas)
    if dialecto == "postgresql":
        # Medido: con psycopg 3 el `rowcount` de este INSERT es -1. `RETURNING` sólo devuelve la fila si se insertó.
        return sesion.execute(sentencia.returning(tabla.c[unicas[0]])).first() is not None
    return sesion.execute(sentencia).rowcount == 1


def _ahora() -> datetime:
    return datetime.now(UTC)


def _iso(valor: datetime) -> str:
    return valor.isoformat()


def _extra_valido(extra: Mapping[str, Any] | None) -> dict | None:
    if extra is None:
        return None
    if not isinstance(extra, Mapping):
        raise TypeError("extra tiene que ser un diccionario")
    try:
        json.dumps(extra)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "extra tiene que ser serializable a JSON (la plata, como texto; las fechas, en ISO 8601): " + str(exc)
        ) from exc
    return dict(extra)


def atender_en_nodo(
    sesion: Session,
    appointment_id: str,
    estado: AppointmentStatus,
    *,
    at: datetime | None = None,
    actor: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> AtencionEnNodo:
    """Atiende un turno en el nodo: deja la fila propia y encola `turno.atendido`, **en la transacción de `sesion`**.

    No commitea: es de quien la llama (el endpoint del producto, junto con lo suyo: el cobro, los movimientos de caja).
    Si el encolado levanta, la atención no queda.

    Valida con las reglas de siempre (`can_transition`) contra el estado **efectivo**: el del espejo con las atenciones
    del nodo encima (en curso → completado vale; completado → «no vino», no).

    - `NoEsUnNodo` si la instancia no es un nodo. En el central un turno se atiende con el scheduler.
    - `AppointmentNotFound` si el turno no está (no se da un turno en el nodo).
    - `EstadoNoAtendible` si `estado` no es `in_progress`, `completed` o `no_show`.
    - `InvalidTransition` si el estado efectivo no permite ese paso, o si otra atención se cargó a la vez.
    """
    nodo = nodo_actual()
    if _configuracion is None or nodo is None:
        raise NoEsUnNodo("esta instancia no es un nodo: un turno se atiende con el scheduler, no con atender_en_nodo")
    estado = AppointmentStatus(estado)
    if estado not in ESTADOS_ATENDIBLES:
        raise EstadoNoAtendible(
            f"desde un nodo un turno sólo pasa a {[e.value for e in ESTADOS_ATENDIBLES]}, no a {estado.value}"
        )
    momento = at or _ahora()
    if momento.tzinfo is None:
        raise ValueError("at tiene que traer zona horaria")
    extra_ok = _extra_valido(extra)
    nombre = actor.strip() if actor and actor.strip() else None

    turno = sesion.get(AppointmentRow, appointment_id)
    if turno is None:
        raise AppointmentNotFound(appointment_id)
    ultima = _ultima_del_nodo(sesion, appointment_id)
    efectivo = AppointmentStatus(ultima.status) if ultima else AppointmentStatus(turno.status)
    if not can_transition(efectivo, estado):
        raise InvalidTransition(f"cannot transition {efectivo.value} to {estado.value}")

    visto = {
        "estado": turno.status,
        "starts_at": _iso(turno.starts_at),
        "duration_seconds": turno.duration_seconds,
        "resource_id": turno.resource_id,
    }
    valores = {
        "id": str(uuid.uuid4()), "appointment_id": appointment_id, "orden": (ultima.orden + 1) if ultima else 1,
        "status": estado.value, "at": momento, "actor": nombre, "seen": visto, "extra": extra_ok,
        "created_at": _ahora(),
    }
    # Si dos pestañas atienden a la vez, la unicidad de `orden` rechaza a la segunda sin matar la transacción.
    if not _insertar_una_vez(sesion, NodeAttendanceRow, valores, ["appointment_id", "orden"]):
        raise InvalidTransition(
            f"el turno {appointment_id} se atendió a la vez desde otro lado: recargar y volver a intentar"
        )
    fila = sesion.get(NodeAttendanceRow, valores["id"], populate_existing=True)

    _configuracion.encolar(sesion, TIPO_TURNO_ATENDIDO, AGREGADO_TURNO, appointment_id, {
        "version": VERSION,
        "atencion_id": fila.id,
        "turno_id": appointment_id,
        "estado": estado.value,
        "at": _iso(momento),
        "actor": nombre,
        "visto": visto,
        "extra": extra_ok,
    })
    return _atencion_en_nodo(fila)


def atenciones_del_nodo(sesion: Session, appointment_ids: list[str] | None = None) -> dict[str, AtencionEnNodo]:
    """La última atención del nodo de cada turno `{turno_id: atención}`, para mostrar la agenda con la fila del nodo
    encima de la del espejo. Sin `appointment_ids`, todas."""
    consulta = select(NodeAttendanceRow).order_by(NodeAttendanceRow.appointment_id, NodeAttendanceRow.orden)
    if appointment_ids is not None:
        if not appointment_ids:
            return {}
        consulta = consulta.where(NodeAttendanceRow.appointment_id.in_(appointment_ids))
    ultimas: dict[str, AtencionEnNodo] = {}
    for fila in sesion.scalars(consulta):
        ultimas[fila.appointment_id] = _atencion_en_nodo(fila)   # ordenadas por `orden`: la última pisa
    return ultimas


def estado_efectivo(sesion: Session, appointment_id: str) -> AppointmentStatus:
    """El estado con el que el nodo ve el turno: el de su última atención, o el del espejo si no hay ninguna."""
    turno = sesion.get(AppointmentRow, appointment_id)
    if turno is None:
        raise AppointmentNotFound(appointment_id)
    ultima = _ultima_del_nodo(sesion, appointment_id)
    return AppointmentStatus(ultima.status if ultima else turno.status)


# ── En el central: validar ───────────────────────────────────────────────────


def _texto(datos: Mapping, campo: str, maximo: int, *, obligatorio: bool = True) -> str | None:
    valor = datos.get(campo)
    if valor is None and not obligatorio:
        return None
    if not isinstance(valor, str) or not valor.strip() or len(valor) > maximo:
        raise AtencionInvalida(f"{campo} {valor!r} no es un texto de 1 a {maximo} caracteres")
    return valor


def _fecha(valor: Any, campo: str) -> datetime:
    try:
        fecha = datetime.fromisoformat(valor)
    except (TypeError, ValueError) as exc:
        raise AtencionInvalida(f"{campo} {valor!r} no es una fecha ISO 8601") from exc
    if fecha.tzinfo is None:
        # Sin zona se leería como UTC: la atención de las 20:00 quedaría a las 17:00.
        raise AtencionInvalida(f"{campo} {valor!r} no trae zona horaria")
    return fecha


def _datos_de_atendido(operacion) -> dict:
    """Valida la operación `turno.atendido` y devuelve sus datos con los tipos de Python."""
    if operacion.operation_type != TIPO_TURNO_ATENDIDO:
        raise AtencionInvalida(f"se esperaba {TIPO_TURNO_ATENDIDO}, llegó {operacion.operation_type!r}")
    if operacion.schema_version != SCHEMA_VERSION:
        raise AtencionInvalida(
            f"schema {operacion.schema_version} de {TIPO_TURNO_ATENDIDO} desconocido (se entiende {SCHEMA_VERSION})"
        )
    datos = operacion.payload
    version = datos.get("version") if isinstance(datos, Mapping) else None
    if version != VERSION:
        raise AtencionInvalida(
            f"versión {version!r} de los datos de {TIPO_TURNO_ATENDIDO} desconocida (se entiende {VERSION})"
        )
    if not isinstance(operacion.node_id, str) or not operacion.node_id.strip():
        raise AtencionInvalida("la operación no dice de qué nodo viene")
    try:
        estado = AppointmentStatus(datos.get("estado"))
    except ValueError as exc:
        raise AtencionInvalida(f"estado {datos.get('estado')!r} desconocido") from exc
    if estado not in ESTADOS_ATENDIBLES:
        raise AtencionInvalida(
            f"estado {estado.value!r} no se puede dar en un nodo (sólo {[e.value for e in ESTADOS_ATENDIBLES]})"
        )
    extra = datos.get("extra")
    if extra is not None and not isinstance(extra, Mapping):
        raise AtencionInvalida("extra no es un diccionario")
    visto = datos.get("visto")
    if visto is not None:
        if not isinstance(visto, Mapping):
            raise AtencionInvalida("visto no es un diccionario")
        visto = dict(visto)
        if visto.get("starts_at") is not None:
            visto["starts_at"] = _fecha(visto["starts_at"], "visto.starts_at")
        dur = visto.get("duration_seconds")
        if dur is not None and (isinstance(dur, bool) or not isinstance(dur, int)):
            raise AtencionInvalida(f"visto.duration_seconds {dur!r} no es un entero")
    return {
        "atencion_id": _texto(datos, "atencion_id", 36),
        "turno_id": _texto(datos, "turno_id", 100),
        "estado": estado,
        "at": _fecha(datos.get("at"), "at"),
        "actor": _texto(datos, "actor", 200, obligatorio=False),
        "visto": visto,
        "extra": dict(extra) if extra is not None else None,
        "node_id": operacion.node_id,
    }


# ── En el central: aplicar ───────────────────────────────────────────────────


def _cambios_de_horario(turno: AppointmentRow, visto: dict | None) -> list[str]:
    """Qué cambió del turno desde que lo vio el nodo (vacío si nada, o si el nodo no dijo cómo lo veía)."""
    if not visto:
        return []
    cambios = []
    inicio = visto.get("starts_at")
    if inicio is not None and inicio.astimezone(UTC) != turno.starts_at.astimezone(UTC):
        cambios.append(f"empezaba {inicio.isoformat()} y ahora {turno.starts_at.isoformat()}")
    if visto.get("duration_seconds") is not None and visto["duration_seconds"] != turno.duration_seconds:
        cambios.append(f"duraba {visto['duration_seconds']} s y ahora {turno.duration_seconds} s")
    if visto.get("resource_id") is not None and visto["resource_id"] != turno.resource_id:
        cambios.append(f"era del recurso {visto['resource_id']} y ahora del {turno.resource_id}")
    return cambios


def _decidir(turno: AppointmentRow | None, datos: dict) -> tuple[bool, str | None, str | None]:
    """`(aplicar, motivo, detalle)`. Con motivo la atención queda a revisar; `aplicar` dice si además se hace la
    transición. Sin motivo y sin aplicar no existe."""
    pedido: AppointmentStatus = datos["estado"]
    if turno is None:
        return False, MOTIVO_TURNO_INEXISTENTE, f"el turno {datos['turno_id']} ya no existe en el central"
    actual = AppointmentStatus(turno.status)
    visto_estado = (datos["visto"] or {}).get("estado")
    if can_transition(actual, pedido):
        cambios = _cambios_de_horario(turno, datos["visto"])
        if cambios:
            return True, MOTIVO_MOVIDO, "el turno se movió en la web mientras tanto: " + "; ".join(cambios)
        return True, None, None
    if actual is AppointmentStatus.CANCELLED:
        return False, MOTIVO_CANCELADO, (
            f"el nodo lo atendió ({pedido.value}) pero en la web está cancelado (el nodo lo veía {visto_estado})"
        )
    if actual in ESTADOS_ATENDIBLES:
        igual = "" if actual is not pedido else " (el mismo)"
        return False, MOTIVO_YA_ATENDIDO, (
            f"el nodo lo marcó {pedido.value} pero en el central ya está {actual.value}{igual}: puede haberse "
            "atendido y cobrado dos veces"
        )
    return False, MOTIVO_TRANSICION_INVALIDA, (
        f"el nodo lo marcó {pedido.value} pero en el central está {actual.value}, desde donde no se puede"
    )


def aplicar_turno_atendido(
    sesion: Session,
    operacion,
    *,
    al_aplicar: Callable[[Session, AtencionAplicada], None] | None = None,
) -> AtencionAplicada:
    """Aplica `turno.atendido` en el central, en la transacción de `sesion` (no commitea). **Idempotente**.

    `operacion` es lo que entrega el receptor de LibraEdge (`node_id`, `operation_type`, `schema_version`, `payload`);
    no se importa nada de LibraEdge. Devuelve la `AtencionAplicada`:

    - la misma `atencion_id` otra vez no hace nada (ni cambia el turno, ni llama a `al_aplicar`) y devuelve la ya
      anotada con `repetida=True`;
    - si la transición es válida, el turno cambia de estado y el historial del turno queda con la hora **del nodo**;
    - si el turno cambió en la web, **la atención igual queda** y se marca `a_revisar` con su motivo (ver el docstring
      del módulo); el turno cambia sólo si la transición es válida.

    `al_aplicar(sesion, atencion)` corre en la misma transacción, **sólo la primera vez**, y también cuando quedó a
    revisar: ahí el producto hace lo suyo con `atencion.extra` (MedLibra manda la consulta a ContaLibra). Si levanta, no
    queda nada y la operación se reintenta.

    `AtencionInvalida` (un `ValueError`) si la operación no se entiende o reusa un `atencion_id` con otro contenido.
    """
    datos = _datos_de_atendido(operacion)
    atencion_id = datos["atencion_id"]

    def repetida() -> AtencionAplicada | None:
        previa = sesion.get(AppliedAttendanceRow, atencion_id, populate_existing=True)
        if previa is None:
            return None
        if (previa.node_id, previa.appointment_id, previa.status) != (
            datos["node_id"], datos["turno_id"], datos["estado"].value
        ):
            raise AtencionInvalida(
                f"el atencion_id {atencion_id} ya se aplicó con otro contenido (nodo {previa.node_id}, turno "
                f"{previa.appointment_id}, estado {previa.status}): no se pisa. Revisar a mano"
            )
        return _atencion_aplicada(previa, repetida=True)

    if (ya := repetida()) is not None:
        return ya

    # El turno se traba antes de mirarlo: una transición hecha en la web a la vez espera a ésta (o al revés), en vez de
    # pisarse. En SQLite `FOR UPDATE` no existe y se omite.
    turno = sesion.get(AppointmentRow, datos["turno_id"], with_for_update=True, populate_existing=True)
    aplicar, motivo, detalle = _decidir(turno, datos)
    antes = AppointmentStatus(turno.status) if turno is not None else None
    despues = datos["estado"] if aplicar else antes

    valores = {
        "atencion_id": atencion_id, "node_id": datos["node_id"], "appointment_id": datos["turno_id"],
        "status": datos["estado"].value, "at": datos["at"], "actor": datos["actor"], "extra": datos["extra"],
        "resultado": RESULTADO_A_REVISAR if motivo else RESULTADO_APLICADA, "motivo": motivo, "detalle": detalle,
        "status_before": antes.value if antes else None, "status_after": despues.value if despues else None,
        "applied_at": _ahora(),
    }
    # La clave es el id de la atención: dos entregas a la vez no pueden anotar las dos. La segunda espera a la primera
    # (PostgreSQL) y recibe `False`; no llegó a tocar el turno, que se cambia recién abajo.
    if not _insertar_una_vez(sesion, AppliedAttendanceRow, valores, ["atencion_id"]):
        if (ya := repetida()) is not None:
            return ya
        raise AtencionInvalida(f"no se pudo anotar la atención {atencion_id}")
    fila = sesion.get(AppliedAttendanceRow, atencion_id, populate_existing=True)

    if aplicar:
        turno.status = datos["estado"].value
        sesion.add(AppointmentTransitionRow(
            appointment_id=turno.id, from_status=antes.value, to_status=datos["estado"].value, at=datos["at"],
            actor=datos["actor"], reason=f"atendido sin conexión en el nodo {datos['node_id']}",
        ))
        sesion.flush()
    resultado = _atencion_aplicada(fila)
    if al_aplicar is not None:
        al_aplicar(sesion, resultado)
    return resultado


# ── En el central: la lista «a revisar» ──────────────────────────────────────


def turnos_a_revisar(
    sesion: Session,
    *,
    incluir_revisadas: bool = False,
    appointment_id: str | None = None,
) -> list[AtencionAplicada]:
    """Las atenciones de nodo que chocaron con un cambio de la web, de la más vieja a la más nueva.

    Sin `incluir_revisadas`, sólo las que esperan (`revisada_at` vacío). Es **una fila por atención**: un turno que el
    nodo marcó en curso y completado tiene dos; la pantalla puede agruparlas por `appointment_id`. Sirve en las dos
    puntas: la tabla baja al nodo como cualquier otra del espejo."""
    consulta = (
        select(AppliedAttendanceRow)
        .where(AppliedAttendanceRow.resultado == RESULTADO_A_REVISAR)
        .order_by(AppliedAttendanceRow.at, AppliedAttendanceRow.atencion_id)
    )
    if not incluir_revisadas:
        consulta = consulta.where(AppliedAttendanceRow.reviewed_at.is_(None))
    if appointment_id is not None:
        consulta = consulta.where(AppliedAttendanceRow.appointment_id == appointment_id)
    return [_atencion_aplicada(fila) for fila in sesion.scalars(consulta)]


def marcar_revisada(
    sesion: Session,
    atencion_id: str,
    *,
    por: str | None = None,
    nota: str | None = None,
    at: datetime | None = None,
) -> AtencionAplicada:
    """Saca una atención de la lista «a revisar» (queda registrada, con quién y cuándo). Es del central: en el nodo la
    tabla es del espejo y la guarda la rechaza. No cambia el turno ni la atención: acomodar el turno se hace con el
    scheduler, a mano. Marcar dos veces no pisa la primera. No commitea."""
    fila = sesion.get(AppliedAttendanceRow, atencion_id, with_for_update=True, populate_existing=True)
    if fila is None:
        raise AtencionNotFound(atencion_id)
    if fila.resultado == RESULTADO_A_REVISAR and fila.reviewed_at is None:
        fila.reviewed_at = at or _ahora()
        fila.reviewed_by = por.strip() if por and por.strip() else None
        fila.review_note = nota
        sesion.flush()
    return _atencion_aplicada(fila)


# ── En el central: el despachador ────────────────────────────────────────────


def _sesion_propia(conexion) -> AbstractContextManager[Session]:
    """Por defecto, una sesión de `libragenda.database` con su propia transacción: se confirma sola al salir."""
    from .database import get_session_factory

    return get_session_factory().begin()


def aplicadores(
    abrir_sesion: Callable[[Any], AbstractContextManager[Session]] | None = None,
    al_aplicar: Callable[[Session, AtencionAplicada], None] | None = None,
) -> dict[str, Callable[[Any, Any], None]]:
    """`{operation_type: (conexion, operacion) -> None}` para el despachador del central.

    `abrir_sesion(conexion)` devuelve el context manager de la sesión donde se aplica y **confirma al salir**. Por
    defecto (`None`) se abre una propia con `libragenda.database` y se ignora la conexión del receptor: la operación
    se confirma en su propia transacción. Eso es seguro **porque el aplicador es idempotente**: si el receptor falla
    después, la entrega se repite y no hace nada. Un producto que quiera todo en la transacción del receptor pasa su
    propio `abrir_sesion` (sobre esa misma conexión)."""
    abrir = abrir_sesion or _sesion_propia

    def manejador(conexion, operacion) -> None:
        with abrir(conexion) as sesion:
            aplicar_turno_atendido(sesion, operacion, al_aplicar=al_aplicar)

    return {TIPO_TURNO_ATENDIDO: manejador}


def registrar_en(
    despachador,
    abrir_sesion: Callable[[Any], AbstractContextManager[Session]] | None = None,
    al_aplicar: Callable[[Session, AtencionAplicada], None] | None = None,
):
    """Registra `turno.atendido` en un `libraedge.sync.despacho.Despachador` (el mismo donde el producto registró los
    de caja, clientes y reservas) y lo devuelve. Registrar dos veces el tipo falla al arrancar (regla del
    `Despachador`). No se importa nada de LibraEdge: el despachador se recibe."""
    for tipo, manejador in aplicadores(abrir_sesion, al_aplicar).items():
        despachador.registrar(tipo, SCHEMA_VERSION, manejador)
    return despachador
