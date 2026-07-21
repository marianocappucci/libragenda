"""Run the real Alembic chain against a live PostgreSQL database.

Skipped unless DATABASE_URL points to a reachable PostgreSQL instance (set by
docker-compose.dev.yml and CI). SQLite is not a valid substitute here: the
whole point of this test is to catch migration/dialect issues (server
defaults, foreign keys, timezone-aware columns) that only show up on the
real production engine.
"""

import os

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic import command
from sqlalchemy import create_engine, inspect

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; skipping real-PostgreSQL migration test"
)

EXPECTED_TABLES = {
    "branches", "clients", "resources", "services", "availability",
    "time_blocks", "availability_exceptions", "appointments", "holidays",
    "sent_reminders", "deposits", "alembic_version",
}


def _alembic_config() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    return cfg


@pytest.fixture(autouse=True)
def _clean_database():
    engine = create_engine(DATABASE_URL)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    engine.dispose()
    yield
    engine = create_engine(DATABASE_URL)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    engine.dispose()


def test_upgrade_head_creates_full_schema():
    cfg = _alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == EXPECTED_TABLES

    foreign_keys = inspector.get_foreign_keys("appointments")
    assert {(item["constrained_columns"][0], item["referred_table"]) for item in foreign_keys} == {
        ("resource_id", "resources"), ("service_id", "services"),
        ("client_id", "clients"), ("branch_id", "branches"),
    }
    engine.dispose()


def test_upgrade_then_downgrade_to_base_drops_all_tables():
    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    # Alembic keeps its own bookkeeping table across a downgrade to "base";
    # it only clears the version row. Every domain table must be gone.
    assert set(inspector.get_table_names()) == {"alembic_version"}
    with engine.begin() as connection:
        assert connection.exec_driver_sql("SELECT * FROM alembic_version").fetchall() == []
    engine.dispose()


def test_revision_chain_is_linear_and_reaches_head():
    cfg = _alembic_config()
    script = ScriptDirectory.from_config(cfg)
    revisions = list(script.walk_revisions())
    assert [rev.revision for rev in revisions] == [
        "0007_appointment_reason", "0006_deposits", "0005_sent_reminders",
        "0004_appointment_series", "0003_timezone_holidays", "0002_entities",
        "0001_initial",
    ]
    assert script.get_current_head() == "0007_appointment_reason"
