# LibraGenda

Motor genérico reutilizable de turnos y agenda para productos de la familia
Libra. Es un módulo independiente y peer de
[LibraCore](https://github.com/marianocappucci/libracore): ningún motor
depende del otro.

Los primeros consumidores previstos son Gestiolibra y MedLibra. El motor debe
mantenerse agnóstico del vertical: un recurso puede ser una persona, un
consultorio, una cabina, una máquina o cualquier otra cosa reservable.

## Estado

Primera API de dominio definida, sin persistencia ni framework. Incluye
`Resource`, `Service`, `Availability`, `Appointment` y `AppointmentStatus`.
La persistencia usa SQLAlchemy 2, con **SQLite como destino de producción
por defecto** para toda la familia Libra (silo: una instancia por
cliente — ver `DECISIONS.md` ADR-005) y PostgreSQL disponible como
opción para el caso puntual que lo amerite. `configure(url)` activa
`PRAGMA foreign_keys=ON` automáticamente en cualquier conexión SQLite. El
esquema mínimo actual contiene la tabla `appointments`; el repositorio
recibe una `sessionmaker` y los casos de uso continúan sin conocer
SQLAlchemy.

## Documentación

- [ROADMAP.md](ROADMAP.md) — dirección estratégica.
- [TASKS.md](TASKS.md) — trabajo concreto vigente.
- [ARCHITECTURE.md](ARCHITECTURE.md) — arquitectura actual.
- [CONVENTIONS.md](CONVENTIONS.md) — estándares del código.
- [DECISIONS.md](DECISIONS.md) — decisiones y motivos.
- [CHANGELOG.md](CHANGELOG.md) — releases publicados.

## Desarrollo

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Versionado

Semver mediante tags de Git (`vX.Y.Z`), con versión derivada automáticamente
por `hatch-vcs`. Los consumidores deben pinear una versión exacta.


## Integración de un producto vertical

LibraGenda no levanta una API HTTP propia. El producto vertical configura la
conexión durante su arranque y construye sus repositorios:

```python
from libragenda.database import configure, get_session_factory
from libragenda import SqlAlchemyAppointmentRepository, SqlAlchemyCatalogRepository

configure(os.environ["LIBRAGENDA_DATABASE_URL"])  # sqlite:///data/producto.db por defecto
sessions = get_session_factory()
appointments = SqlAlchemyAppointmentRepository(sessions)
catalog = SqlAlchemyCatalogRepository(sessions)
```

Las migraciones Alembic se ejecutan como paso de deploy antes de iniciar la
API del producto.
