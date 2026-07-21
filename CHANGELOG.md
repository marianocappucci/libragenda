# Changelog — LibraGenda

## [Unreleased]

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
