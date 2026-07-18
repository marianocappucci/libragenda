"""Repositories for resources, services, branches and clients."""

from collections.abc import Iterable
from sqlalchemy.orm import Session, sessionmaker

from .domain import Branch, Client, Resource, Service
from .sqlalchemy_repository import BranchRow, ClientRow, ResourceRow, ServiceRow


class SqlAlchemyCatalogRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def add_branch(self, branch: Branch) -> None:
        with self.session_factory.begin() as session: session.add(BranchRow(id=branch.id, name=branch.name, active=branch.active))

    def add_client(self, client: Client) -> None:
        with self.session_factory.begin() as session: session.add(ClientRow(id=client.id, name=client.name, phone=client.phone, email=client.email, active=client.active))

    def add_resource(self, resource: Resource) -> None:
        with self.session_factory.begin() as session: session.add(ResourceRow(id=resource.id, name=resource.name, branch_id=resource.branch_id, active=resource.active))

    def add_service(self, service: Service) -> None:
        with self.session_factory.begin() as session: session.add(ServiceRow(id=service.id, name=service.name, duration_seconds=int(service.duration.total_seconds()), active=service.active))

    def list_branches(self) -> Iterable[Branch]:
        with self.session_factory() as session: return tuple(Branch(row.id, row.name, row.active) for row in session.query(BranchRow).all())

    def list_clients(self) -> Iterable[Client]:
        with self.session_factory() as session: return tuple(Client(row.id, row.name, row.phone, row.email, row.active) for row in session.query(ClientRow).all())

    def list_resources(self) -> Iterable[Resource]:
        with self.session_factory() as session: return tuple(Resource(row.id, row.name, row.branch_id, row.active) for row in session.query(ResourceRow).all())

    def list_services(self) -> Iterable[Service]:
        from datetime import timedelta
        with self.session_factory() as session: return tuple(Service(row.id, row.name, timedelta(seconds=row.duration_seconds), row.active) for row in session.query(ServiceRow).all())
