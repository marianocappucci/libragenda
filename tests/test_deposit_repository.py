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


def _repos(extra_appointment_ids: tuple[str, ...] = ()):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    appointments = SqlAlchemyAppointmentRepository(session_factory)
    for identifier in ("apt-1", *extra_appointment_ids):
        appointments.add(Appointment(identifier, "resource-1", "service-1", "client-1",
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


def test_deposit_repository_round_trips_medio_pago():
    deposits = _repos()
    deposits.add(Deposit("dep-1", "apt-1", Decimal("500.00")))
    assert deposits.get("dep-1").medio_pago is None

    deposits.save(Deposit("dep-1", "apt-1", Decimal("500.00"), DepositStatus.PAID,
                          medio_pago="mercadopago"))
    assert deposits.get("dep-1").medio_pago == "mercadopago"


def test_deposit_repository_list_by_status():
    deposits = _repos(extra_appointment_ids=("apt-2", "apt-3"))
    deposits.add(Deposit("dep-1", "apt-1", Decimal("500.00")))
    deposits.add(Deposit("dep-2", "apt-2", Decimal("300.00")))
    deposits.add(Deposit("dep-3", "apt-3", Decimal("100.00")))
    deposits.save(Deposit("dep-2", "apt-2", Decimal("300.00"), DepositStatus.PAID))

    pending = deposits.list_by_status(DepositStatus.PENDING)
    assert {item.id for item in pending} == {"dep-1", "dep-3"}

    paid = deposits.list_by_status(DepositStatus.PAID)
    assert {item.id for item in paid} == {"dep-2"}

    assert deposits.list_by_status(DepositStatus.REFUNDED) == []
