"""Application use cases over the LibraGenda domain."""

from datetime import datetime

from .domain import Appointment, AppointmentStatus, Availability
from .scheduling import (
    AvailabilityException,
    TimeBlock,
    find_conflicts,
    is_appointment_available,
)


class ScheduleError(Exception):
    """Base error for schedule use-case failures."""


class AppointmentNotFound(ScheduleError):
    pass


class AppointmentConflict(ScheduleError):
    pass


class AppointmentUnavailable(ScheduleError):
    pass


class InvalidTransition(ScheduleError):
    pass


_ALLOWED_TRANSITIONS = {
    AppointmentStatus.PENDING: {AppointmentStatus.CONFIRMED, AppointmentStatus.CANCELLED},
    AppointmentStatus.CONFIRMED: {
        AppointmentStatus.IN_PROGRESS,
        AppointmentStatus.COMPLETED,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.NO_SHOW,
    },
    AppointmentStatus.IN_PROGRESS: {AppointmentStatus.COMPLETED},
    AppointmentStatus.COMPLETED: set(),
    AppointmentStatus.CANCELLED: set(),
    AppointmentStatus.NO_SHOW: set(),
}


class InMemoryScheduler:
    """Small in-memory application service used until persistence is added."""

    def __init__(
        self,
        availability: list[Availability] | None = None,
        blocks: list[TimeBlock] | None = None,
        exceptions: list[AvailabilityException] | None = None,
    ) -> None:
        self.availability = availability or []
        self.blocks = blocks or []
        self.exceptions = exceptions or []
        self._appointments: dict[str, Appointment] = {}

    def create(self, appointment: Appointment) -> Appointment:
        if appointment.id in self._appointments:
            raise ScheduleError(f"appointment already exists: {appointment.id}")
        self._validate_slot(appointment)
        self._appointments[appointment.id] = appointment
        return appointment

    def get(self, appointment_id: str) -> Appointment:
        try:
            return self._appointments[appointment_id]
        except KeyError as exc:
            raise AppointmentNotFound(appointment_id) from exc

    def confirm(self, appointment_id: str) -> Appointment:
        return self._transition(appointment_id, AppointmentStatus.CONFIRMED)

    def cancel(self, appointment_id: str) -> Appointment:
        return self._transition(appointment_id, AppointmentStatus.CANCELLED)

    def reschedule(self, appointment_id: str, starts_at: datetime) -> Appointment:
        current = self.get(appointment_id)
        if current.status not in {AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED}:
            raise InvalidTransition(f"cannot reschedule {current.status.value} appointment")
        candidate = Appointment(
            id=current.id, resource_id=current.resource_id, service_id=current.service_id,
            client_id=current.client_id, starts_at=starts_at, duration=current.duration,
            status=current.status,
        )
        self._validate_slot(candidate, exclude_id=current.id)
        self._appointments[appointment_id] = candidate
        return candidate

    def _transition(self, appointment_id: str, target: AppointmentStatus) -> Appointment:
        current = self.get(appointment_id)
        if target not in _ALLOWED_TRANSITIONS[current.status]:
            raise InvalidTransition(
                f"cannot transition {current.status.value} to {target.value}"
            )
        updated = Appointment(
            id=current.id, resource_id=current.resource_id, service_id=current.service_id,
            client_id=current.client_id, starts_at=current.starts_at,
            duration=current.duration, status=target,
        )
        self._appointments[appointment_id] = updated
        return updated

    def _validate_slot(self, appointment: Appointment, exclude_id: str | None = None) -> None:
        if not is_appointment_available(
            appointment, self.availability, self.blocks, self.exceptions
        ):
            raise AppointmentUnavailable(appointment.id)
        existing = [item for item in self._appointments.values() if item.id != exclude_id]
        if find_conflicts(appointment, existing):
            raise AppointmentConflict(appointment.id)
