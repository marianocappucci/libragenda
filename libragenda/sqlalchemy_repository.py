"""SQLAlchemy persistence adapter for appointments."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import (
    Date, DateTime, ForeignKey, Integer, String, Text, Time, UniqueConstraint,
    create_engine, select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .domain import Appointment, AppointmentStatus


class Base(DeclarativeBase):
    pass


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


class TimeBlockRow(Base):
    __tablename__ = "time_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
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
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), index=True)
    branch_id: Mapped[str | None] = mapped_column(
        ForeignKey("branches.id"), nullable=True, index=True
    )
    series_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)


class SentReminderRow(Base):
    __tablename__ = "sent_reminders"
    __table_args__ = (UniqueConstraint("appointment_id", "policy_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    appointment_id: Mapped[str] = mapped_column(ForeignKey("appointments.id"), index=True)
    policy_id: Mapped[str] = mapped_column(String(100))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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

    @staticmethod
    def _to_row(appointment: Appointment) -> AppointmentRow:
        return AppointmentRow(
            id=appointment.id, resource_id=appointment.resource_id,
            service_id=appointment.service_id, client_id=appointment.client_id,
            starts_at=appointment.starts_at,
            duration_seconds=int(appointment.duration.total_seconds()),
            status=appointment.status.value, branch_id=appointment.branch_id,
            series_id=appointment.series_id,
        )

    @staticmethod
    def _copy_to_row(row: AppointmentRow, appointment: Appointment) -> None:
        row.resource_id = appointment.resource_id
        row.service_id = appointment.service_id
        row.client_id = appointment.client_id
        row.starts_at = appointment.starts_at
        row.duration_seconds = int(appointment.duration.total_seconds())
        row.status = appointment.status.value
        row.branch_id = appointment.branch_id
        row.series_id = appointment.series_id

    @staticmethod
    def _to_domain(row: AppointmentRow) -> Appointment:
        return Appointment(
            id=row.id, resource_id=row.resource_id, service_id=row.service_id,
            client_id=row.client_id, starts_at=row.starts_at,
            duration=timedelta(seconds=row.duration_seconds),
            status=AppointmentStatus(row.status), branch_id=row.branch_id,
            series_id=row.series_id,
        )
