"""SQLAlchemy persistence adapter for appointments."""

from datetime import datetime, timedelta

from sqlalchemy import DateTime, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .domain import Appointment, AppointmentStatus


class Base(DeclarativeBase):
    pass


class AppointmentRow(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(100), index=True)
    service_id: Mapped[str] = mapped_column(String(100), index=True)
    client_id: Mapped[str] = mapped_column(String(100), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), index=True)


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
            status=appointment.status.value,
        )

    @staticmethod
    def _copy_to_row(row: AppointmentRow, appointment: Appointment) -> None:
        row.resource_id = appointment.resource_id
        row.service_id = appointment.service_id
        row.client_id = appointment.client_id
        row.starts_at = appointment.starts_at
        row.duration_seconds = int(appointment.duration.total_seconds())
        row.status = appointment.status.value

    @staticmethod
    def _to_domain(row: AppointmentRow) -> Appointment:
        return Appointment(
            id=row.id, resource_id=row.resource_id, service_id=row.service_id,
            client_id=row.client_id, starts_at=row.starts_at,
            duration=timedelta(seconds=row.duration_seconds),
            status=AppointmentStatus(row.status),
        )
