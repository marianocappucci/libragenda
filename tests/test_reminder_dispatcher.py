from datetime import datetime, timedelta

from libragenda import (
    Appointment,
    InMemoryAppointmentRepository,
    InMemorySentReminderRepository,
    ReminderDispatcher,
    ReminderPolicy,
)


class FakeNotificationPort:
    def __init__(self) -> None:
        self.sent = []

    def send(self, notification) -> None:
        self.sent.append(notification)


def make_dispatcher(policies=None):
    appointments = InMemoryAppointmentRepository()
    reminders = InMemorySentReminderRepository()
    port = FakeNotificationPort()
    dispatcher = ReminderDispatcher(
        appointments, reminders, port,
        policies or [ReminderPolicy("24h", timedelta(hours=24))],
    )
    return dispatcher, appointments, reminders, port


def test_dispatch_sends_due_reminders_and_records_them():
    dispatcher, appointments, reminders, port = make_dispatcher()
    target = Appointment("apt-1", "resource-1", "service-1", "client-1",
                         datetime(2026, 7, 20, 10), timedelta(minutes=45))
    appointments.add(target)

    due = dispatcher.dispatch(now=target.starts_at - timedelta(hours=24))

    assert len(due) == 1
    assert len(port.sent) == 1
    assert reminders.sent_pairs(["apt-1"]) == {("apt-1", "24h")}


def test_dispatch_does_not_resend_on_a_second_run():
    dispatcher, appointments, reminders, port = make_dispatcher()
    target = Appointment("apt-1", "resource-1", "service-1", "client-1",
                         datetime(2026, 7, 20, 10), timedelta(minutes=45))
    appointments.add(target)
    now = target.starts_at - timedelta(hours=24)

    dispatcher.dispatch(now=now)
    second_run = dispatcher.dispatch(now=now + timedelta(minutes=5))

    assert second_run == []
    assert len(port.sent) == 1
