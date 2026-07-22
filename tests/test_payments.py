from decimal import Decimal

import pytest

from libragenda.payments import Deposit, DepositStatus


def test_deposit_defaults_to_pending():
    deposit = Deposit("dep-1", "apt-1", Decimal("500.00"))
    assert deposit.status is DepositStatus.PENDING


@pytest.mark.parametrize("factory", [
    lambda: Deposit("", "apt-1", Decimal("500.00")),
    lambda: Deposit("dep-1", "", Decimal("500.00")),
    lambda: Deposit("dep-1", "apt-1", Decimal("0")),
    lambda: Deposit("dep-1", "apt-1", Decimal("-1")),
    lambda: Deposit("dep-1", "apt-1", Decimal("500.00"), medio_pago="   "),
])
def test_deposit_rejects_invalid_values(factory):
    with pytest.raises(ValueError):
        factory()


def test_deposit_accepts_an_optional_medio_pago():
    deposit = Deposit("dep-1", "apt-1", Decimal("500.00"), medio_pago="efectivo")
    assert deposit.medio_pago == "efectivo"
