from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from libragenda.sqlalchemy_repository import Base


def test_revision_ids_fit_in_the_alembic_version_column():
    """`alembic_version.version_num` es varchar(32) y PostgreSQL lo hace cumplir.

    Vive acá y no en `test_migrations.py` a propósito: aquel módulo entero se
    saltea sin `DATABASE_URL`, así que un id largo pasaría toda la suite local
    y recién explotaría contra Postgres. Pasó con el `0009`, que nació con 33
    caracteres y solo lo agarró el CI. Este chequeo no necesita base ninguna.
    """
    revisions = [
        rev.revision
        for rev in ScriptDirectory.from_config(Config("alembic.ini")).walk_revisions()
    ]

    # Sin esto el test pasaría en vacío el día que no encuentre la cadena, que
    # es la forma más silenciosa de perder un chequeo.
    assert len(revisions) >= 9
    assert [rev for rev in revisions if len(rev) > 32] == []


def test_full_schema_has_core_tables_and_foreign_keys():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "branches", "clients", "resources", "services", "availability",
        "time_blocks", "availability_exceptions", "appointments", "holidays",
        "sent_reminders", "deposits", "appointment_resources",
        "appointment_transitions", "agenda_policies",
    }
    foreign_keys = inspector.get_foreign_keys("appointments")
    assert {(item["constrained_columns"][0], item["referred_table"]) for item in foreign_keys} == {
        ("resource_id", "resources"), ("service_id", "services"),
        ("client_id", "clients"), ("branch_id", "branches"),
    }
    deposit_foreign_keys = inspector.get_foreign_keys("deposits")
    assert {(item["constrained_columns"][0], item["referred_table"]) for item in deposit_foreign_keys} == {
        ("appointment_id", "appointments"),
    }
    occupancy_foreign_keys = inspector.get_foreign_keys("appointment_resources")
    assert {
        (item["constrained_columns"][0], item["referred_table"])
        for item in occupancy_foreign_keys
    } == {("appointment_id", "appointments"), ("resource_id", "resources")}
