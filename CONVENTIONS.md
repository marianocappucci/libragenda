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
- **SQLite por defecto** para toda la familia Libra (silo: una instancia
  aislada por cliente, mismo patrón que Contalibra/Restolibra), a menos
  que el producto amerite otra cosa — ver `DECISIONS.md` ADR-005.
  `configure(url)` activa `PRAGMA foreign_keys=ON` automáticamente para
  cualquier URL `sqlite:///`, ya sea en memoria o archivo — SQLite no
  fuerza integridad referencial por default. PostgreSQL sigue siendo una
  opción soportada vía la misma `configure(url)`, para el caso puntual
  que lo justifique; cuando se use, una base + un usuario propio por
  producto/entorno, nunca schema compartido.
- `alembic upgrade head` antes de iniciar el consumidor.
- Versiones de LibraGenda por tags SemVer; consumidores pinean tags exactos.
- **Las migraciones no viajan en el paquete pip.** `pyproject.toml` solo
  empaqueta el paquete `libragenda/` (`[tool.hatch.build.targets.wheel]
  packages = ["libragenda"]`); `migrations/` queda fuera del wheel. Un
  consumidor que solo hace `pip install libragenda@vX.Y.Z` no tiene acceso a
  `migrations/` desde el paquete instalado.
- **Decisión (2026-07-18): el deploy pipeline de cada consumidor clona el
  repo, no se agrega `migrations/` al wheel.** Duplicar el empaquetado
  (wheel + repo) para lo mismo agrega una segunda fuente de verdad para un
  problema ya resuelto por el propio versionado en Git; clonar en el tag
  exacto que el consumidor ya pinea es más simple y no requiere tocar
  `pyproject.toml`.
- `scripts/run_migrations.sh` es la forma reproducible de aplicar esto: dado
  `LIBRAGENDA_REF` (tag) y `DATABASE_URL`, clona el repo en ese tag a un
  directorio temporal, instala el paquete en un venv descartable y corre
  `alembic upgrade head` contra la base indicada. Cada consumidor lo invoca
  como paso explícito de su propio pipeline de deploy, antes de levantar la
  API -- reemplaza el sync manual por rsync que se usaba en dev.
- `migrations/env.py` lee `DATABASE_URL` del entorno si está seteada (con
  fallback a `sqlalchemy.url` de `alembic.ini`), así el script no necesita
  editar `alembic.ini` por consumidor.
