"""Persistence for the at-most-one-deposit-per-appointment ledger."""

from sqlalchemy.orm import Session, sessionmaker

from .payments import Deposit, DepositStatus
from .sqlalchemy_repository import DepositRow


class SqlAlchemyDepositRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def add(self, deposit: Deposit) -> None:
        with self.session_factory.begin() as session:
            session.add(self._to_row(deposit))

    def get(self, deposit_id: str) -> Deposit | None:
        with self.session_factory() as session:
            row = session.get(DepositRow, deposit_id)
            return self._to_domain(row) if row else None

    def get_by_appointment(self, appointment_id: str) -> Deposit | None:
        with self.session_factory() as session:
            row = (
                session.query(DepositRow)
                .filter(DepositRow.appointment_id == appointment_id)
                .one_or_none()
            )
            return self._to_domain(row) if row else None

    def save(self, deposit: Deposit) -> None:
        with self.session_factory.begin() as session:
            row = session.get(DepositRow, deposit.id)
            if row is None:
                raise KeyError(deposit.id)
            row.status = deposit.status.value
            row.amount = deposit.amount
            row.medio_pago = deposit.medio_pago

    @staticmethod
    def _to_row(deposit: Deposit) -> DepositRow:
        return DepositRow(
            id=deposit.id, appointment_id=deposit.appointment_id,
            amount=deposit.amount, status=deposit.status.value,
            medio_pago=deposit.medio_pago,
        )

    @staticmethod
    def _to_domain(row: DepositRow) -> Deposit:
        return Deposit(
            id=row.id, appointment_id=row.appointment_id,
            amount=row.amount, status=DepositStatus(row.status),
            medio_pago=row.medio_pago,
        )
