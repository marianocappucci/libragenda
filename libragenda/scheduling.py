"""Pure scheduling rules for LibraGenda."""

from dataclasses import dataclass
from datetime import date, datetime, time

from .domain import Appointment, Availability


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
) -> bool:
    """Check weekly availability, date exceptions and point-in-time blocks."""
    blocks = blocks or []
    exceptions = exceptions or []
    matching_exceptions = [
        exception for exception in exceptions
        if exception.resource_id == appointment.resource_id
        and exception.day == appointment.starts_at.date()
        and appointment.starts_at.time() >= exception.starts_at
        and appointment.ends_at.time() <= exception.ends_at
    ]
    if matching_exceptions:
        available = matching_exceptions[-1].available
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
