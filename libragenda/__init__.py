"""LibraGenda — motor generico reutilizable de turnos y agenda.

LibraGenda es un paquete interno independiente de LibraCore. Los productos
verticales componen uno, otro o ambos segun sus necesidades.
"""

try:
    from importlib.metadata import version as _version

    __version__ = _version("libragenda")
except Exception:
    __version__ = "0.0.0.dev0"


from .domain import (
    Appointment,
    AppointmentStatus,
    Branch,
    Client,
    Availability,
    Holiday,
    Resource,
    Service,
)

__all__ = [
    "Appointment",
    "AppointmentStatus",
    "Availability",
    "Holiday",
    "Resource",
    "Service",
]

from .scheduling import AvailabilityException, BranchMismatch, TimeBlock, check_resource_branch

from .timezones import to_branch_local, to_utc, validate_timezone

from .recurrence import RecurrenceRule, generate_occurrences

from .notifications import (
    NotificationPort,
    ReminderNotification,
    ReminderPolicy,
    due_reminders,
)

from .application import (
    AppointmentConflict,
    AppointmentNotFound,
    AppointmentUnavailable,
    InMemoryScheduler,
    InvalidTransition,
    ResourceBranchMismatch,
)

from .reminder_dispatcher import ReminderDispatcher

from .repositories import (
    AppointmentRepository,
    InMemoryAppointmentRepository,
    InMemorySentReminderRepository,
    SentReminderRepository,
)

from .sqlalchemy_repository import SqlAlchemyAppointmentRepository

from .catalog_repository import SqlAlchemyCatalogRepository

from .availability_repository import SqlAlchemyAvailabilityRepository

from .reminder_repository import SqlAlchemyReminderRepository

from .database import configure as configure_database, get_engine, get_session_factory
