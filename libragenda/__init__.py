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
    Resource,
    Service,
)

__all__ = [
    "Appointment",
    "AppointmentStatus",
    "Availability",
    "Resource",
    "Service",
]

from .scheduling import AvailabilityException, TimeBlock

from .application import (
    AppointmentConflict,
    AppointmentNotFound,
    AppointmentUnavailable,
    InMemoryScheduler,
    InvalidTransition,
)

from .repositories import AppointmentRepository, InMemoryAppointmentRepository

from .sqlalchemy_repository import SqlAlchemyAppointmentRepository

from .catalog_repository import SqlAlchemyCatalogRepository

from .availability_repository import SqlAlchemyAvailabilityRepository

from .database import configure as configure_database, get_engine, get_session_factory
