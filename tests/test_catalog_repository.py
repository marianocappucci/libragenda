from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from libragenda import Branch, Client, Resource, Service, SqlAlchemyCatalogRepository
from libragenda.sqlalchemy_repository import Base


def test_catalog_repository_round_trips_master_entities():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repo = SqlAlchemyCatalogRepository(sessionmaker(engine, expire_on_commit=False))
    repo.add_branch(Branch("branch-1", "Centro"))
    repo.add_client(Client("client-1", "Ana", phone="123"))
    repo.add_resource(Resource("resource-1", "Box 1", branch_id="branch-1"))
    repo.add_service(Service("service-1", "Consulta", timedelta(minutes=30)))

    assert tuple(repo.list_branches())[0].name == "Centro"
    assert tuple(repo.list_clients())[0].phone == "123"
    assert tuple(repo.list_resources())[0].branch_id == "branch-1"
    assert tuple(repo.list_services())[0].duration == timedelta(minutes=30)
