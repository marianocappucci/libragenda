"""Deposits and the outbound payment port.

Per MODULES.md, LibraGenda only tracks deposit state and exposes a port to
request a charge/refund — provider integration (MercadoPago, Stripe, cash)
and any confirm-on-webhook flow belong to the vertical's PaymentPort
implementation. The engine never gates Appointment transitions on deposit
state; a vertical that wants "no seña, no confirmación" enforces that
itself by checking DepositManager before calling InMemoryScheduler.confirm.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class DepositStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


@dataclass(frozen=True, slots=True)
class Deposit:
    """A single deposit/anticipo tied to one appointment."""

    id: str
    appointment_id: str
    amount: Decimal
    status: DepositStatus = DepositStatus.PENDING
    medio_pago: str | None = None
    """Free-text payment method (e.g. 'efectivo', 'transferencia',
    'mercadopago'), set by the caller once the deposit is marked paid. The
    engine never validates its content or maps it to any provider — that's
    vertical-specific (same treatment as Appointment.reason)."""

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("deposit id cannot be empty")
        if not self.appointment_id.strip():
            raise ValueError("deposit appointment_id cannot be empty")
        if self.amount <= 0:
            raise ValueError("deposit amount must be positive")
        if self.medio_pago is not None and not self.medio_pago.strip():
            raise ValueError("medio_pago cannot be blank when provided")


class PaymentPort(Protocol):
    """Outbound port a vertical implements to actually move money."""

    def request_charge(self, deposit: Deposit) -> None: ...

    def request_refund(self, deposit: Deposit) -> None: ...
