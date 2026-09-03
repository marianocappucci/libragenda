"""Alembic environment for LibraGenda."""
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from libragenda.sqlalchemy_repository import Base

target_metadata = Base.metadata


def get_url():
    """La base contra la que se migra, en orden de precedencia.

    1. **`libragenda.url`**, que pone `migrar.configuracion()` cuando alguien
       pasa la URL explícita. Va primero porque es la única señal inequívoca de
       intención.
    2. `DATABASE_URL` del entorno — el caso de cualquier contenedor.
    3. `sqlalchemy.url` del `alembic.ini`, que en este repo es un placeholder.

    🔴 **La opción 1 existe porque sin ella el argumento explícito se ignoraba
    en silencio.** `DATABASE_URL` ganaba siempre, así que
    `migrar.upgrade("…/otra_base")` con la variable puesta migraba **la del
    entorno** y devolvía éxito. Lo encontró el test que migra una base real: el
    upgrade daba verde y `alembic_version` aparecía en la base equivocada.

    🔴 Y no se invirtió la precedencia contra `sqlalchemy.url` a secas: ese
    valor en `alembic.ini` es un placeholder
    (`postgresql://user:password@localhost/libragenda`), así que preferirlo
    rompería el `alembic -c alembic.ini upgrade head` de siempre.

    La normalización del driver pasa por acá para los tres casos — ver
    `libragenda/migrar.py::normalizar_url`.
    """
    from libragenda.migrar import normalizar_url

    explicita = context.config.get_main_option("libragenda.url", None)
    return normalizar_url(
        explicita
        or os.environ.get("DATABASE_URL")
        or context.config.get_main_option("sqlalchemy.url")
    )


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
