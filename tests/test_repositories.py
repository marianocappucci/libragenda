from datetime import datetime, timedelta

import pytest

from libragenda import Appointment, InMemoryAppointmentRepository


def make_appointment(identifier="apt-1"):
    return Appointment(identifier, "resource-1", "service-1", "client-1",
                       datetime(2026, 7, 20, 10), timedelta(minutes=30))


def test_in_memory_repository_add_get_save_and_list():
    repository = InMemoryAppointmentRepository()
    appointment = make_appointment()
    repository.add(appointment)
    assert repository.get(appointment.id) == appointment
    updated = make_appointment()
    repository.save(updated)
    assert tuple(repository.list()) == (updated,)


def test_in_memory_repository_rejects_duplicate_and_unknown_save():
    repository = InMemoryAppointmentRepository()
    repository.add(make_appointment())
    with pytest.raises(ValueError):
        repository.add(make_appointment())
    with pytest.raises(KeyError):
        repository.save(make_appointment("missing"))
