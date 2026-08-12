from datetime import date, datetime, time, timedelta

import pytest

from libragenda import Appointment, AppointmentStatus, Availability, Holiday, Resource
from libragenda.scheduling import (
    AgendaPolicy,
    AvailabilityException,
    BranchMismatch,
    TimeBlock,
    check_resource_branch,
    find_conflicts,
    intervals_overlap,
    is_appointment_available,
    policy_for,
)


def appointment(identifier, hour=10, duration=60, status=AppointmentStatus.CONFIRMED):
    return Appointment(identifier, "resource-1", "service-1", "client-1",
                       datetime(2026, 7, 20, hour), timedelta(minutes=duration), status)


def test_intervals_touching_at_boundary_do_not_overlap():
    start = datetime(2026, 7, 20, 10)
    assert not intervals_overlap(start, start + timedelta(hours=1),
                                 start + timedelta(hours=1), start + timedelta(hours=2))


def test_find_conflicts_ignores_other_resources_cancelled_and_no_show():
    target = appointment("target")
    assert find_conflicts(target, [
        appointment("target"),
        appointment("other", status=AppointmentStatus.CANCELLED),
        appointment("no-show", status=AppointmentStatus.NO_SHOW),
        Appointment("different", "resource-2", "service-1", "client-1",
                    target.starts_at, timedelta(minutes=30)),
    ]) == []  # same id is excluded and all others are ineligible


def test_find_conflicts_returns_overlapping_active_appointment():
    target = appointment("target")
    conflict = appointment("conflict", hour=10, duration=30)
    assert find_conflicts(target, [conflict]) == [conflict]


def test_weekly_window_and_block_control_availability():
    target = appointment("target")
    window = Availability("resource-1", 0, time(9), time(18))
    block = TimeBlock("resource-1", datetime(2026, 7, 20, 10, 30), datetime(2026, 7, 20, 11, 30))
    assert not is_appointment_available(target, [window], [block])
    assert is_appointment_available(appointment("early", hour=9), [window], [block])


def test_date_exception_can_close_or_open_a_window():
    target = appointment("target")
    window = Availability("resource-1", 0, time(9), time(18))
    closed = AvailabilityException("resource-1", date(2026, 7, 20), time(9), time(18))
    assert not is_appointment_available(target, [window], exceptions=[closed])
    outside = appointment("outside", hour=19)
    opened = AvailabilityException("resource-1", date(2026, 7, 20), time(19), time(20), True)
    assert is_appointment_available(outside, [window], exceptions=[opened])


@pytest.mark.parametrize("factory", [
    lambda: TimeBlock("resource", datetime(2026, 7, 20, 10), datetime(2026, 7, 20, 10)),
    lambda: AvailabilityException("resource", date.today(), time(10), time(10)),
])
def test_scheduling_rules_reject_invalid_intervals(factory):
    with pytest.raises(ValueError):
        factory()


def test_branch_holiday_closes_resource_even_within_weekly_window():
    target = appointment("target")
    window = Availability("resource-1", 0, time(9), time(18))
    resources = [Resource("resource-1", "Box 1", branch_id="branch-1")]
    holidays = [Holiday("branch-1", date(2026, 7, 20), "Feriado")]
    assert not is_appointment_available(target, [window], holidays=holidays, resources=resources)


def test_resource_exception_overrides_a_branch_holiday():
    target = appointment("target")
    window = Availability("resource-1", 0, time(9), time(18))
    resources = [Resource("resource-1", "Box 1", branch_id="branch-1")]
    holidays = [Holiday("branch-1", date(2026, 7, 20), "Feriado")]
    reopened = AvailabilityException("resource-1", date(2026, 7, 20), time(9), time(18), True)
    assert is_appointment_available(
        target, [window], holidays=holidays, resources=resources, exceptions=[reopened]
    )


def test_holiday_does_not_affect_a_resource_without_a_branch():
    target = appointment("target")
    window = Availability("resource-1", 0, time(9), time(18))
    resources = [Resource("resource-1", "Box 1")]
    holidays = [Holiday("branch-1", date(2026, 7, 20), "Feriado")]
    assert is_appointment_available(target, [window], holidays=holidays, resources=resources)


def test_check_resource_branch_is_noop_without_a_branch_scoped_appointment():
    target = appointment("target")
    check_resource_branch(target, Resource("resource-1", "Box 1", branch_id="other-branch"))


def test_check_resource_branch_rejects_mismatched_branch():
    scoped = Appointment("apt", "resource-1", "service-1", "client-1",
                         datetime(2026, 7, 20, 10), timedelta(minutes=30),
                         branch_id="branch-1")
    with pytest.raises(BranchMismatch):
        check_resource_branch(scoped, Resource("resource-1", "Box 1", branch_id="branch-2"))


