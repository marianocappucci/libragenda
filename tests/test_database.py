from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from libragenda.database import configure, get_engine, get_session_factory, reset
from libragenda.sqlalchemy_repository import Base, HolidayRow


def test_database_configuration_exposes_engine_and_sessions():
    try:
        configure("sqlite:///:memory:")
        assert get_engine().url.get_backend_name() == "sqlite"
        assert get_session_factory()
    finally:
        reset()


def test_database_access_before_configuration_fails():
    reset()
    with pytest.raises(RuntimeError):
        get_engine()
    with pytest.raises(RuntimeError):
        get_session_factory()


def test_sqlite_foreign_keys_are_enforced_by_default():
    """SQLite doesn't enforce FKs unless told to per connection -- without
    this, referential-integrity bugs fail silently instead of raising."""
    try:
        configure("sqlite:///:memory:")
        with get_engine().connect() as conn:
            fk_status = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert fk_status == 1
    finally:
        reset()


def test_sqlite_file_based_url_also_enforces_foreign_keys(tmp_path):
    db_path = tmp_path / "test.db"
    try:
        configure(f"sqlite:///{db_path}")
        with get_engine().connect() as conn:
            fk_status = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert fk_status == 1
    finally:
        reset()


def test_sqlite_actually_rejects_a_foreign_key_violation():
    """Not just the pragma reading back as on -- confirm SQLite actually
    blocks an insert referencing a nonexistent parent row."""
    try:
        configure("sqlite:///:memory:")
        Base.metadata.create_all(get_engine())
        with get_session_factory().begin() as session:
            session.add(HolidayRow(branch_id="missing-branch", day=date(2026, 1, 1), name="x"))
            with pytest.raises(IntegrityError):
                session.flush()
    finally:
        reset()
