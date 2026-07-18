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
- PostgreSQL dedicado por entorno.
- `alembic upgrade head` antes de iniciar el consumidor.
- Versiones de LibraGenda por tags SemVer; consumidores pinean tags exactos.
