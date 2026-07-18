from decimal import Decimal

import pytest

from libragenda import (
    DepositError,
    DepositManager,
    DepositNotFound,
    DepositStatus,
    InMemoryDepositRepository,
    InvalidDepositTransition,
)


class FakePaymentPort:
    def __init__(self) -> None:
        self.charges = []
        self.refunds = []

    def request_charge(self, deposit) -> None:
        self.charges.append(deposit)

    def request_refund(self, deposit) -> None:
        self.refunds.append(deposit)


@pytest.fixture
def manager():
    return DepositManager(InMemoryDepositRepository(), FakePaymentPort())


def test_request_creates_pending_deposit_and_requests_charge(manager):
    deposit = manager.request("dep-1", "apt-1", Decimal("500.00"))
    assert deposit.status is DepositStatus.PENDING
    assert manager.payment_port.charges == [deposit]


def test_mark_paid_then_refund_requests_a_refund(manager):
    manager.request("dep-1", "apt-1", Decimal("500.00"))
    paid = manager.mark_paid("dep-1")
    assert paid.status is DepositStatus.PAID

    refunded = manager.request_refund("dep-1")
    assert refunded.status is DepositStatus.REFUNDED
    assert len(manager.payment_port.refunds) == 1


def test_mark_failed_is_terminal(manager):
    manager.request("dep-1", "apt-1", Decimal("500.00"))
    failed = manager.mark_failed("dep-1")
    assert failed.status is DepositStatus.FAILED
    with pytest.raises(InvalidDepositTransition):
        manager.mark_paid("dep-1")


def test_cannot_refund_a_pending_deposit(manager):
    manager.request("dep-1", "apt-1", Decimal("500.00"))
    with pytest.raises(InvalidDepositTransition):
        manager.request_refund("dep-1")
    assert manager.payment_port.refunds == []


def test_operations_on_unknown_deposit_raise_not_found(manager):
    with pytest.raises(DepositNotFound):
        manager.mark_paid("missing")


def test_appointment_can_only_have_one_deposit(manager):
    manager.request("dep-1", "apt-1", Decimal("500.00"))
    with pytest.raises(DepositError):
        manager.request("dep-2", "apt-1", Decimal("100.00"))
