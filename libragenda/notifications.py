"""Reminder rules and the outbound notification port.

Per MODULES.md, LibraGenda only owns the port and the "is this reminder due"
rule. Building message copy, picking a channel (email/SMS/WhatsApp) and
templating belong to the vertical's NotificationPort implementation.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from .domain import Appointment, AppointmentStatus

_REMINDABLE_STATUSES = {AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED}


@dataclass(frozen=True, slots=True)
class ReminderPolicy:
    """A named lead time before an appointment. Define several for e.g. 24h + 1h."""

    id: str
    lead_time: timedelta

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("reminder policy id cannot be empty")
        if self.lead_time <= timedelta(0):
            raise ValueError("lead_time must be positive")


@dataclass(frozen=True, slots=True)
class ReminderNotification:
    """Structured payload handed to the port; it carries no message text."""

    appointment_id: str
    policy_id: str
    resource_id: str
    service_id: str
    client_id: str
    starts_at: datetime


class NotificationPort(Protocol):
    """Outbound port a vertical implements to actually deliver a reminder."""

    def send(self, notification: ReminderNotification) -> None: ...


def due_reminders(
    appointments: list[Appointment],
    policies: list[ReminderPolicy],
    now: datetime,
    already_sent: set[tuple[str, str]],
) -> list[ReminderNotification]:
    """Return reminders whose lead time has arrived and were not sent yet.

    Only appointments still eligible to happen (pending/confirmed) are
    considered, and a reminder is never fired once the appointment already
    started — no point notifying about something already underway.
    """
    due: list[ReminderNotification] = []
    for appointment in appointments:
        if appointment.status not in _REMINDABLE_STATUSES:
            continue
        for policy in policies:
            if (appointment.id, policy.id) in already_sent:
                continue
            fires_at = appointment.starts_at - policy.lead_time
            if fires_at <= now < appointment.starts_at:
                due.append(ReminderNotification(
                    appointment_id=appointment.id, policy_id=policy.id,
                    resource_id=appointment.resource_id, service_id=appointment.service_id,
                    client_id=appointment.client_id, starts_at=appointment.starts_at,
                ))
    return due
