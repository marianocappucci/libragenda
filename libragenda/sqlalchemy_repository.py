"""SQLAlchemy persistence adapter for appointments."""

from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import (
    Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, TypeDecorator,
    UniqueConstraint, create_engine, select,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker,
)

from .domain import Appointment, AppointmentStatus, AppointmentTransition


class Base(DeclarativeBase):
    pass


def ensure_utc(value: datetime) -> datetime:
    """Normalize a `DateTime(timezone=True)` column value read back as naive.

    SQLite has no native timestamptz type, so SQLAlchemy round-trips
    `DateTime(timezone=True)` values as naive on that backend while
    PostgreSQL correctly returns them timezone-aware — the same stored
    instant, two different dialect behaviors. Every row->domain conversion
    for such a column must call this so callers get a consistent aware
    datetime regardless of which database is behind the repository.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class UtcDateTime(TypeDecorator):
    """`DateTime(timezone=True)` que guarda SIEMPRE el instante en UTC.

    🔴 **El motivo, medido el 2026-08-09 contra los dos motores.** Sin esto,
    escribir un turno a las `09:00-03:00` -- o sea las 12:00 UTC -- guardaba
    **instantes distintos** segun el backend:

    | Motor | Vuelve | Instante |
    |---|---|---|
    | PostgreSQL | `12:00+00:00` | correcto |
    | SQLite | `09:00` naive, y `ensure_utc` le pone UTC encima | `09:00+00:00`, **corrido 3 horas** |

    SQLite no tiene tipo con zona: SQLAlchemy le pasa el datetime tal cual y
    se pierde el offset, con lo que queda guardada la hora de pared en vez del
    instante. `ensure_utc` es correcto **al leer** -- un valor naive que salio
    de esta columna esta en UTC -- pero no puede reparar un valor que se
    guardo mal, porque para entonces el offset ya no existe.

    Por eso la normalizacion va **al escribir**, y a nivel del tipo: son cinco
    columnas en tres modulos, y hacerlo en cada call site deja fuera al
    proximo que se agregue. `Appointment` no normaliza `starts_at` -- valida
    ids y duracion y nada mas --, asi que lo que manda el llamador llega
    intacto hasta aca.

    Un datetime **naive** se toma como UTC, que es lo que ya hacian los dos
    motores antes de este tipo: es el unico caso donde coincidian, y cambiarlo
    moveria datos existentes.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return ensure_utc(value)


class BranchRow(Base):
    __tablename__ = "branches"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(default=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")


class HolidayRow(Base):
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(200))


class ClientRow(Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    active: Mapped[bool] = mapped_column(default=True)


class ResourceRow(Base):
    __tablename__ = "resources"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(default=True)


class ServiceRow(Base):
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(default=True)


class AvailabilityRow(Base):
    __tablename__ = "availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class AgendaPolicyRow(Base):
    __tablename__ = "agenda_policies"

    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), primary_key=True)
    slot_interval_seconds: Mapped[int] = mapped_column(Integer, default=0)
    max_overbookings_per_day: Mapped[int] = mapped_column(Integer, default=0)


class TimeBlockRow(Base):
    __tablename__ = "time_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(UtcDateTime())
    ends_at: Mapped[datetime] = mapped_column(UtcDateTime())
    reason: Mapped[str] = mapped_column(Text, default="")


class AvailabilityExceptionRow(Base):
    __tablename__ = "availability_exceptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    available: Mapped[bool] = mapped_column(default=False)


