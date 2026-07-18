from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from libragenda import Branch, Client, Holiday, Resource, Service, SqlAlchemyCatalogRepository
from libragenda.sqlalchemy_repository import Base


@pytest.fixture()
def repo() -> SqlAlchemyCatalogRepository:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlAlchemyCatalogRepository(sessionmaker(engine, expire_on_commit=False))


def test_catalog_repository_round_trips_master_entities():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repo = SqlAlchemyCatalogRepository(sessionmaker(engine, expire_on_commit=False))
    repo.add_branch(Branch("branch-1", "Centro", timezone="America/Argentina/Buenos_Aires"))
    repo.add_client(Client("client-1", "Ana", phone="123"))
    repo.add_resource(Resource("resource-1", "Box 1", branch_id="branch-1"))
    repo.add_service(Service("service-1", "Consulta", timedelta(minutes=30)))

    assert tuple(repo.list_branches())[0].name == "Centro"
    assert tuple(repo.list_branches())[0].timezone == "America/Argentina/Buenos_Aires"
    assert tuple(repo.list_clients())[0].phone == "123"
    assert tuple(repo.list_resources())[0].branch_id == "branch-1"
    assert tuple(repo.list_services())[0].duration == timedelta(minutes=30)


def test_catalog_repository_round_trips_holidays_scoped_by_branch():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repo = SqlAlchemyCatalogRepository(sessionmaker(engine, expire_on_commit=False))
    repo.add_branch(Branch("branch-1", "Centro"))
    repo.add_branch(Branch("branch-2", "Sucursal Norte"))
    repo.add_holiday(Holiday("branch-1", date(2026, 12, 25), "Navidad"))
    repo.add_holiday(Holiday("branch-2", date(2026, 5, 1), "Feriado laboral"))

    assert {holiday.name for holiday in repo.list_holidays()} == {"Navidad", "Feriado laboral"}
    branch_1_holidays = tuple(repo.list_holidays(branch_id="branch-1"))
    assert len(branch_1_holidays) == 1
    assert branch_1_holidays[0].name == "Navidad"


def test_branch_crud_round_trip(repo: SqlAlchemyCatalogRepository):
    repo.add_branch(Branch("branch-1", "Centro"))
    assert repo.get_branch("branch-1") == Branch("branch-1", "Centro")

    repo.update_branch("branch-1", Branch("branch-1", "Centro renombrado", active=False))
    updated = repo.get_branch("branch-1")
    assert updated.name == "Centro renombrado"
    assert updated.active is False

    repo.delete_branch("branch-1")
    assert repo.get_branch("branch-1") is None
    with pytest.raises(KeyError):
        repo.delete_branch("branch-1")
    with pytest.raises(KeyError):
        repo.update_branch("branch-1", Branch("branch-1", "x"))


def test_client_crud_round_trip(repo: SqlAlchemyCatalogRepository):
    repo.add_client(Client("client-1", "Ana", phone="123"))
    assert repo.get_client("client-1").phone == "123"

    repo.update_client("client-1", Client("client-1", "Ana", phone="456", email="ana@x.com"))
    updated = repo.get_client("client-1")
    assert updated.phone == "456"
    assert updated.email == "ana@x.com"

    repo.delete_client("client-1")
    assert repo.get_client("client-1") is None
    with pytest.raises(KeyError):
        repo.delete_client("client-1")


def test_resource_crud_round_trip(repo: SqlAlchemyCatalogRepository):
    repo.add_branch(Branch("branch-1", "Centro"))
    repo.add_resource(Resource("resource-1", "Box 1", branch_id="branch-1"))
    assert repo.get_resource("resource-1").branch_id == "branch-1"

    repo.update_resource("resource-1", Resource("resource-1", "Box renombrado", active=False))
    updated = repo.get_resource("resource-1")
    assert updated.name == "Box renombrado"
    assert updated.branch_id is None
    assert updated.active is False

    repo.delete_resource("resource-1")
    assert repo.get_resource("resource-1") is None
    with pytest.raises(KeyError):
        repo.delete_resource("resource-1")


def test_service_crud_round_trip(repo: SqlAlchemyCatalogRepository):
    repo.add_service(Service("service-1", "Consulta", timedelta(minutes=30)))
    assert repo.get_service("service-1").duration == timedelta(minutes=30)

    repo.update_service("service-1", Service("service-1", "Consulta larga", timedelta(minutes=60)))
    updated = repo.get_service("service-1")
    assert updated.name == "Consulta larga"
    assert updated.duration == timedelta(minutes=60)

    repo.delete_service("service-1")
    assert repo.get_service("service-1") is None
    with pytest.raises(KeyError):
        repo.delete_service("service-1")
