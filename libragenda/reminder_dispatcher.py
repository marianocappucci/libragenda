"""Wires the reminder rule, the sent-reminder ledger and the outbound port."""

from datetime import datetime

from .notifications import NotificationPort, ReminderNotification, ReminderPolicy, due_reminders
from .repositories import AppointmentRepository, SentReminderRepository


class ReminderDispatcher:
    """Application service: find due reminders, send them, record them sent."""

    def __init__(
        self,
        appointment_repository: AppointmentRepository,
        reminder_repository: SentReminderRepository,
        notification_port: NotificationPort,
        policies: list[ReminderPolicy],
    ) -> None:
        self.appointment_repository = appointment_repository
        self.reminder_repository = reminder_repository
        self.notification_port = notification_port
        self.policies = policies

    def dispatch(self, now: datetime) -> list[ReminderNotification]:
        appointments = list(self.appointment_repository.list())
        already_sent = self.reminder_repository.sent_pairs([item.id for item in appointments])
        due = due_reminders(appointments, self.policies, now, already_sent)
        for notification in due:
            self.notification_port.send(notification)
            self.reminder_repository.mark_sent(notification.appointment_id, notification.policy_id, now)
        return due
