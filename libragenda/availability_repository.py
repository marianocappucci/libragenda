"""CRUD repository for weekly availability, time blocks and exceptions."""

from sqlalchemy.orm import Session, sessionmaker

from .domain import Availability
from .scheduling import AvailabilityException, TimeBlock
from .sqlalchemy_repository import (
    AvailabilityExceptionRow,
    AvailabilityRow,
    TimeBlockRow,
)


class SqlAlchemyAvailabilityRepository:
    """Repository covering weekly windows, point-in-time blocks and date exceptions."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    # -- weekly availability windows -----------------------------------

    def add_availability(self, availability: Availability) -> int:
        with self.session_factory.begin() as session:
            row = self._availability_to_row(availability)
            session.add(row)
            session.flush()
            return row.id

    def get_availability(self, availability_id: int) -> Availability | None:
        with self.session_factory() as session:
            row = session.get(AvailabilityRow, availability_id)
            return self._availability_to_domain(row) if row else None

    def update_availability(self, availability_id: int, availability: Availability) -> None:
        with self.session_factory.begin() as session:
            row = session.get(AvailabilityRow, availability_id)
            if row is None:
                raise KeyError(availability_id)
            row.resource_id = availability.resource_id
            row.weekday = availability.weekday
            row.starts_at = availability.starts_at
            row.ends_at = availability.ends_at

    def delete_availability(self, availability_id: int) -> None:
        with self.session_factory.begin() as session:
            row = session.get(AvailabilityRow, availability_id)
            if row is None:
                raise KeyError(availability_id)
            session.delete(row)

    def list_availability(
        self, resource_id: str | None = None
    ) -> tuple[tuple[int, Availability], ...]:
        with self.session_factory() as session:
            query = session.query(AvailabilityRow)
            if resource_id is not None:
                query = query.filter(AvailabilityRow.resource_id == resource_id)
            return tuple((row.id, self._availability_to_domain(row)) for row in query.all())

    @staticmethod
    def _availability_to_row(availability: Availability) -> AvailabilityRow:
        return AvailabilityRow(
            resource_id=availability.resource_id,
            weekday=availability.weekday,
            starts_at=availability.starts_at,
            ends_at=availability.ends_at,
        )

    @staticmethod
    def _availability_to_domain(row: AvailabilityRow) -> Availability:
        return Availability(
            resource_id=row.resource_id,
            weekday=row.weekday,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
        )

    # -- point-in-time blocks --------------------------------------------

    def add_block(self, block: TimeBlock) -> int:
        with self.session_factory.begin() as session:
            row = self._block_to_row(block)
            session.add(row)
            session.flush()
            return row.id

    def get_block(self, block_id: int) -> TimeBlock | None:
        with self.session_factory() as session:
            row = session.get(TimeBlockRow, block_id)
            return self._block_to_domain(row) if row else None

    def update_block(self, block_id: int, block: TimeBlock) -> None:
        with self.session_factory.begin() as session:
            row = session.get(TimeBlockRow, block_id)
            if row is None:
                raise KeyError(block_id)
            row.resource_id = block.resource_id
            row.starts_at = block.starts_at
            row.ends_at = block.ends_at
            row.reason = block.reason

    def delete_block(self, block_id: int) -> None:
        with self.session_factory.begin() as session:
            row = session.get(TimeBlockRow, block_id)
            if row is None:
                raise KeyError(block_id)
            session.delete(row)

    def list_blocks(self, resource_id: str | None = None) -> tuple[tuple[int, TimeBlock], ...]:
        with self.session_factory() as session:
            query = session.query(TimeBlockRow)
            if resource_id is not None:
                query = query.filter(TimeBlockRow.resource_id == resource_id)
            return tuple((row.id, self._block_to_domain(row)) for row in query.all())

    @staticmethod
    def _block_to_row(block: TimeBlock) -> TimeBlockRow:
        return TimeBlockRow(
            resource_id=block.resource_id,
            starts_at=block.starts_at,
            ends_at=block.ends_at,
            reason=block.reason,
        )

    @staticmethod
    def _block_to_domain(row: TimeBlockRow) -> TimeBlock:
        return TimeBlock(
            resource_id=row.resource_id,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            reason=row.reason,
        )

    # -- date-specific exceptions -----------------------------------------

    def add_exception(self, exception: AvailabilityException) -> int:
        with self.session_factory.begin() as session:
            row = self._exception_to_row(exception)
            session.add(row)
            session.flush()
            return row.id

    def get_exception(self, exception_id: int) -> AvailabilityException | None:
        with self.session_factory() as session:
            row = session.get(AvailabilityExceptionRow, exception_id)
            return self._exception_to_domain(row) if row else None

    def update_exception(self, exception_id: int, exception: AvailabilityException) -> None:
        with self.session_factory.begin() as session:
            row = session.get(AvailabilityExceptionRow, exception_id)
            if row is None:
                raise KeyError(exception_id)
            row.resource_id = exception.resource_id
            row.day = exception.day
            row.starts_at = exception.starts_at
            row.ends_at = exception.ends_at
            row.available = exception.available

    def delete_exception(self, exception_id: int) -> None:
        with self.session_factory.begin() as session:
            row = session.get(AvailabilityExceptionRow, exception_id)
            if row is None:
                raise KeyError(exception_id)
            session.delete(row)

    def list_exceptions(
        self, resource_id: str | None = None
    ) -> tuple[tuple[int, AvailabilityException], ...]:
        with self.session_factory() as session:
            query = session.query(AvailabilityExceptionRow)
            if resource_id is not None:
                query = query.filter(AvailabilityExceptionRow.resource_id == resource_id)
            return tuple((row.id, self._exception_to_domain(row)) for row in query.all())

    @staticmethod
    def _exception_to_row(exception: AvailabilityException) -> AvailabilityExceptionRow:
        return AvailabilityExceptionRow(
            resource_id=exception.resource_id,
            day=exception.day,
            starts_at=exception.starts_at,
            ends_at=exception.ends_at,
            available=exception.available,
        )

    @staticmethod
    def _exception_to_domain(row: AvailabilityExceptionRow) -> AvailabilityException:
        return AvailabilityException(
            resource_id=row.resource_id,
            day=row.day,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            available=row.available,
        )
