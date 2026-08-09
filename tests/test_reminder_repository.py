from datetime import datetime, timedelta, timezone

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


def test_reminder_repository_list_sent_filters_by_date_range():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    appointments = SqlAlchemyAppointmentRepository(session_factory)
    for identifier in ("apt-1", "apt-2"):
        appointments.add(Appointment(identifier, "resource-1", "service-1", "client-1",
                                     datetime(2026, 7, 20, 10), timedelta(minutes=45)))
    reminders = SqlAlchemyReminderRepository(session_factory)
    reminders.mark_sent("apt-1", "24h", datetime(2026, 7, 19, 10))
    reminders.mark_sent("apt-2", "2h", datetime(2026, 7, 21, 8))

    # `sent_at` vuelve AWARE en UTC, en los dos motores.
    #
    # Esta asercion pedia un datetime naive, que era lo que devolvia SQLite --
    # y solo SQLite. `sent_at` era la unica de las cinco columnas con zona que
    # no pasaba por `ensure_utc` al leer, asi que contra PostgreSQL este mismo
    # repositorio ya devolvia un valor aware desde siempre. O sea que el test
    # no estaba fijando el contrato del repositorio: estaba fijando el
    # comportamiento de un backend. `UtcDateTime` (2026-08-09) los unifico.
    #
    # No rompe a los consumidores: Gestiolibra y MedLibra usan `list_sent`
    # dentro de un `len()`, para contar recordatorios del periodo.
    in_range = reminders.list_sent(datetime(2026, 7, 19, 0), datetime(2026, 7, 19, 23, 59))
    assert in_range == [("apt-1", "24h", datetime(2026, 7, 19, 10, tzinfo=timezone.utc))]

    both = reminders.list_sent(datetime(2026, 7, 1, 0), datetime(2026, 7, 31, 23, 59))
    assert {item[:2] for item in both} == {("apt-1", "24h"), ("apt-2", "2h")}

    none = reminders.list_sent(datetime(2026, 8, 1, 0), datetime(2026, 8, 31, 23, 59))
    assert none == []
