from sqlalchemy import create_engine, inspect

from libragenda.sqlalchemy_repository import Base


def test_full_schema_has_core_tables_and_foreign_keys():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {"resources", "services", "availability", "appointments"}
    foreign_keys = inspector.get_foreign_keys("appointments")
    assert {(item["constrained_columns"][0], item["referred_table"]) for item in foreign_keys} == {
        ("resource_id", "resources"), ("service_id", "services")
    }
