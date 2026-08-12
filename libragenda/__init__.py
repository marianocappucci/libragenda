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
    AppointmentTransition,
    Branch,
    Client,
    Availability,
    Holiday,
    Resource,
    Service,
    first_time_at,
)

__all__ = [
    "Appointment",
    "AppointmentStatus",
    "AppointmentTransition",
    "Availability",
    "Holiday",
    "Resource",
    "Service",
    "first_time_at",
]

from .scheduling import (
    AgendaPolicy,
    AvailabilityException,
    BranchMismatch,
    TimeBlock,
    check_resource_branch,
    policy_for,
)

from .timezones import to_branch_local, to_utc, validate_timezone

from .recurrence import RecurrenceRule, generate_occurrences

from .notifications import (
    NotificationPort,
    ReminderNotification,
    ReminderPolicy,
    due_reminders,
)

from .payments import Deposit, DepositStatus, PaymentPort

from .application import (
    AppointmentConflict,
    AppointmentNotFound,
    AppointmentUnavailable,
    InMemoryScheduler,
    InvalidTransition,
    OverbookingLimitReached,
    ResourceBranchMismatch,
)

from .reminder_dispatcher import ReminderDispatcher

from .deposit_manager import (
    DepositError,
    DepositManager,
    DepositNotFound,
    InvalidDepositTransition,
)

from .repositories import (
    AppointmentRepository,
    DepositRepository,
    InMemoryAppointmentRepository,
    InMemoryDepositRepository,
    InMemorySentReminderRepository,
    InMemoryTransitionLog,
    SentReminderRepository,
    TransitionLogRepository,
)

from .sqlalchemy_repository import SqlAlchemyAppointmentRepository, SqlAlchemyTransitionLog

from .catalog_repository import SqlAlchemyCatalogRepository

from .availability_repository import SqlAlchemyAvailabilityRepository

from .reminder_repository import SqlAlchemyReminderRepository

from .deposit_repository import SqlAlchemyDepositRepository

from .database import configure as configure_database, get_engine, get_session_factory
