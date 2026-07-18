"""Repositories for resources, services, branches and clients."""

from collections.abc import Iterable
from datetime import timedelta
from sqlalchemy.orm import Session, sessionmaker

from .domain import Branch, Client, Holiday, Resource, Service
from .sqlalchemy_repository import BranchRow, ClientRow, HolidayRow, ResourceRow, ServiceRow


class SqlAlchemyCatalogRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    # -- branches ----------------------------------------------------------

    def add_branch(self, branch: Branch) -> None:
        with self.session_factory.begin() as session:
            session.add(self._branch_to_row(branch))

    def get_branch(self, branch_id: str) -> Branch | None:
        with self.session_factory() as session:
            row = session.get(BranchRow, branch_id)
            return self._branch_to_domain(row) if row else None

    def update_branch(self, branch_id: str, branch: Branch) -> None:
        with self.session_factory.begin() as session:
            row = session.get(BranchRow, branch_id)
            if row is None:
                raise KeyError(branch_id)
            row.name = branch.name
            row.active = branch.active
            row.timezone = branch.timezone

    def delete_branch(self, branch_id: str) -> None:
        with self.session_factory.begin() as session:
            row = session.get(BranchRow, branch_id)
            if row is None:
                raise KeyError(branch_id)
            session.delete(row)

    def list_branches(self) -> Iterable[Branch]:
        with self.session_factory() as session:
            return tuple(self._branch_to_domain(row) for row in session.query(BranchRow).all())

    @staticmethod
    def _branch_to_row(branch: Branch) -> BranchRow:
        return BranchRow(id=branch.id, name=branch.name, active=branch.active, timezone=branch.timezone)

    @staticmethod
    def _branch_to_domain(row: BranchRow) -> Branch:
        return Branch(row.id, row.name, row.active, row.timezone)

    # -- clients -------------------------------------------------------------

    def add_client(self, client: Client) -> None:
        with self.session_factory.begin() as session:
            session.add(self._client_to_row(client))

    def get_client(self, client_id: str) -> Client | None:
        with self.session_factory() as session:
            row = session.get(ClientRow, client_id)
            return self._client_to_domain(row) if row else None

    def update_client(self, client_id: str, client: Client) -> None:
        with self.session_factory.begin() as session:
            row = session.get(ClientRow, client_id)
            if row is None:
                raise KeyError(client_id)
            row.name = client.name
            row.phone = client.phone
            row.email = client.email
            row.active = client.active

    def delete_client(self, client_id: str) -> None:
        with self.session_factory.begin() as session:
            row = session.get(ClientRow, client_id)
            if row is None:
                raise KeyError(client_id)
            session.delete(row)

    def list_clients(self) -> Iterable[Client]:
        with self.session_factory() as session:
            return tuple(self._client_to_domain(row) for row in session.query(ClientRow).all())

    @staticmethod
    def _client_to_row(client: Client) -> ClientRow:
        return ClientRow(
            id=client.id, name=client.name, phone=client.phone,
            email=client.email, active=client.active,
        )

    @staticmethod
    def _client_to_domain(row: ClientRow) -> Client:
        return Client(row.id, row.name, row.phone, row.email, row.active)

    # -- resources -----------------------------------------------------------

    def add_resource(self, resource: Resource) -> None:
        with self.session_factory.begin() as session:
            session.add(self._resource_to_row(resource))

    def get_resource(self, resource_id: str) -> Resource | None:
        with self.session_factory() as session:
            row = session.get(ResourceRow, resource_id)
            return self._resource_to_domain(row) if row else None

    def update_resource(self, resource_id: str, resource: Resource) -> None:
        with self.session_factory.begin() as session:
            row = session.get(ResourceRow, resource_id)
            if row is None:
                raise KeyError(resource_id)
            row.name = resource.name
            row.branch_id = resource.branch_id
            row.active = resource.active

    def delete_resource(self, resource_id: str) -> None:
        with self.session_factory.begin() as session:
            row = session.get(ResourceRow, resource_id)
            if row is None:
                raise KeyError(resource_id)
            session.delete(row)

    def list_resources(self) -> Iterable[Resource]:
        with self.session_factory() as session:
            return tuple(self._resource_to_domain(row) for row in session.query(ResourceRow).all())

    @staticmethod
    def _resource_to_row(resource: Resource) -> ResourceRow:
        return ResourceRow(
            id=resource.id, name=resource.name,
            branch_id=resource.branch_id, active=resource.active,
        )

    @staticmethod
    def _resource_to_domain(row: ResourceRow) -> Resource:
        return Resource(row.id, row.name, row.branch_id, row.active)

    # -- services --------------------------------------------------------------

    def add_service(self, service: Service) -> None:
        with self.session_factory.begin() as session:
            session.add(self._service_to_row(service))

    def get_service(self, service_id: str) -> Service | None:
        with self.session_factory() as session:
            row = session.get(ServiceRow, service_id)
            return self._service_to_domain(row) if row else None

    def update_service(self, service_id: str, service: Service) -> None:
        with self.session_factory.begin() as session:
            row = session.get(ServiceRow, service_id)
            if row is None:
                raise KeyError(service_id)
            row.name = service.name
            row.duration_seconds = int(service.duration.total_seconds())
            row.active = service.active

    def delete_service(self, service_id: str) -> None:
        with self.session_factory.begin() as session:
            row = session.get(ServiceRow, service_id)
            if row is None:
                raise KeyError(service_id)
            session.delete(row)

    def list_services(self) -> Iterable[Service]:
        with self.session_factory() as session:
            return tuple(self._service_to_domain(row) for row in session.query(ServiceRow).all())

    @staticmethod
    def _service_to_row(service: Service) -> ServiceRow:
        return ServiceRow(
            id=service.id, name=service.name,
            duration_seconds=int(service.duration.total_seconds()), active=service.active,
        )

    @staticmethod
    def _service_to_domain(row: ServiceRow) -> Service:
        return Service(row.id, row.name, timedelta(seconds=row.duration_seconds), row.active)

    # -- holidays --------------------------------------------------------------

    def add_holiday(self, holiday: Holiday) -> int:
        with self.session_factory.begin() as session:
            row = HolidayRow(branch_id=holiday.branch_id, day=holiday.day, name=holiday.name)
            session.add(row)
            session.flush()
            return row.id

    def list_holidays(self, branch_id: str | None = None) -> Iterable[Holiday]:
        with self.session_factory() as session:
            query = session.query(HolidayRow)
            if branch_id is not None:
                query = query.filter(HolidayRow.branch_id == branch_id)
            return tuple(Holiday(row.branch_id, row.day, row.name) for row in query.all())
