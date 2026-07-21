from datetime import date, datetime, time, timedelta

import pytest

from libragenda.domain import (
    Appointment,
    AppointmentStatus,
    Availability,
    Branch,
    Holiday,
    Resource,
    Service,
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
