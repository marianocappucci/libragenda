from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from libragenda import (
    Appointment,
    Deposit,
    DepositStatus,
    SqlAlchemyAppointmentRepository,
    SqlAlchemyDepositRepository,
)
from libragenda.sqlalchemy_repository import Base


def _repos():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    appointments = SqlAlchemyAppointmentRepository(session_factory)
    appointments.add(Appointment("apt-1", "resource-1", "service-1", "client-1",
                                 datetime(2026, 7, 20, 10), timedelta(minutes=45)))
    return SqlAlchemyDepositRepository(session_factory)


def test_deposit_repository_round_trips_and_transitions():
    deposits = _repos()
    deposits.add(Deposit("dep-1", "apt-1", Decimal("500.00")))

    stored = deposits.get("dep-1")
    assert stored.status is DepositStatus.PENDING
    assert stored.amount == Decimal("500.00")
    assert deposits.get_by_appointment("apt-1") == stored

    deposits.save(Deposit("dep-1", "apt-1", Decimal("500.00"), DepositStatus.PAID))
    assert deposits.get("dep-1").status is DepositStatus.PAID


def test_deposit_repository_get_by_appointment_returns_none_when_absent():
    deposits = _repos()
    assert deposits.get_by_appointment("apt-1") is None
