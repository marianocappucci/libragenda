from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from libragenda import Appointment, AppointmentStatus
from libragenda.sqlalchemy_repository import Base, SqlAlchemyAppointmentRepository


def test_sqlalchemy_repository_round_trips_appointments():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = SqlAlchemyAppointmentRepository(sessionmaker(engine, expire_on_commit=False))
    appointment = Appointment("apt-1", "resource-1", "service-1", "client-1",
                              datetime(2026, 7, 20, 10), timedelta(minutes=45))

    repository.add(appointment)
    assert repository.get("apt-1") == appointment
    updated = Appointment("apt-1", "resource-1", "service-1", "client-1",
                           appointment.starts_at, appointment.duration, AppointmentStatus.CONFIRMED,
                           branch_id="branch-1")
    repository.save(updated)
    assert repository.get("apt-1") == updated
    assert repository.get("apt-1").branch_id == "branch-1"
    assert repository.list() == (updated,)
