"""Core domain contract for LibraGenda.

The first domain layer is deliberately framework- and persistence-agnostic.
"""

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

    def __post_init__(self) -> None:
        if not 0 <= self.weekday <= 6:
            raise ValueError("weekday must be between 0 (Monday) and 6 (Sunday)")
        if self.starts_at >= self.ends_at:
            raise ValueError("availability must end after it starts")

    def contains(self, starts_at: datetime, ends_at: datetime) -> bool:
        """Return whether an interval falls inside this weekly window."""
        return (
            starts_at.weekday() == self.weekday
            and starts_at.time() >= self.starts_at
            and ends_at.time() <= self.ends_at
            and starts_at.date() == ends_at.date()
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

    @property
    def ends_at(self) -> datetime:
        return self.starts_at + self.duration

    def is_on(self, day: date) -> bool:
        return self.starts_at.date() == day


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
