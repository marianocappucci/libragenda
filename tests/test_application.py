from datetime import date, datetime, time, timedelta

import pytest

from libragenda import (
    Appointment,
    AppointmentConflict,
    AppointmentStatus,
    AppointmentUnavailable,
    Availability,
    Holiday,
    InMemoryScheduler,
    InvalidTransition,
    Resource,
    ResourceBranchMismatch,
)


def make_appointment(identifier="apt-1", hour=10, status=AppointmentStatus.PENDING, branch_id=None):
    return Appointment(identifier, "resource-1", "service-1", "client-1",
                       datetime(2026, 7, 20, hour), timedelta(minutes=45), status,
                       branch_id=branch_id)


@pytest.fixture
def scheduler():
    return InMemoryScheduler([Availability("resource-1", 0, time(9), time(18))])


def test_create_confirm_and_cancel(scheduler):
    created = scheduler.create(make_appointment())
    assert created.status is AppointmentStatus.PENDING
    assert scheduler.confirm(created.id).status is AppointmentStatus.CONFIRMED
    assert scheduler.cancel(created.id).status is AppointmentStatus.CANCELLED


def test_create_rejects_conflict(scheduler):
    scheduler.create(make_appointment("first"))
    with pytest.raises(AppointmentConflict):
        scheduler.create(make_appointment("second"))


def test_create_rejects_unavailable_slot(scheduler):
    with pytest.raises(AppointmentUnavailable):
        scheduler.create(make_appointment(hour=19))


def test_reschedule_validates_new_slot(scheduler):
    scheduler.create(make_appointment())
    moved = scheduler.reschedule("apt-1", datetime(2026, 7, 20, 12))
    assert moved.starts_at.hour == 12


def test_cancelled_appointment_cannot_be_rescheduled_or_confirmed(scheduler):
    scheduler.create(make_appointment())
    scheduler.cancel("apt-1")
    with pytest.raises(InvalidTransition):
        scheduler.reschedule("apt-1", datetime(2026, 7, 20, 12))
    with pytest.raises(InvalidTransition):
        scheduler.confirm("apt-1")


def test_confirmed_appointment_cannot_be_confirmed_again(scheduler):
    scheduler.create(make_appointment())
    scheduler.confirm("apt-1")
    with pytest.raises(InvalidTransition):
        scheduler.confirm("apt-1")


def test_create_rejects_appointment_on_a_branch_holiday():
    scheduler = InMemoryScheduler(
        [Availability("resource-1", 0, time(9), time(18))],
        holidays=[Holiday("branch-1", date(2026, 7, 20), "Feriado")],
        resources=[Resource("resource-1", "Box 1", branch_id="branch-1")],
    )
    with pytest.raises(AppointmentUnavailable):
        scheduler.create(make_appointment())


def test_create_rejects_resource_from_a_different_branch():
    scheduler = InMemoryScheduler(
        [Availability("resource-1", 0, time(9), time(18))],
        resources=[Resource("resource-1", "Box 1", branch_id="branch-2")],
    )
    with pytest.raises(ResourceBranchMismatch):
        scheduler.create(make_appointment(branch_id="branch-1"))


def test_reschedule_preserves_branch_id_and_still_enforces_it():
    scheduler = InMemoryScheduler(
        [Availability("resource-1", 0, time(9), time(18))],
        resources=[Resource("resource-1", "Box 1", branch_id="branch-1")],
    )
    scheduler.create(make_appointment(branch_id="branch-1"))
    moved = scheduler.reschedule("apt-1", datetime(2026, 7, 20, 12))
    assert moved.branch_id == "branch-1"
