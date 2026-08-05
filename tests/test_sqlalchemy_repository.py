from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from libragenda import Appointment, AppointmentStatus, AppointmentTransition, first_time_at
from libragenda.sqlalchemy_repository import (
    Base,
    SqlAlchemyAppointmentRepository,
    SqlAlchemyTransitionLog,
)


def test_sqlalchemy_repository_round_trips_appointments():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = SqlAlchemyAppointmentRepository(sessionmaker(engine, expire_on_commit=False))
    # DateTime(timezone=True) always round-trips as aware — even on SQLite,
    # which has no native tz type (see sqlalchemy_repository.ensure_utc) —
    # so the domain object under comparison must start out aware too.
    appointment = Appointment("apt-1", "resource-1", "service-1", "client-1",
                              datetime(2026, 7, 20, 10, tzinfo=timezone.utc), timedelta(minutes=45))

    repository.add(appointment)
    assert repository.get("apt-1") == appointment
    updated = Appointment("apt-1", "resource-1", "service-1", "client-1",
                           appointment.starts_at, appointment.duration, AppointmentStatus.CONFIRMED,
                           branch_id="branch-1", series_id="series-1")
    repository.save(updated)
    assert repository.get("apt-1") == updated
    assert repository.get("apt-1").branch_id == "branch-1"
    assert repository.get("apt-1").series_id == "series-1"
    assert repository.list() == (updated,)

    cancelled = Appointment("apt-1", "resource-1", "service-1", "client-1",
                             appointment.starts_at, appointment.duration, AppointmentStatus.CANCELLED,
                             branch_id="branch-1", series_id="series-1", reason="cliente no puede asistir")
    repository.save(cancelled)
    assert repository.get("apt-1").reason == "cliente no puede asistir"


def make_repository():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlAlchemyAppointmentRepository(sessionmaker(engine, expire_on_commit=False))


def booked(secondary=(), overbooked=False):
    return Appointment("apt-1", "doctor-1", "service-1", "client-1",
                       datetime(2026, 7, 20, 10, tzinfo=timezone.utc), timedelta(minutes=45),
                       secondary_resource_ids=secondary, overbooked=overbooked)


def test_secondary_resources_and_overbooking_round_trip():
    repository = make_repository()
    appointment = booked(secondary=("room-2", "equipo-7"), overbooked=True)

    repository.add(appointment)

    stored = repository.get("apt-1")
    assert stored == appointment
    # Order is preserved, which is why the join table carries a position.
    assert stored.secondary_resource_ids == ("room-2", "equipo-7")
    assert stored.overbooked is True


def test_saving_without_a_secondary_resource_releases_it():
    repository = make_repository()
    repository.add(booked(secondary=("room-2", "equipo-7")))

    repository.save(booked(secondary=("room-2",)))

    # If the removed row survived, the equipment would stay busy forever.
    assert repository.get("apt-1").secondary_resource_ids == ("room-2",)


def test_an_appointment_without_secondary_resources_round_trips_empty():
    repository = make_repository()
    repository.add(booked())

    assert repository.get("apt-1").secondary_resource_ids == ()
    assert repository.get("apt-1").overbooked is False


def test_transition_log_round_trips_in_chronological_order():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    log = SqlAlchemyTransitionLog(sessionmaker(engine, expire_on_commit=False))
    started = datetime(2026, 7, 20, 10, 18, tzinfo=timezone.utc)
    log.record(AppointmentTransition("apt-1", AppointmentStatus.COMPLETED,
                                     datetime(2026, 7, 20, 10, 41, tzinfo=timezone.utc),
                                     from_status=AppointmentStatus.IN_PROGRESS,
                                     actor="dr-perez"))
    log.record(AppointmentTransition("apt-1", AppointmentStatus.IN_PROGRESS, started,
                                     from_status=AppointmentStatus.CONFIRMED,
                                     actor="dr-perez"))
    log.record(AppointmentTransition("apt-2", AppointmentStatus.PENDING, started))

    history = log.list_for("apt-1")

    assert [item.to_status for item in history] == [
        AppointmentStatus.IN_PROGRESS, AppointmentStatus.COMPLETED,
    ]
    assert history[0].from_status is AppointmentStatus.CONFIRMED
    assert history[0].actor == "dr-perez"
    assert first_time_at(history, AppointmentStatus.IN_PROGRESS) == started


def test_transition_log_keeps_a_creation_entry_without_a_previous_status():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    log = SqlAlchemyTransitionLog(sessionmaker(engine, expire_on_commit=False))
    log.record(AppointmentTransition("apt-1", AppointmentStatus.PENDING,
                                     datetime(2026, 7, 1, 9, tzinfo=timezone.utc)))

    assert log.list_for("apt-1")[0].from_status is None