def test_check_resource_branch_rejects_resource_without_any_branch():
    scoped = Appointment("apt", "resource-1", "service-1", "client-1",
                         datetime(2026, 7, 20, 10), timedelta(minutes=30),
                         branch_id="branch-1")
    with pytest.raises(BranchMismatch):
        check_resource_branch(scoped, Resource("resource-1", "Box 1"))


# -- shared secondary resources --------------------------------------------


def booking(identifier, resource_id, hour=10, duration=60, secondary=()):
    return Appointment(identifier, resource_id, "service-1", "client-1",
                       datetime(2026, 7, 20, hour), timedelta(minutes=duration),
                       AppointmentStatus.CONFIRMED, secondary_resource_ids=secondary)


def test_two_professionals_sharing_a_room_conflict():
    booked = booking("first", "doctor-1", secondary=("room-2",))
    candidate = booking("second", "doctor-9", secondary=("room-2",))

    assert find_conflicts(candidate, [booked]) == [booked]


def test_same_professional_in_different_rooms_still_conflicts():
    # The primary resource alone is enough: a person cannot be in two places.
    booked = booking("first", "doctor-1", secondary=("room-2",))
    candidate = booking("second", "doctor-1", secondary=("room-8",))

    assert find_conflicts(candidate, [booked]) == [booked]


def test_different_professionals_in_different_rooms_do_not_conflict():
    booked = booking("first", "doctor-1", secondary=("room-2",))
    candidate = booking("second", "doctor-9", secondary=("room-8",))

    assert find_conflicts(candidate, [booked]) == []


def test_a_room_alone_is_enough_to_conflict_even_without_the_other_side_declaring_it():
    # One booking takes the room as a secondary resource, the other has it as
    # its primary one — the engine does not care which slot it sits in.
    booked = booking("first", "doctor-1", secondary=("room-2",))
    candidate = booking("second", "room-2")

    assert find_conflicts(candidate, [booked]) == [booked]


# -- the gap between appointments ------------------------------------------


def test_back_to_back_appointments_are_fine_without_a_gap():
    booked = booking("first", "doctor-1", hour=10, duration=60)
    candidate = booking("second", "doctor-1", hour=11, duration=60)

    assert find_conflicts(candidate, [booked]) == []


def test_a_gap_rejects_an_appointment_that_merely_touches_the_previous_one():
    booked = booking("first", "doctor-1", hour=10, duration=60)
    candidate = booking("second", "doctor-1", hour=11, duration=60)

    assert find_conflicts(candidate, [booked], gap=timedelta(minutes=10)) == [booked]


def test_a_gap_accepts_an_appointment_that_clears_it():
    booked = booking("first", "doctor-1", hour=10, duration=60)
    candidate = booking("second", "doctor-1", hour=11, duration=60)
    candidate = Appointment(
        candidate.id, candidate.resource_id, candidate.service_id, candidate.client_id,
        datetime(2026, 7, 20, 11, 10), candidate.duration, candidate.status,
    )

    assert find_conflicts(candidate, [booked], gap=timedelta(minutes=10)) == []


# -- blocks reach every occupied resource ----------------------------------


def test_a_blocked_room_makes_the_appointment_unavailable():
    windows = [Availability("doctor-1", 0, time(9), time(18))]
    maintenance = TimeBlock("room-2", datetime(2026, 7, 20, 9), datetime(2026, 7, 20, 13),
                            reason="mantenimiento")
    candidate = booking("apt", "doctor-1", secondary=("room-2",))

    assert not is_appointment_available(candidate, windows, blocks=[maintenance])


def test_a_secondary_resource_needs_no_weekly_window_of_its_own():
    # Only the professional has opening hours; the room is a thing, not a
    # schedule. If this ever required a window for the room, every booking
    # with a room would be unavailable.
    windows = [Availability("doctor-1", 0, time(9), time(18))]
    candidate = booking("apt", "doctor-1", secondary=("room-2",))

    assert is_appointment_available(candidate, windows)


# -- agenda policies --------------------------------------------------------


def test_policy_for_falls_back_to_a_permissive_default():
    policy = policy_for("doctor-1", [AgendaPolicy("doctor-9", timedelta(minutes=10), 3)])

    assert policy.resource_id == "doctor-1"
    assert policy.slot_interval == timedelta(0)
    assert policy.max_overbookings_per_day == 0


def test_policy_for_finds_the_matching_resource():
    policy = policy_for("doctor-1", [AgendaPolicy("doctor-1", timedelta(minutes=10), 3)])

    assert policy.max_overbookings_per_day == 3


@pytest.mark.parametrize("factory", [
    lambda: AgendaPolicy(" "),
    lambda: AgendaPolicy("doctor-1", slot_interval=timedelta(minutes=-1)),
    lambda: AgendaPolicy("doctor-1", max_overbookings_per_day=-1),
])
def test_agenda_policy_rejects_invalid_values(factory):
    with pytest.raises(ValueError):
        factory()
