"""Process-wide database configuration for LibraGenda consumers.

SQLite is the default engine for the whole Libra product family (silo
deployment: one isolated instance per client, same reasoning as
Contalibra/Restolibra) -- Postgres remains an option for products/cases
that genuinely need it, via the same `configure(url)` call.
"""

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    """SQLite does not enforce foreign keys unless told to, per connection.

    Without this, referential-integrity bugs (e.g. deleting a parent row
    before its FK-dependent extension row) fail silently instead of
    raising -- already bit MedLibra once, only caught by chance when
    verifying against Postgres (see MedLibra DECISIONS.md ADR-011).
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def configure(url: str, **engine_options) -> None:
    """Configure the database used by repositories in the current process.

    Call once during the vertical product startup, before constructing
    repositories. Migrations are intentionally separate and must run before
    the application starts serving traffic.
    """
    global _engine, _session_factory
    is_sqlite = url.startswith("sqlite:///")
    if url == "sqlite:///:memory:":
        engine_options.setdefault("connect_args", {"check_same_thread": False})
        engine_options.setdefault("poolclass", StaticPool)
    _engine = create_engine(url, **engine_options)
    if is_sqlite:
        event.listen(_engine, "connect", _enable_sqlite_foreign_keys)
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
