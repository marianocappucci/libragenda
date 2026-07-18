from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from libragenda import Branch, Client, Holiday, Resource, Service, SqlAlchemyCatalogRepository
from libragenda.sqlalchemy_repository import Base


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
