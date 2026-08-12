from datetime import date, time, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from libragenda import (
    AgendaPolicy,
    Availability,
    AvailabilityException,
    SqlAlchemyAvailabilityRepository,
    TimeBlock,
)
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
    from datetime import datetime, timezone

    # DateTime(timezone=True) always round-trips as aware — even on SQLite,
    # which has no native tz type (see sqlalchemy_repository.ensure_utc) —
    # so the domain object under comparison must start out aware too.
    block = TimeBlock(
        "resource-1",
        starts_at=datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc),
        reason="maintenance",
    )
    block_id = repo.add_block(block)

    assert repo.get_block(block_id) == block

    updated = TimeBlock(
        "resource-1",
        starts_at=datetime(2026, 7, 20, 11, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
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


def test_availability_validity_round_trips(repo: SqlAlchemyAvailabilityRepository):
    dated = Availability("resource-1", weekday=1, starts_at=time(9, 0), ends_at=time(12, 0),
                         valid_from=date(2026, 7, 1), valid_to=date(2026, 7, 31))
    availability_id = repo.add_availability(dated)

    assert repo.get_availability(availability_id) == dated

    reopened = Availability("resource-1", weekday=1, starts_at=time(9, 0), ends_at=time(12, 0),
                            valid_from=date(2026, 8, 1))
    repo.update_availability(availability_id, reopened)
    stored = repo.get_availability(availability_id)
    assert stored.valid_from == date(2026, 8, 1)
    assert stored.valid_to is None


def test_availability_without_validity_round_trips_as_unbounded(
    repo: SqlAlchemyAvailabilityRepository,
):
    availability_id = repo.add_availability(
        Availability("resource-1", weekday=1, starts_at=time(9, 0), ends_at=time(12, 0))
    )

    stored = repo.get_availability(availability_id)
    assert (stored.valid_from, stored.valid_to) == (None, None)


def test_agenda_policy_crud_round_trip(repo: SqlAlchemyAvailabilityRepository):
    policy = AgendaPolicy("resource-1", slot_interval=timedelta(minutes=10),
                          max_overbookings_per_day=2)
    repo.set_policy(policy)

    assert repo.get_policy("resource-1") == policy
    assert repo.list_policies() == (policy,)

    # Setting it again replaces rather than duplicating: one agenda, one policy.
    repo.set_policy(AgendaPolicy("resource-1", slot_interval=timedelta(minutes=5),
                                 max_overbookings_per_day=0))
    assert len(repo.list_policies()) == 1
    assert repo.get_policy("resource-1").slot_interval == timedelta(minutes=5)

    repo.delete_policy("resource-1")
    assert repo.get_policy("resource-1") is None
    with pytest.raises(KeyError):
        repo.delete_policy("resource-1")
