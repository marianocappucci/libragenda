"""Persistence for which (appointment, policy) reminders were already sent."""

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .sqlalchemy_repository import SentReminderRow


class SqlAlchemyReminderRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def sent_pairs(self, appointment_ids: list[str]) -> set[tuple[str, str]]:
        if not appointment_ids:
            return set()
        with self.session_factory() as session:
            rows = (
                session.query(SentReminderRow)
                .filter(SentReminderRow.appointment_id.in_(appointment_ids))
                .all()
            )
            return {(row.appointment_id, row.policy_id) for row in rows}

    def mark_sent(self, appointment_id: str, policy_id: str, sent_at: datetime) -> None:
        """Record a reminder as sent. Idempotent: a duplicate call is a no-op.

        The unique constraint on (appointment_id, policy_id) is the actual
        guard against a double-send race; the caller checking `sent_pairs`
        first is only an optimization, not the source of truth.
        """
        try:
            with self.session_factory.begin() as session:
                session.add(SentReminderRow(
                    appointment_id=appointment_id, policy_id=policy_id, sent_at=sent_at,
                ))
        except IntegrityError:
            pass
