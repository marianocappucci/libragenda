from datetime import datetime, time, timedelta

import pytest

from libragenda.domain import (
    Appointment,
    AppointmentStatus,
    Availability,
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


@pytest.mark.parametrize("factory", [
    lambda: Resource("", "Profesional"),
    lambda: Service("svc", "Corte", timedelta(0)),
    lambda: Availability("resource", 7, time(9), time(18)),
    lambda: Appointment("apt", "resource", "svc", "client", datetime.now(), timedelta(0)),
])
def test_domain_rejects_invalid_values(factory):
    with pytest.raises(ValueError):
        factory()
