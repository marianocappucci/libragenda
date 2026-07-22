# Changelog — LibraGenda

## [Unreleased]

- **SQLite pasa a ser el destino de producción por defecto** para toda la
  familia Libra (silo por cliente), Postgres queda como opción soportada
  para el caso puntual que lo amerite — ver `DECISIONS.md` ADR-005.
  `configure(url)` activa `PRAGMA foreign_keys=ON` en cualquier conexión
  SQLite (antes solo aplicaba opciones de pool al caso especial
  `sqlite:///:memory:`, sin tocar FKs). Corregidas migraciones que
  asumían soporte de `ALTER` para constraints
  (`0002_domain_entities.py`, `0003_timezone_holidays_branch.py`,
  `0005_sent_reminders.py`) — envueltas en `op.batch_alter_table()` o
  declaradas en `create_table()`, sin cambio de comportamiento en
  Postgres. Verificado migrando/revirtiendo contra SQLite real y contra
  Postgres real.

## v0.5.0 — 2026-07-21

- Motivo opcional (`reason`) en `cancel()`, `reschedule()` y `cancel_series()`,
  persistido en `appointments.reason` (migración `0007_appointment_reason`).
- Normalización documental al estándar híbrido por producto.

## v0.4.2 — 2026-07-18

- Normalización de datetimes para mantener valores UTC-aware con SQLite.

## v0.4.1

- CRUD completo para branches, clients, resources y services.

## v0.4.0 — 2026-07-18

- Verificación del scaffold de MedLibra en entorno dev real.

## v0.3.0

- Agregadas señas mediante puerto de pagos y `DepositManager`.

## v0.2.0

- Agregado CI con PostgreSQL real para push y tags.
- Agregadas reglas de timezone, feriados y consistencia recurso-sucursal.
- Agregadas pruebas de migración Alembic contra PostgreSQL real.

## v0.1.0

- Baseline inicial del motor, empaquetado, dominio, persistencia, Docker y migraciones.
