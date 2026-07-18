from datetime import date, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from libragenda import Availability, AvailabilityException, SqlAlchemyAvailabilityRepository, TimeBlock
from libragenda.sqlalchemy_repository import Base


@pytest.fixture()
def repo() -> SqlAlchemyAvailabilityRepository:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlAlchemyAvailabilityRepository(sessionmaker(engine, expire_on_commit=False))


def test_availability_crud_round_trip(repo: SqlAlchemyAvailabilityRepository):
    availability = Availability("resource-1", weekday=1, starts_at=time(9, 0), ends_at=time(12, 0))
    availability_id = repo.add_availability(availability)

    stored = repo.get_availability(availability_id)
    assert stored == availability

    updated = Availability("resource-1", weekday=2, starts_at=time(10, 0), ends_at=time(13, 0))
    repo.update_availability(availability_id, updated)
    assert repo.get_availability(availability_id) == updated

    assert [item for _, item in repo.list_availability(resource_id="resource-1")] == [updated]

    repo.delete_availability(availability_id)
    assert repo.get_availability(availability_id) is None
    with pytest.raises(KeyError):
        repo.delete_availability(availability_id)


def test_block_crud_round_trip(repo: SqlAlchemyAvailabilityRepository):
    from datetime import datetime

    block = TimeBlock(
        "resource-1",
        starts_at=datetime(2026, 7, 20, 9, 0),
        ends_at=datetime(2026, 7, 20, 10, 0),
        reason="maintenance",
    )
    block_id = repo.add_block(block)

    assert repo.get_block(block_id) == block

    updated = TimeBlock(
        "resource-1",
        starts_at=datetime(2026, 7, 20, 11, 0),
        ends_at=datetime(2026, 7, 20, 12, 0),
        reason="vacation",
    )
    repo.update_block(block_id, updated)
    assert repo.get_block(block_id) == updated

    assert [item for _, item in repo.list_blocks(resource_id="resource-1")] == [updated]

    repo.delete_block(block_id)
    assert repo.get_block(block_id) is None
    with pytest.raises(KeyError):
        repo.update_block(block_id, updated)


def test_exception_crud_round_trip(repo: SqlAlchemyAvailabilityRepository):
    exception = AvailabilityException(
        "resource-1", day=date(2026, 12, 25), starts_at=time(0, 0), ends_at=time(23, 59), available=False
    )
    exception_id = repo.add_exception(exception)

    assert repo.get_exception(exception_id) == exception

    updated = AvailabilityException(
        "resource-1", day=date(2026, 12, 25), starts_at=time(9, 0), ends_at=time(13, 0), available=True
    )
    repo.update_exception(exception_id, updated)
    assert repo.get_exception(exception_id) == updated

    assert [item for _, item in repo.list_exceptions(resource_id="resource-1")] == [updated]

    repo.delete_exception(exception_id)
    assert repo.get_exception(exception_id) is None
    with pytest.raises(KeyError):
        repo.delete_exception(exception_id)