class AppointmentRow(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), index=True)
    branch_id: Mapped[str | None] = mapped_column(
        ForeignKey("branches.id"), nullable=True, index=True
    )
    series_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    overbooked: Mapped[bool] = mapped_column(default=False)
    secondary_resources: Mapped[list["AppointmentResourceRow"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="AppointmentResourceRow.position",
    )


class AppointmentResourceRow(Base):
    """Extra resources one appointment occupies, beyond its primary one.

    A join table rather than a column because the relation is plural by
    nature; `position` exists only so the tuple round-trips in the order the
    caller wrote it.
    """

    __tablename__ = "appointment_resources"
    __table_args__ = (UniqueConstraint("appointment_id", "resource_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    appointment_id: Mapped[str] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), index=True
    )
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class AppointmentTransitionRow(Base):
    __tablename__ = "appointment_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    appointment_id: Mapped[str] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), index=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    actor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class SentReminderRow(Base):
    __tablename__ = "sent_reminders"
    __table_args__ = (UniqueConstraint("appointment_id", "policy_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    appointment_id: Mapped[str] = mapped_column(ForeignKey("appointments.id"), index=True)
    policy_id: Mapped[str] = mapped_column(String(100))
    sent_at: Mapped[datetime] = mapped_column(UtcDateTime())


class DepositRow(Base):
    __tablename__ = "deposits"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    appointment_id: Mapped[str] = mapped_column(
        ForeignKey("appointments.id"), unique=True, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(30), index=True)
    medio_pago: Mapped[str | None] = mapped_column(String(50), nullable=True)


def _secondary_rows(appointment: Appointment) -> list[AppointmentResourceRow]:
    """Build the join rows for an appointment's secondary resources.

    Module level rather than a method because inside the repository's class
    body `list` resolves to its own `list()` method, so the annotation below
    would blow up at import time.
    """
    return [
        AppointmentResourceRow(resource_id=resource_id, position=position)
        for position, resource_id in enumerate(appointment.secondary_resource_ids)
    ]


def _sync_secondary_rows(row: AppointmentRow, appointment: Appointment) -> None:
    """Reconcile the join rows in place, keeping the ones that survive.

    Replacing the whole collection would be simpler to read, but SQLAlchemy
    flushes the inserts before the delete-orphans, so a resource present both
    before and after trips the `(appointment_id, resource_id)` unique
    constraint. Touching only what actually changed avoids the clash instead
    of ordering around it.
    """
    wanted = list(appointment.secondary_resource_ids)
    existing = {item.resource_id: item for item in row.secondary_resources}
    for item in list(row.secondary_resources):
        if item.resource_id not in wanted:
            row.secondary_resources.remove(item)
    for position, resource_id in enumerate(wanted):
        kept = existing.get(resource_id)
        if kept is None:
            row.secondary_resources.append(
                AppointmentResourceRow(resource_id=resource_id, position=position)
            )
        else:
            kept.position = position


class SqlAlchemyAppointmentRepository:
    """Appointment repository backed by PostgreSQL or any SQLAlchemy database."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    @classmethod
    def from_url(cls, url: str) -> "SqlAlchemyAppointmentRepository":
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        return cls(sessionmaker(engine, expire_on_commit=False))

    def add(self, appointment: Appointment) -> None:
        with self.session_factory.begin() as session:
            session.add(self._to_row(appointment))

    def reserve(
        self,
        appointment: Appointment,
        validator: Callable[[Iterable[Appointment]], Appointment],
    ) -> Appointment:
        """Validate and insert an appointment in one database transaction.

        PostgreSQL locks the occupied resource rows so concurrent schedulers
        serialize on the same resource. SQLite has no row locks, so acquire
        its writer lock before reading the candidate set instead.
        """
        with self.session_factory.begin() as session:
            if session.bind.dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            occupied_ids = appointment.occupied_resource_ids
            if occupied_ids:
                session.scalars(
                    select(ResourceRow)
                    .where(ResourceRow.id.in_(occupied_ids))
                    .with_for_update()
                ).all()
            if session.get(AppointmentRow, appointment.id) is not None:
                raise ValueError(f"appointment already exists: {appointment.id}")
            existing_rows = session.scalars(select(AppointmentRow)).all()
            existing = tuple(self._to_domain(row) for row in existing_rows)
            stored = validator(existing)
            session.add(self._to_row(stored))
            return stored

    def get(self, appointment_id: str) -> Appointment | None:
        with self.session_factory() as session:
            row = session.get(AppointmentRow, appointment_id)
            return self._to_domain(row) if row else None

    def save(self, appointment: Appointment) -> None:
        with self.session_factory.begin() as session:
            row = session.get(AppointmentRow, appointment.id)
            if row is None:
                raise KeyError(appointment.id)
            self._copy_to_row(row, appointment)

    def list(self) -> tuple[Appointment, ...]:
        with self.session_factory() as session:
            rows = session.scalars(select(AppointmentRow).order_by(AppointmentRow.starts_at)).all()
            return tuple(self._to_domain(row) for row in rows)

    @classmethod
    def _to_row(cls, appointment: Appointment) -> AppointmentRow:
        return AppointmentRow(
            id=appointment.id, resource_id=appointment.resource_id,
            service_id=appointment.service_id, client_id=appointment.client_id,
            starts_at=appointment.starts_at,
            duration_seconds=int(appointment.duration.total_seconds()),
            status=appointment.status.value, branch_id=appointment.branch_id,
            series_id=appointment.series_id, reason=appointment.reason,
            overbooked=appointment.overbooked,
            secondary_resources=_secondary_rows(appointment),
        )

    @classmethod
    def _copy_to_row(cls, row: AppointmentRow, appointment: Appointment) -> None:
        row.resource_id = appointment.resource_id
        row.service_id = appointment.service_id
        row.client_id = appointment.client_id
        row.starts_at = appointment.starts_at
        row.duration_seconds = int(appointment.duration.total_seconds())
        row.status = appointment.status.value
        row.branch_id = appointment.branch_id
        row.series_id = appointment.series_id
        row.reason = appointment.reason
        row.overbooked = appointment.overbooked
        _sync_secondary_rows(row, appointment)

    @staticmethod
    def _to_domain(row: AppointmentRow) -> Appointment:
        return Appointment(
            id=row.id, resource_id=row.resource_id, service_id=row.service_id,
            client_id=row.client_id, starts_at=ensure_utc(row.starts_at),
            duration=timedelta(seconds=row.duration_seconds),
            status=AppointmentStatus(row.status), branch_id=row.branch_id,
            series_id=row.series_id, reason=row.reason,
            secondary_resource_ids=tuple(
                item.resource_id for item in row.secondary_resources
            ),
            overbooked=row.overbooked,
        )


class SqlAlchemyTransitionLog:
    """Append-only persistence for the appointment status history."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    @classmethod
    def from_url(cls, url: str) -> "SqlAlchemyTransitionLog":
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        return cls(sessionmaker(engine, expire_on_commit=False))

    def record(self, transition: AppointmentTransition) -> None:
        with self.session_factory.begin() as session:
            session.add(AppointmentTransitionRow(
                appointment_id=transition.appointment_id,
                from_status=(
                    transition.from_status.value if transition.from_status else None
                ),
                to_status=transition.to_status.value,
                at=transition.at,
                actor=transition.actor,
                reason=transition.reason,
            ))

    def list_for(self, appointment_id: str) -> list[AppointmentTransition]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(AppointmentTransitionRow)
                .where(AppointmentTransitionRow.appointment_id == appointment_id)
                .order_by(AppointmentTransitionRow.at, AppointmentTransitionRow.id)
            ).all()
            return [
                AppointmentTransition(
                    appointment_id=row.appointment_id,
                    from_status=(
                        AppointmentStatus(row.from_status) if row.from_status else None
                    ),
                    to_status=AppointmentStatus(row.to_status),
                    at=ensure_utc(row.at),
                    actor=row.actor,
                    reason=row.reason,
                )
                for row in rows
            ]
