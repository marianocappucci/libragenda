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
])
def test_deposit_rejects_invalid_values(factory):
    with pytest.raises(ValueError):
        factory()
