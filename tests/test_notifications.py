from datetime import datetime, timedelta

import pytest

from libragenda import Appointment, AppointmentStatus
from libragenda.notifications import ReminderPolicy, due_reminders


def appointment(identifier="apt-1", hour=10, status=AppointmentStatus.CONFIRMED):
    return Appointment(identifier, "resource-1", "service-1", "client-1",
                       datetime(2026, 7, 20, hour), timedelta(minutes=45), status)


def test_reminder_fires_once_lead_time_window_opens():
    policy = ReminderPolicy("24h", timedelta(hours=24))
    target = appointment()
    now = target.starts_at - timedelta(hours=24)
    due = due_reminders([target], [policy], now, set())
    assert len(due) == 1
    assert due[0].appointment_id == "apt-1"
    assert due[0].policy_id == "24h"


def test_reminder_does_not_fire_before_its_lead_time():
    policy = ReminderPolicy("24h", timedelta(hours=24))
    target = appointment()
    now = target.starts_at - timedelta(hours=25)
    assert due_reminders([target], [policy], now, set()) == []


def test_reminder_does_not_fire_after_appointment_already_started():
    policy = ReminderPolicy("24h", timedelta(hours=24))
    target = appointment()
    now = target.starts_at + timedelta(minutes=1)
    assert due_reminders([target], [policy], now, set()) == []


def test_already_sent_pair_is_skipped():
    policy = ReminderPolicy("24h", timedelta(hours=24))
    target = appointment()
    now = target.starts_at - timedelta(hours=24)
    already_sent = {("apt-1", "24h")}
    assert due_reminders([target], [policy], now, already_sent) == []


def test_cancelled_and_completed_appointments_are_never_reminded():
    policy = ReminderPolicy("24h", timedelta(hours=24))
    now = datetime(2026, 7, 19, 10)
    cancelled = appointment("cancelled", status=AppointmentStatus.CANCELLED)
    completed = appointment("completed", status=AppointmentStatus.COMPLETED)
    assert due_reminders([cancelled, completed], [policy], now, set()) == []


def test_multiple_policies_can_fire_independently_for_the_same_appointment():
    target = appointment()
    policies = [ReminderPolicy("24h", timedelta(hours=24)), ReminderPolicy("1h", timedelta(hours=1))]

    # Only the 24h lead time has opened yet; the 1h one has not.
    only_24h_open = target.starts_at - timedelta(hours=2)
    due = due_reminders([target], policies, only_24h_open, set())
    assert {item.policy_id for item in due} == {"24h"}

    # Once 24h was already sent, only the newly-opened 1h one is due.
    both_open = target.starts_at - timedelta(minutes=30)
    due = due_reminders([target], policies, both_open, {("apt-1", "24h")})
    assert {item.policy_id for item in due} == {"1h"}


@pytest.mark.parametrize("factory", [
    lambda: ReminderPolicy("", timedelta(hours=1)),
    lambda: ReminderPolicy("id", timedelta(0)),
    lambda: ReminderPolicy("id", timedelta(hours=-1)),
])
def test_reminder_policy_rejects_invalid_values(factory):
    with pytest.raises(ValueError):
        factory()
