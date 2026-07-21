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
    RecurrenceRule,
    Resource,
    ResourceBranchMismatch,
    generate_occurrences,
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


def test_cancel_accepts_an_optional_reason(scheduler):
    scheduler.create(make_appointment())
    cancelled = scheduler.cancel("apt-1", reason="cliente no puede asistir")
    assert cancelled.reason == "cliente no puede asistir"


def test_reschedule_accepts_an_optional_reason_and_preserves_it_if_omitted(scheduler):
    scheduler.create(make_appointment())
    moved = scheduler.reschedule("apt-1", datetime(2026, 7, 20, 12), reason="pidio otro horario")
    assert moved.reason == "pidio otro horario"
    moved_again = scheduler.reschedule("apt-1", datetime(2026, 7, 20, 13))
    assert moved_again.reason == "pidio otro horario"


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


def _create_series(scheduler: InMemoryScheduler, series_id: str, count: int) -> list[Appointment]:
    rule = RecurrenceRule(weekdays=frozenset({0}), start_time=time(10, 0),
                          starts_on=date(2026, 7, 20), count=count)
    created = []
    for index, occurrence in enumerate(generate_occurrences(rule)):
        appointment = Appointment(
            f"apt-{index}", "resource-1", "service-1", "client-1",
            occurrence, timedelta(minutes=45), series_id=series_id,
        )
        created.append(scheduler.create(appointment))
    return created


def test_list_series_returns_only_matching_occurrences(scheduler):
    _create_series(scheduler, "series-1", count=3)
    scheduler.create(make_appointment("standalone", hour=14))
    assert len(scheduler.list_series("series-1")) == 3


def test_cancel_series_cancels_every_pending_occurrence(scheduler):
    _create_series(scheduler, "series-1", count=3)
    cancelled = scheduler.cancel_series("series-1")
    assert len(cancelled) == 3
    assert all(item.status is AppointmentStatus.CANCELLED for item in cancelled)


def test_cancel_series_applies_the_same_reason_to_every_occurrence(scheduler):
    _create_series(scheduler, "series-1", count=2)
    cancelled = scheduler.cancel_series("series-1", reason="profesional de licencia")
    assert all(item.reason == "profesional de licencia" for item in cancelled)


def test_cancel_series_skips_occurrences_already_closed_out(scheduler):
    occurrences = _create_series(scheduler, "series-1", count=2)
    scheduler.confirm(occurrences[0].id)
    scheduler.cancel(occurrences[0].id)  # already cancelled

    cancelled = scheduler.cancel_series("series-1")

    assert len(cancelled) == 1
    assert cancelled[0].id == occurrences[1].id
