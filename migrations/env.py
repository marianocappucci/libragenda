"""Alembic environment for LibraGenda."""
import os

from alembic import context
from sqlalchemy import engine_from_config, pool
from libragenda.sqlalchemy_repository import Base

target_metadata = Base.metadata


def get_url():
    return os.environ.get("DATABASE_URL") or context.config.get_main_option("sqlalchemy.url")


def run_migrations_offline():
    context.configure(url=get_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online():
    configuration = context.config.get_section(context.config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction(): context.run_migrations()

if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
