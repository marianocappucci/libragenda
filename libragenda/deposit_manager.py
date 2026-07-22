"""Application service driving one deposit through its lifecycle."""

from decimal import Decimal

from .payments import Deposit, DepositStatus, PaymentPort
from .repositories import DepositRepository

_ALLOWED_TRANSITIONS = {
    DepositStatus.PENDING: {DepositStatus.PAID, DepositStatus.FAILED},
    DepositStatus.PAID: {DepositStatus.REFUNDED},
    DepositStatus.FAILED: set(),
    DepositStatus.REFUNDED: set(),
}


class DepositError(Exception):
    """Base error for deposit use-case failures."""


class DepositNotFound(DepositError):
    pass


class InvalidDepositTransition(DepositError):
    pass


class DepositManager:
    """Requests a deposit, then drives it through paid/failed/refunded.

    Confirmation of an actual charge/refund is never synchronous here: the
    vertical calls request() to kick off the provider flow, then calls
    mark_paid()/mark_failed()/mark_refunded() once it hears back (webhook,
    polling, whatever the provider's PaymentPort implementation does).
    """

    def __init__(self, repository: DepositRepository, payment_port: PaymentPort) -> None:
        self.repository = repository
        self.payment_port = payment_port

    def request(self, deposit_id: str, appointment_id: str, amount: Decimal) -> Deposit:
        deposit = Deposit(deposit_id, appointment_id, amount)
        try:
            self.repository.add(deposit)
        except ValueError as exc:
            raise DepositError(str(exc)) from exc
        self.payment_port.request_charge(deposit)
        return deposit

    def mark_paid(self, deposit_id: str, medio_pago: str | None = None) -> Deposit:
        return self._transition(deposit_id, DepositStatus.PAID, medio_pago=medio_pago)

    def mark_failed(self, deposit_id: str) -> Deposit:
        return self._transition(deposit_id, DepositStatus.FAILED)

    def request_refund(self, deposit_id: str) -> Deposit:
        deposit = self._get(deposit_id)
        if DepositStatus.REFUNDED not in _ALLOWED_TRANSITIONS[deposit.status]:
            raise InvalidDepositTransition(f"cannot refund {deposit.status.value} deposit")
        self.payment_port.request_refund(deposit)
        updated = Deposit(
            deposit.id, deposit.appointment_id, deposit.amount, DepositStatus.REFUNDED,
            medio_pago=deposit.medio_pago,
        )
        self.repository.save(updated)
        return updated

    def _get(self, deposit_id: str) -> Deposit:
        deposit = self.repository.get(deposit_id)
        if deposit is None:
            raise DepositNotFound(deposit_id)
        return deposit

    def _transition(
        self, deposit_id: str, target: DepositStatus, medio_pago: str | None = None
    ) -> Deposit:
        current = self._get(deposit_id)
        if target not in _ALLOWED_TRANSITIONS[current.status]:
            raise InvalidDepositTransition(
                f"cannot transition {current.status.value} to {target.value}"
            )
        updated = Deposit(
            current.id, current.appointment_id, current.amount, target,
            medio_pago=medio_pago if medio_pago is not None else current.medio_pago,
        )
        self.repository.save(updated)
        return updated
