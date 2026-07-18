import pytest
from sqlalchemy import create_engine

from libragenda.database import configure, get_engine, get_session_factory, reset


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
