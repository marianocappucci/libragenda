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
- **Las migraciones SÍ viajan en el paquete pip, desde la `v0.10.0`.** Viven en
  `libragenda/migrations/` —adentro del paquete, que es lo que las mete en
  `[tool.hatch.build.targets.wheel] packages = ["libragenda"]`— y se aplican con
  el comando de consola que instala el propio paquete:

  ```
  DATABASE_URL=... libragenda-migrar upgrade
  ```

  También `python -m libragenda.migrar`, o `from libragenda.migrar import
  upgrade` desde código. El detalle está en `libragenda/migrar.py`.

  > 🔴 **Esto revierte la decisión del 2026-07-18**, que decía *"el deploy
  > pipeline de cada consumidor clona el repo, no se agrega `migrations/` al
  > wheel"* para no duplicar el empaquetado. El argumento era razonable y el
  > supuesto era falso: **el deploy de un consumidor no es un pipeline con git,
  > es un contenedor** — sin repo que clonar, sin git instalado y sin red
  > saliente garantizada.
  >
  > Lo que costó, medido el 2026-08-24: **ninguna instancia de Gestiolibra ni de
  > MedLibra tenía las migraciones aplicadas**, ni siquiera la tabla
  > `alembic_version`. Su esquema lo creaba `Base.metadata.create_all()` al
  > arrancar. El CI sí las corría —clonando— así que su verde no decía nada
  > sobre lo desplegado.

- `scripts/run_migrations.sh` **sigue existiendo** para el caso que lo
  justifica: aplicar las migraciones de un tag **distinto** del instalado sin
  tocar el entorno. **No es el camino normal.** El normal es
  `libragenda-migrar`, que usa lo que el consumidor ya tiene instalado y por lo
  tanto no se puede desincronizar del pin.
- `libragenda/migrations/env.py` resuelve la base en este orden:
  **`libragenda.url`** del `Config` (la que pone `migrar.configuracion()` cuando
  se le pasa explícita) → `DATABASE_URL` del entorno → `sqlalchemy.url` del
  `alembic.ini`.

  > 🔴 La primera existe porque sin ella el argumento explícito **se ignoraba en
  > silencio**: `DATABASE_URL` ganaba siempre, así que
  > `migrar.upgrade("…/otra_base")` con la variable puesta migraba la del
  > entorno y devolvía éxito.
- El driver se normaliza: `postgresql://` → `postgresql+psycopg://`. Este
  paquete declara psycopg **3** y nada más, y SQLAlchemy resuelve el prefijo
  pelado a psycopg2 — el error resultante manda a instalar el driver
  equivocado. Un `postgresql+psycopg2://` explícito se respeta.
