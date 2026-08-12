"""Application use cases over the LibraGenda domain."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from .domain import (
    Appointment,
    AppointmentStatus,
    AppointmentTransition,
    Availability,
    Holiday,
    Resource,
)
from .repositories import (
    AppointmentRepository,
    InMemoryAppointmentRepository,
    InMemoryTransitionLog,
    TransitionLogRepository,
)
from .scheduling import (
    AgendaPolicy,
    AvailabilityException,
    BranchMismatch,
    TimeBlock,
    check_resource_branch,
    find_conflicts,
    is_appointment_available,
    policy_for,
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


class OverbookingLimitReached(ScheduleError):
    """Raised when an authorized overbooking would exceed the agenda's cap.

    Distinct from `AppointmentConflict`: that one means "this slot is taken
    and you did not ask to overbook", this one means "you asked, and the
    agenda has had enough for the day".
    """


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
        policies: list[AgendaPolicy] | None = None,
        transition_log: TransitionLogRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.availability = availability or []
        self.blocks = blocks or []
        self.exceptions = exceptions or []
        self.holidays = holidays or []
        self.resources = resources or []
        self.repository = repository or InMemoryAppointmentRepository()
        self.policies = policies or []
        self.transition_log = transition_log or InMemoryTransitionLog()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def create(
        self,
        appointment: Appointment,
        allow_overbooking: bool = False,
        actor: str | None = None,
    ) -> Appointment:
        """Book an appointment, optionally as an authorized overbooking.

        `allow_overbooking` only relaxes the conflict rule — never opening
        hours, holidays or blocks. A sobreturno is squeezed into a working
        day, not into a day off, and an agenda that is closed is closed.

        The stored appointment carries `overbooked=True` **only if it really
        did overlap something**: asking to overbook and not needing to is an
        ordinary booking, and recording it otherwise would inflate the very
        count the cap is meant to control.
        """
        try:
            stored = self.repository.reserve(
                appointment,
                lambda existing: replace(
                    appointment,
                    overbooked=self._validate_slot(
                        appointment,
                        existing=existing,
                        allow_overbooking=allow_overbooking,
                    ),
                ),
            )
        except ValueError as exc:
            raise ScheduleError(str(exc)) from exc
        self._record(stored, from_status=None, actor=actor)
        return stored

    def get(self, appointment_id: str) -> Appointment:
        appointment = self.repository.get(appointment_id)
        if appointment is None:
            raise AppointmentNotFound(appointment_id)
        return appointment

    def history(self, appointment_id: str) -> list[AppointmentTransition]:
        """Everything that ever happened to this appointment, oldest first."""
        return sorted(self.transition_log.list_for(appointment_id), key=lambda item: item.at)

    def confirm(self, appointment_id: str, actor: str | None = None) -> Appointment:
        return self._transition(appointment_id, AppointmentStatus.CONFIRMED, actor=actor)

    def start(self, appointment_id: str, actor: str | None = None) -> Appointment:
        """Mark an appointment as being attended right now.

        The `confirmed`/`in_progress` transition existed in the state machine
        from the original design; it just never had a verb, the same way
        `complete()` did not until ADR-006.
        """
        return self._transition(appointment_id, AppointmentStatus.IN_PROGRESS, actor=actor)

    def cancel(
        self, appointment_id: str, reason: str | None = None, actor: str | None = None
    ) -> Appointment:
        return self._transition(
            appointment_id, AppointmentStatus.CANCELLED, reason=reason, actor=actor
        )

    def complete(self, appointment_id: str, actor: str | None = None) -> Appointment:
        return self._transition(appointment_id, AppointmentStatus.COMPLETED, actor=actor)

    def list_series(self, series_id: str) -> list[Appointment]:
        return [item for item in self.repository.list() if item.series_id == series_id]

    def cancel_series(
        self, series_id: str, reason: str | None = None, actor: str | None = None
    ) -> list[Appointment]:
        """Cancel every still-cancellable occurrence of a series.

        Occurrences already completed, cancelled or marked no-show are left
        untouched instead of raising, since cancelling a whole series should
        not fail just because one past occurrence is already closed out.
        """
        cancelled = []
        for occurrence in self.list_series(series_id):
            if AppointmentStatus.CANCELLED in _ALLOWED_TRANSITIONS[occurrence.status]:
                cancelled.append(self.cancel(occurrence.id, reason=reason, actor=actor))
        return cancelled

    def reschedule(
        self,
        appointment_id: str,
        starts_at: datetime,
        reason: str | None = None,
        allow_overbooking: bool = False,
        actor: str | None = None,
    ) -> Appointment:
        current = self.get(appointment_id)
        if current.status not in {AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED}:
            raise InvalidTransition(f"cannot reschedule {current.status.value} appointment")
        candidate = replace(
            current,
            starts_at=starts_at,
            reason=reason if reason is not None else current.reason,
        )
        overbooked = self._validate_slot(
            candidate, exclude_id=current.id, allow_overbooking=allow_overbooking
        )
        moved = replace(candidate, overbooked=overbooked)
        self.repository.save(moved)
        self._record(moved, from_status=current.status, actor=actor, reason=reason)
        return moved

    def _transition(
        self,
        appointment_id: str,
        target: AppointmentStatus,
        reason: str | None = None,
        actor: str | None = None,
    ) -> Appointment:
        current = self.get(appointment_id)
        if target not in _ALLOWED_TRANSITIONS[current.status]:
            raise InvalidTransition(
                f"cannot transition {current.status.value} to {target.value}"
            )
        updated = replace(
            current,
            status=target,
            reason=reason if reason is not None else current.reason,
        )
        self.repository.save(updated)
        self._record(updated, from_status=current.status, actor=actor, reason=reason)
        return updated

    def _record(
        self,
        appointment: Appointment,
        from_status: AppointmentStatus | None,
        actor: str | None,
        reason: str | None = None,
    ) -> None:
        """Append one entry to the history.

        A reschedule is recorded too, with `from_status` equal to the status
        it kept: moving a booking is a change worth auditing even though it
        is not a change of state, and the alternative — leaving it out — makes
        "who moved this and when" unanswerable.
        """
        self.transition_log.record(AppointmentTransition(
            appointment_id=appointment.id,
            from_status=from_status,
            to_status=appointment.status,
            at=self.clock(),
            actor=actor,
            reason=reason,
        ))

    def _validate_slot(
        self,
        appointment: Appointment,
        exclude_id: str | None = None,
        allow_overbooking: bool = False,
        existing=None,
    ) -> bool:
        """Check a candidate slot; return whether it lands as an overbooking."""
        for resource_id in appointment.occupied_resource_ids:
            resource = next((item for item in self.resources if item.id == resource_id), None)
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
        policy = policy_for(appointment.resource_id, self.policies)
        if existing is None:
            existing = self.repository.list()
        existing = [item for item in existing if item.id != exclude_id]
        if not find_conflicts(appointment, existing, gap=policy.slot_interval):
            return False
        if not allow_overbooking:
            raise AppointmentConflict(appointment.id)
        self._check_overbooking_cap(appointment, policy, existing)
        return True

    @staticmethod
    def _check_overbooking_cap(
        appointment: Appointment, policy: AgendaPolicy, existing: list[Appointment]
    ) -> None:
        day = appointment.starts_at.date()
        already = [
            item for item in existing
            if item.overbooked
            and item.resource_id == appointment.resource_id
            and item.starts_at.date() == day
            and item.status.value not in {"cancelled", "no_show"}
        ]
        if len(already) >= policy.max_overbookings_per_day:
            raise OverbookingLimitReached(
                f"resource {appointment.resource_id} already has {len(already)} "
                f"overbooking(s) on {day}, cap is {policy.max_overbookings_per_day}"
            )
