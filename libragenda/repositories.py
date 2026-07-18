"""Storage ports and in-memory adapters for LibraGenda."""

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from .domain import Appointment
from .payments import Deposit


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


class SentReminderRepository(Protocol):
    """Port tracking which (appointment_id, policy_id) reminders were sent."""

    def sent_pairs(self, appointment_ids: list[str]) -> set[tuple[str, str]]: ...

    def mark_sent(self, appointment_id: str, policy_id: str, sent_at: datetime) -> None: ...


class InMemorySentReminderRepository:
    """Reference adapter for tests and local development."""

    def __init__(self) -> None:
        self._sent: set[tuple[str, str]] = set()

    def sent_pairs(self, appointment_ids: list[str]) -> set[tuple[str, str]]:
        wanted = set(appointment_ids)
        return {pair for pair in self._sent if pair[0] in wanted}

    def mark_sent(self, appointment_id: str, policy_id: str, sent_at: datetime) -> None:
        self._sent.add((appointment_id, policy_id))


class DepositRepository(Protocol):
    """Port for the at-most-one-deposit-per-appointment ledger."""

    def add(self, deposit: Deposit) -> None: ...

    def get(self, deposit_id: str) -> Deposit | None: ...

    def get_by_appointment(self, appointment_id: str) -> Deposit | None: ...

    def save(self, deposit: Deposit) -> None: ...


class InMemoryDepositRepository:
    """Reference adapter for tests and local development."""

    def __init__(self) -> None:
        self._items: dict[str, Deposit] = {}

    def add(self, deposit: Deposit) -> None:
        if deposit.id in self._items:
            raise ValueError(f"deposit already exists: {deposit.id}")
        if self.get_by_appointment(deposit.appointment_id) is not None:
            raise ValueError(f"appointment already has a deposit: {deposit.appointment_id}")
        self._items[deposit.id] = deposit

    def get(self, deposit_id: str) -> Deposit | None:
        return self._items.get(deposit_id)

    def get_by_appointment(self, appointment_id: str) -> Deposit | None:
        return next(
            (item for item in self._items.values() if item.appointment_id == appointment_id),
            None,
        )

    def save(self, deposit: Deposit) -> None:
        if deposit.id not in self._items:
            raise KeyError(deposit.id)
        self._items[deposit.id] = deposit
