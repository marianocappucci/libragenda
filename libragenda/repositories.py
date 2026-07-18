"""Storage ports and in-memory adapters for LibraGenda."""

from collections.abc import Iterable
from typing import Protocol

from .domain import Appointment


class AppointmentRepository(Protocol):
    """Port required by application use cases to store appointments."""

    def add(self, appointment: Appointment) -> None: ...

    def get(self, appointment_id: str) -> Appointment | None: ...

    def save(self, appointment: Appointment) -> None: ...

    def list(self) -> Iterable[Appointment]: ...


class InMemoryAppointmentRepository:
    """Reference adapter for tests and local development."""

    def __init__(self) -> None:
        self._items: dict[str, Appointment] = {}

    def add(self, appointment: Appointment) -> None:
        if appointment.id in self._items:
            raise ValueError(f"appointment already exists: {appointment.id}")
        self._items[appointment.id] = appointment

    def get(self, appointment_id: str) -> Appointment | None:
        return self._items.get(appointment_id)

    def save(self, appointment: Appointment) -> None:
        if appointment.id not in self._items:
            raise KeyError(appointment.id)
        self._items[appointment.id] = appointment

    def list(self) -> Iterable[Appointment]:
        return tuple(self._items.values())
