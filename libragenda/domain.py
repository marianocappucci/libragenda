"""Core domain contract for LibraGenda.

The first domain layer is deliberately framework- and persistence-agnostic.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from .timezones import validate_timezone


@dataclass(frozen=True, slots=True)
class Resource:
    """Anything that can receive an appointment."""

    id: str
    name: str
    branch_id: str | None = None
    active: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("resource id cannot be empty")
        if not self.name.strip():
            raise ValueError("resource name cannot be empty")


@dataclass(frozen=True, slots=True)
class Service:
    """A bookable service with a default duration."""

    id: str
    name: str
    duration: timedelta
    active: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("service id cannot be empty")
        if not self.name.strip():
            raise ValueError("service name cannot be empty")
        if self.duration <= timedelta(0):
            raise ValueError("service duration must be positive")


@dataclass(frozen=True, slots=True)
class Availability:
    """A recurring weekly availability window for a resource."""

    resource_id: str
    weekday: int
    starts_at: time
    ends_at: time
    valid_from: date | None = None
    """First day this window applies, inclusive. `None` means "always was"."""
    valid_to: date | None = None
    """Last day this window applies, inclusive. `None` means "still is"."""

    def __post_init__(self) -> None:
        if not 0 <= self.weekday <= 6:
            raise ValueError("weekday must be between 0 (Monday) and 6 (Sunday)")
        if self.starts_at >= self.ends_at:
            raise ValueError("availability must end after it starts")
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_from > self.valid_to
        ):
            raise ValueError("availability validity must end on or after it starts")

    def applies_on(self, day: date) -> bool:
        """Return whether this window is in force on `day`.

        Both bounds are inclusive and independently optional, so a window
        with neither behaves exactly like one that never had them — which is
        what every window created before validity existed relies on.
        """
        if self.valid_from is not None and day < self.valid_from:
            return False
        return not (self.valid_to is not None and day > self.valid_to)

    def contains(self, starts_at: datetime, ends_at: datetime) -> bool:
        """Return whether an interval falls inside this weekly window."""
        return (
            starts_at.weekday() == self.weekday
            and starts_at.time() >= self.starts_at
            and ends_at.time() <= self.ends_at
            and starts_at.date() == ends_at.date()
            and self.applies_on(starts_at.date())
        )


class AppointmentStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


@dataclass(frozen=True, slots=True)
class Appointment:
    """A reservation of one resource for one service and client."""

    id: str
    resource_id: str
    service_id: str
    client_id: str
    starts_at: datetime
    duration: timedelta
    status: AppointmentStatus = AppointmentStatus.PENDING
    branch_id: str | None = None
    """Branch the appointment was booked through, when the vertical scopes
    appointments by branch. Optional: engines that never assign resources to
    branches can leave this unset."""
    series_id: str | None = None
    """Groups the occurrences generated from one RecurrenceRule. Optional:
    the recurrence engine only produces datetimes, it never assigns this —
    the caller decides whether and how to link occurrences together."""
    reason: str | None = None
    """Free-text note for the last cancellation or reschedule, set by the
    caller. The engine never requires, validates the content of, or enforces
    a notice policy around it — that's vertical-specific business logic."""
    secondary_resource_ids: tuple[str, ...] = ()
    """Extra resources this appointment occupies for the same interval, on top
    of `resource_id`. The engine assigns them no meaning beyond occupancy: a
    consulting room, a workshop bay, a washing station. They are checked for
    conflicts and blocks exactly like the primary resource, but they are NOT
    required to have weekly availability of their own — a room is open
    whenever somebody books it, unlike a person."""
    overbooked: bool = False
    """Set by the scheduler when this appointment was deliberately allowed to
    overlap another one. It is what separates an authorized overbooking from a
    data-entry mistake, which is the whole reason it is stored rather than
    inferred from the overlap."""

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("appointment id cannot be empty")
        for field_name in ("resource_id", "service_id", "client_id"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        if self.duration <= timedelta(0):
            raise ValueError("appointment duration must be positive")
        if self.branch_id is not None and not self.branch_id.strip():
            raise ValueError("branch_id cannot be blank when provided")
        if self.series_id is not None and not self.series_id.strip():
            raise ValueError("series_id cannot be blank when provided")
        if self.reason is not None and not self.reason.strip():
            raise ValueError("reason cannot be blank when provided")
        for secondary_id in self.secondary_resource_ids:
            if not secondary_id.strip():
                raise ValueError("secondary resource id cannot be blank")
        if len(set(self.secondary_resource_ids)) != len(self.secondary_resource_ids):
            raise ValueError("secondary resource ids cannot repeat")
        if self.resource_id in self.secondary_resource_ids:
            raise ValueError("secondary resource ids cannot include the primary resource")

    @property
    def occupied_resource_ids(self) -> tuple[str, ...]:
        """Every resource this appointment makes busy, primary one first."""
        return (self.resource_id, *self.secondary_resource_ids)

    @property
    def ends_at(self) -> datetime:
        return self.starts_at + self.duration

    def is_on(self, day: date) -> bool:
        return self.starts_at.date() == day


@dataclass(frozen=True, slots=True)
class AppointmentTransition:
    """One recorded move of an appointment from one status to another.

    The creation of an appointment is recorded too, with `from_status` unset —
    otherwise the first thing that ever happened to a booking would be the
    only thing missing from its history.

    Timestamps like "when did attention start" are read from this log rather
    than stored as columns on the appointment: a status and the instant it was
    reached are the same fact, and keeping them together is what stops the two
    from drifting apart.
    """

    appointment_id: str
    to_status: AppointmentStatus
    at: datetime
    from_status: AppointmentStatus | None = None
    actor: str | None = None
    """Who caused the transition, as the consumer names its users. The engine
    has no notion of identity and never validates this."""
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.appointment_id.strip():
            raise ValueError("transition appointment_id cannot be empty")
        if self.at.tzinfo is None:
            raise ValueError("transition timestamp must be timezone-aware")
        if self.actor is not None and not self.actor.strip():
            raise ValueError("actor cannot be blank when provided")
        if self.reason is not None and not self.reason.strip():
            raise ValueError("reason cannot be blank when provided")


def first_time_at(
    transitions: Iterable[AppointmentTransition], status: AppointmentStatus
) -> datetime | None:
    """When an appointment first reached `status`, or `None` if it never did.

    This is how the engine answers "started at" and "finished at" without
    either column existing.
    """
    return next(
        (item.at for item in sorted(transitions, key=lambda item: item.at)
         if item.to_status == status),
        None,
    )


@dataclass(frozen=True, slots=True)
class Branch:
    id: str
    name: str
    active: bool = True
    timezone: str = "UTC"

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("branch id and name cannot be empty")
        validate_timezone(self.timezone)


@dataclass(frozen=True, slots=True)
class Holiday:
    """A calendar exception shared by every resource of a branch."""

    branch_id: str
    day: date
    name: str

    def __post_init__(self) -> None:
        if not self.branch_id.strip():
            raise ValueError("holiday branch_id cannot be empty")
        if not self.name.strip():
            raise ValueError("holiday name cannot be empty")


@dataclass(frozen=True, slots=True)
class Client:
    id: str
    name: str
    phone: str | None = None
    email: str | None = None
    active: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("client id and name cannot be empty")
