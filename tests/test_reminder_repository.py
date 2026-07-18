from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from libragenda import Appointment, SqlAlchemyAppointmentRepository, SqlAlchemyReminderRepository
from libragenda.sqlalchemy_repository import Base


def test_reminder_repository_tracks_sent_pairs_and_is_idempotent():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    appointments = SqlAlchemyAppointmentRepository(session_factory)
    appointments.add(Appointment("apt-1", "resource-1", "service-1", "client-1",
                                 datetime(2026, 7, 20, 10), timedelta(minutes=45)))
    reminders = SqlAlchemyReminderRepository(session_factory)

    assert reminders.sent_pairs(["apt-1"]) == set()

    sent_at = datetime(2026, 7, 19, 10)
    reminders.mark_sent("apt-1", "24h", sent_at)
    assert reminders.sent_pairs(["apt-1"]) == {("apt-1", "24h")}

    reminders.mark_sent("apt-1", "24h", sent_at)  # duplicate call is a no-op
    assert reminders.sent_pairs(["apt-1"]) == {("apt-1", "24h")}


def test_reminder_repository_sent_pairs_filters_by_appointment_ids():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    appointments = SqlAlchemyAppointmentRepository(session_factory)
    for identifier in ("apt-1", "apt-2"):
        appointments.add(Appointment(identifier, "resource-1", "service-1", "client-1",
                                     datetime(2026, 7, 20, 10), timedelta(minutes=45)))
    reminders = SqlAlchemyReminderRepository(session_factory)
    reminders.mark_sent("apt-1", "24h", datetime(2026, 7, 19, 10))
    reminders.mark_sent("apt-2", "24h", datetime(2026, 7, 19, 10))

    assert reminders.sent_pairs(["apt-1"]) == {("apt-1", "24h")}
    assert reminders.sent_pairs([]) == set()
