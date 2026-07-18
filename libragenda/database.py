"""Process-wide PostgreSQL configuration for LibraGenda consumers."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def configure(url: str, **engine_options) -> None:
    """Configure the database used by repositories in the current process.

    Call once during the vertical product startup, before constructing
    repositories. Migrations are intentionally separate and must run before
    the application starts serving traffic.
    """
    global _engine, _session_factory
    _engine = create_engine(url, **engine_options)
    _session_factory = sessionmaker(_engine, expire_on_commit=False)


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("libragenda.database is not configured; call configure() first")
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        raise RuntimeError("libragenda.database is not configured; call configure() first")
    return _session_factory


def reset() -> None:
    """Reset process state for tests; not used by production consumers."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
