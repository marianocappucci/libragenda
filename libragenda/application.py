"""Application use cases over the LibraGenda domain."""

from datetime import datetime

from .domain import Appointment, AppointmentStatus, Availability, Holiday, Resource
from .repositories import AppointmentRepository, InMemoryAppointmentRepository
from .scheduling import (
    AvailabilityException,
    BranchMismatch,
    TimeBlock,
    check_resource_branch,
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


class ResourceBranchMismatch(ScheduleError):
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
        holidays: list[Holiday] | None = None,
        resources: list[Resource] | None = None,
        repository: AppointmentRepository | None = None,
    ) -> None:
        self.availability = availability or []
        self.blocks = blocks or []
        self.exceptions = exceptions or []
        self.holidays = holidays or []
        self.resources = resources or []
        self.repository = repository or InMemoryAppointmentRepository()

    def create(self, appointment: Appointment) -> Appointment:
        if self.repository.get(appointment.id) is not None:
            raise ScheduleError(f"appointment already exists: {appointment.id}")
        self._validate_slot(appointment)
        try:
            self.repository.add(appointment)
        except ValueError as exc:
            raise ScheduleError(str(exc)) from exc
        return appointment

    def get(self, appointment_id: str) -> Appointment:
        appointment = self.repository.get(appointment_id)
        if appointment is None:
            raise AppointmentNotFound(appointment_id)
        return appointment

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
            status=current.status, branch_id=current.branch_id,
        )
        self._validate_slot(candidate, exclude_id=current.id)
        self.repository.save(candidate)
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
            duration=current.duration, status=target, branch_id=current.branch_id,
        )
        self.repository.save(updated)
        return updated

    def _validate_slot(self, appointment: Appointment, exclude_id: str | None = None) -> None:
        resource = next(
            (item for item in self.resources if item.id == appointment.resource_id), None
        )
        if resource is not None:
            try:
                check_resource_branch(appointment, resource)
            except BranchMismatch as exc:
                raise ResourceBranchMismatch(str(exc)) from exc
        if not is_appointment_available(
            appointment, self.availability, self.blocks, self.exceptions,
            self.holidays, self.resources,
        ):
            raise AppointmentUnavailable(appointment.id)
        existing = [item for item in self.repository.list() if item.id != exclude_id]
        if find_conflicts(appointment, existing):
            raise AppointmentConflict(appointment.id)
