from datetime import date, datetime, time, timedelta

import pytest

from libragenda import Appointment, AppointmentStatus, Availability
from libragenda.scheduling import (
    AvailabilityException,
    TimeBlock,
    find_conflicts,
    intervals_overlap,
    is_appointment_available,
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
