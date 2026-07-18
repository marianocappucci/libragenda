"""Pure scheduling rules for LibraGenda."""

from dataclasses import dataclass
from datetime import date, datetime, time

from .domain import Appointment, Availability, Holiday, Resource


@dataclass(frozen=True, slots=True)
class TimeBlock:
    """A period in which a resource cannot receive appointments."""

    resource_id: str
    starts_at: datetime
    ends_at: datetime
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.resource_id.strip():
            raise ValueError("block resource id cannot be empty")
        if self.starts_at >= self.ends_at:
            raise ValueError("block must end after it starts")


@dataclass(frozen=True, slots=True)
class AvailabilityException:
    """A date-specific replacement or closure for a weekly window."""

    resource_id: str
    day: date
    starts_at: time
    ends_at: time
    available: bool = False

    def __post_init__(self) -> None:
        if not self.resource_id.strip():
            raise ValueError("exception resource id cannot be empty")
        if self.starts_at >= self.ends_at:
            raise ValueError("exception must end after it starts")


def intervals_overlap(first_start: datetime, first_end: datetime,
                      second_start: datetime, second_end: datetime) -> bool:
    """Return whether two half-open time intervals overlap."""
    return first_start < second_end and second_start < first_end


def find_conflicts(appointment: Appointment,
                   existing: list[Appointment]) -> list[Appointment]:
    """Find existing active appointments for the same resource that overlap."""
    return [
        other for other in existing
        if other.id != appointment.id
        and other.resource_id == appointment.resource_id
        and other.status.value not in {"cancelled", "no_show"}
        and intervals_overlap(
            appointment.starts_at, appointment.ends_at,
            other.starts_at, other.ends_at,
        )
    ]


def is_appointment_available(
    appointment: Appointment,
    weekly_windows: list[Availability],
    blocks: list[TimeBlock] | None = None,
    exceptions: list[AvailabilityException] | None = None,
    holidays: list[Holiday] | None = None,
    resources: list[Resource] | None = None,
) -> bool:
    """Check weekly availability, holidays, date exceptions and blocks.

    A per-resource `AvailabilityException` always has the final say: it can
    both close a resource that would otherwise be open (including on a
    branch holiday) and reopen one that a holiday would otherwise close.
    `holidays`/`resources` are optional; omit both to keep the previous
    behaviour of resources with no branch or no holiday calendar.
    """
    blocks = blocks or []
    exceptions = exceptions or []
    holidays = holidays or []
    resources = resources or []
    matching_exceptions = [
        exception for exception in exceptions
        if exception.resource_id == appointment.resource_id
        and exception.day == appointment.starts_at.date()
        and appointment.starts_at.time() >= exception.starts_at
        and appointment.ends_at.time() <= exception.ends_at
    ]
    if matching_exceptions:
        available = matching_exceptions[-1].available
    elif _is_branch_holiday(appointment, holidays, resources):
        available = False
    else:
        available = any(
            window.resource_id == appointment.resource_id
            and window.contains(appointment.starts_at, appointment.ends_at)
            for window in weekly_windows
        )
    if not available:
        return False
    return not any(
        block.resource_id == appointment.resource_id
        and intervals_overlap(
            appointment.starts_at, appointment.ends_at,
            block.starts_at, block.ends_at,
        )
        for block in blocks
    )


def _is_branch_holiday(
    appointment: Appointment, holidays: list[Holiday], resources: list[Resource]
) -> bool:
    resource = next(
        (item for item in resources if item.id == appointment.resource_id), None
    )
    if resource is None or resource.branch_id is None:
        return False
    day = appointment.starts_at.date()
    return any(
        holiday.branch_id == resource.branch_id and holiday.day == day
        for holiday in holidays
    )


class BranchMismatch(ValueError):
    """Raised when an appointment's resource does not belong to its branch."""


def check_resource_branch(appointment: Appointment, resource: Resource) -> None:
    """Validate that `resource` can serve an appointment scoped to a branch.

    No-op if the appointment does not declare a branch. Otherwise the
    resource must belong to that same branch — a resource with no branch at
    all is rejected too, since it cannot honor a branch-scoped request.
    """
    if appointment.branch_id is None:
        return
    if resource.branch_id != appointment.branch_id:
        raise BranchMismatch(
            f"resource {resource.id} belongs to branch {resource.branch_id!r}, "
            f"not {appointment.branch_id!r}"
        )
