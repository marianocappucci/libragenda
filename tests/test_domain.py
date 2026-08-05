from datetime import date, datetime, time, timedelta, timezone

import pytest

from libragenda.domain import (
    Appointment,
    AppointmentStatus,
    AppointmentTransition,
    Availability,
    Branch,
    Holiday,
    Resource,
    Service,
    first_time_at,
)


def test_service_and_appointment_compose_with_service_duration():
    service = Service("svc-1", "Corte", timedelta(minutes=45))
    appointment = Appointment(
        "apt-1", "resource-1", service.id, "client-1",
        datetime(2026, 7, 20, 10, 0), service.duration,
    )

    assert appointment.ends_at == datetime(2026, 7, 20, 10, 45)
    assert appointment.status is AppointmentStatus.PENDING


def test_availability_contains_interval():
    window = Availability("resource-1", 0, time(9), time(18))

    assert window.contains(datetime(2026, 7, 20, 10), datetime(2026, 7, 20, 10, 45))
    assert not window.contains(datetime(2026, 7, 20, 17, 30), datetime(2026, 7, 20, 18, 15))


def test_branch_defaults_to_utc_and_validates_timezone():
    assert Branch("branch-1", "Centro").timezone == "UTC"
    Branch("branch-1", "Centro", timezone="America/Argentina/Buenos_Aires")


def test_holiday_belongs_to_a_branch_and_a_day():
    holiday = Holiday("branch-1", date(2026, 12, 25), "Navidad")
    assert holiday.branch_id == "branch-1"
    assert holiday.day == date(2026, 12, 25)


def test_appointment_branch_id_is_optional_but_not_blank_when_given():
    with_branch = Appointment(
        "apt", "resource", "svc", "client", datetime.now(), timedelta(minutes=1),
        branch_id="branch-1",
    )
    assert with_branch.branch_id == "branch-1"


def test_appointment_series_id_is_optional_but_not_blank_when_given():
    occurrence = Appointment(
        "apt", "resource", "svc", "client", datetime.now(), timedelta(minutes=1),
        series_id="series-1",
    )
    assert occurrence.series_id == "series-1"


def test_appointment_reason_is_optional_but_not_blank_when_given():
    cancelled = Appointment(
        "apt", "resource", "svc", "client", datetime.now(), timedelta(minutes=1),
        reason="cliente no puede asistir",
    )
    assert cancelled.reason == "cliente no puede asistir"


@pytest.mark.parametrize("factory", [
    lambda: Resource("", "Profesional"),
    lambda: Service("svc", "Corte", timedelta(0)),
    lambda: Availability("resource", 7, time(9), time(18)),
    lambda: Appointment("apt", "resource", "svc", "client", datetime.now(), timedelta(0)),
    lambda: Appointment("apt", "resource", "svc", "client", datetime.now(), timedelta(minutes=1), branch_id="  "),
    lambda: Appointment("apt", "resource", "svc", "client", datetime.now(), timedelta(minutes=1), series_id="  "),
    lambda: Appointment("apt", "resource", "svc", "client", datetime.now(), timedelta(minutes=1), reason="  "),
    lambda: Branch("branch", "Centro", timezone="Not/A_Zone"),
    lambda: Holiday("", date(2026, 12, 25), "Navidad"),
    lambda: Holiday("branch-1", date(2026, 12, 25), ""),
])
def test_domain_rejects_invalid_values(factory):
    with pytest.raises(ValueError):
        factory()


# -- availability validity -------------------------------------------------


def test_availability_without_validity_applies_on_any_day():
    window = Availability("resource-1", 0, time(9), time(18))

    assert window.applies_on(date(2020, 1, 6))
    assert window.applies_on(date(2030, 1, 7))


def test_availability_applies_only_inside_its_validity():
    window = Availability("resource-1", 0, time(9), time(18),
                          valid_from=date(2026, 7, 1), valid_to=date(2026, 7, 31))

    assert not window.applies_on(date(2026, 6, 30))
    assert window.applies_on(date(2026, 7, 1))
    assert window.applies_on(date(2026, 7, 31))
    assert not window.applies_on(date(2026, 8, 1))


def test_availability_bounds_are_independently_optional():
    open_ended = Availability("resource-1", 0, time(9), time(18), valid_from=date(2026, 7, 1))
    already_closed = Availability("resource-1", 0, time(9), time(18), valid_to=date(2026, 7, 31))

    assert open_ended.applies_on(date(2030, 1, 1))
    assert not open_ended.applies_on(date(2026, 6, 30))
    assert already_closed.applies_on(date(2020, 1, 1))
    assert not already_closed.applies_on(date(2026, 8, 1))


def test_contains_respects_validity():
    # 2026-07-20 is a Monday, inside the weekly window but past the validity.
    window = Availability("resource-1", 0, time(9), time(18), valid_to=date(2026, 7, 19))

    assert not window.contains(datetime(2026, 7, 20, 10), datetime(2026, 7, 20, 11))


def test_availability_rejects_validity_that_ends_before_it_starts():
    with pytest.raises(ValueError):
        Availability("resource-1", 0, time(9), time(18),
                     valid_from=date(2026, 7, 31), valid_to=date(2026, 7, 1))


# -- secondary resources ---------------------------------------------------


def make_domain_appointment(secondary=()):
    return Appointment("apt-1", "resource-1", "service-1", "client-1",
                       datetime(2026, 7, 20, 10), timedelta(minutes=30),
                       secondary_resource_ids=secondary)


def test_occupied_resource_ids_lists_the_primary_first():
    assert make_domain_appointment(("room-2", "room-3")).occupied_resource_ids == (
        "resource-1", "room-2", "room-3",
    )


def test_appointment_without_secondary_resources_occupies_only_its_own():
    assert make_domain_appointment().occupied_resource_ids == ("resource-1",)


@pytest.mark.parametrize("secondary", [
    ("  ",),
    ("room-2", "room-2"),
    ("resource-1",),
])
def test_appointment_rejects_invalid_secondary_resources(secondary):
    with pytest.raises(ValueError):
        make_domain_appointment(secondary)


# -- transition history ----------------------------------------------------


def test_first_time_at_returns_the_earliest_occurrence():
    transitions = [
        AppointmentTransition("apt-1", AppointmentStatus.IN_PROGRESS,
                              datetime(2026, 7, 20, 10, 18, tzinfo=timezone.utc)),
        AppointmentTransition("apt-1", AppointmentStatus.PENDING,
                              datetime(2026, 7, 1, 9, tzinfo=timezone.utc)),
        AppointmentTransition("apt-1", AppointmentStatus.COMPLETED,
                              datetime(2026, 7, 20, 10, 41, tzinfo=timezone.utc)),
    ]

    started = first_time_at(transitions, AppointmentStatus.IN_PROGRESS)
    finished = first_time_at(transitions, AppointmentStatus.COMPLETED)

    assert started == datetime(2026, 7, 20, 10, 18, tzinfo=timezone.utc)
    # 23 minutes of real attention, read from the log and not from a column.
    assert finished - started == timedelta(minutes=23)


def test_first_time_at_is_none_for_a_status_never_reached():
    transitions = [AppointmentTransition("apt-1", AppointmentStatus.PENDING,
                                         datetime(2026, 7, 1, 9, tzinfo=timezone.utc))]

    assert first_time_at(transitions, AppointmentStatus.COMPLETED) is None


def test_transition_rejects_a_naive_timestamp():
    with pytest.raises(ValueError):
        AppointmentTransition("apt-1", AppointmentStatus.PENDING, datetime(2026, 7, 1, 9))
