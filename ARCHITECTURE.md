# Arquitectura — LibraGenda

## Propósito y límites

LibraGenda es un motor genérico reutilizable de turnos y agenda. Es peer de LibraCore y no depende de él. Los productos verticales consumen el paquete y conservan su dominio específico.

El motor no incluye lógica clínica, gastronómica ni de facturación, y actualmente no levanta una API HTTP propia.

## Capas

- `domain.py`: entidades y reglas de valor, sin SQLAlchemy ni FastAPI.
- `scheduling.py`: reglas puras de disponibilidad, solapamientos y bloqueos.
- `application.py`: casos de uso y transiciones de estado.
- `repositories.py`: puertos y adaptadores en memoria.
- `sqlalchemy_repository.py`, `catalog_repository.py`: persistencia SQLAlchemy.
- `database.py`: configuración de conexión del proceso consumidor.
- `migrations/`: cambios de esquema gestionados por Alembic.

## Persistencia

PostgreSQL es el destino de producción. SQLite se usa en tests. Cada producto y entorno tiene base y usuario propios; no se comparte schema entre consumidores.

Las migraciones no viajan en el wheel: el pipeline del consumidor clona LibraGenda en `LIBRAGENDA_REF`, instala el paquete y ejecuta `alembic upgrade head` antes de iniciar la API del consumidor.

## Integración y deploy

El producto vertical configura `DATABASE_URL`, construye la factoría de sesiones y los repositorios. LibraGenda se versiona con tags SemVer y los consumidores pinean una versión exacta.

## Entornos

- Desarrollo: ejecución local o entorno dev del consumidor.
- Demo: entorno de producción controlada del consumidor.
- Producción: dominio del cliente del consumidor.

La rama observada actualmente en este repositorio es `main`; la adopción de `develop` como rama de integración queda pendiente de una decisión operativa explícita.
