# Convenciones de LibraGenda

## Capas

- `domain.py`: entidades y value rules, sin SQLAlchemy ni FastAPI.
- `scheduling.py`: reglas puras de disponibilidad, solapamientos y bloqueos.
- `application.py`: casos de uso y transiciones de estado.
- `repositories.py`: puertos (`Protocol`) y adaptadores en memoria.
- `sqlalchemy_repository.py`, `catalog_repository.py`: persistencia.
- `database.py`: configuración de conexión del proceso consumidor.
- `migrations/`: única fuente de cambios de esquema; no usar `create_all()` en producción.

## Reglas

- Nombres de clases y métodos en inglés; documentación de producto puede estar en español.
- Datetimes con timezone cuando representen instantes; ventanas semanales usan `time`.
- Entidades de dominio inmutables (`dataclass(frozen=True, slots=True)`).
- Las reglas de negocio no hacen I/O.
- Los repositorios no contienen reglas de agenda.
- Los errores de negocio son excepciones específicas, no `ValueError` genérico hacia la API.
- Cada cambio de dominio debe agregar tests unitarios; cada integración HTTP debe tener smoke test.
- No incluir datos clínicos, gastronómicos ni facturación específica en LibraGenda.

## Configuración y deploy

- Secretos solo por variables de entorno o archivos `.env` fuera de Git.
- PostgreSQL dedicado por entorno (una base + un usuario propio por
  producto/entorno — nunca comparten schema con la base de LibraGenda ni
  entre sí).
- `alembic upgrade head` antes de iniciar el consumidor.
- Versiones de LibraGenda por tags SemVer; consumidores pinean tags exactos.
- **Las migraciones no viajan en el paquete pip.** `pyproject.toml` solo
  empaqueta el paquete `libragenda/` (`[tool.hatch.build.targets.wheel]
  packages = ["libragenda"]`); `migrations/` queda fuera del wheel. Un
  consumidor que solo hace `pip install libragenda@vX.Y.Z` no tiene forma de
  correr `alembic upgrade head` — necesita, además, un checkout del repo en
  esa misma versión (tag) para acceder a `migrations/`. En dev esto se
  resolvió sincronizando el checkout local al VPS y corriendo Alembic desde
  ahí contra la base del consumidor; en producción falta decidir si el
  deploy pipeline clona el repo aparte o si se agrega `migrations/` al wheel.
