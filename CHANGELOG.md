# Changelog — LibraGenda

## [Unreleased]

Reparto motor / vertical del sistema de agendas de salud de MedLibra: al motor
la ocupación del tiempo, al vertical lo que le pasa a una persona durante la
jornada. Ver `DECISIONS.md`, bloque previo a ADR-009.

- **Recursos secundarios**: `Appointment.secondary_resource_ids` y
  `find_conflicts()` comparando la **intersección** de recursos ocupados — un
  turno puede ocupar el profesional **y** la sala, y cualquiera de los dos
  bloquea. Los `TimeBlock` pasan a chequearse contra todos los recursos
  ocupados, así que un consultorio en mantenimiento es inreservable sin
  ningún concepto nuevo. Tabla `appointment_resources`. ADR-009.
- **`InMemoryScheduler.start()`**: expone la transición a `IN_PROGRESS`, que la
  máquina de estados permitía desde `confirmed` sin método público. Sin
  migración. ADR-010.
- **Registro de transiciones**: `AppointmentTransition`,
  `TransitionLogRepository`, `InMemoryTransitionLog`, `SqlAlchemyTransitionLog`
  y `scheduler.history()`. Append-only, con actor y motivo; las marcas de
  tiempo de inicio y fin se **leen** de ahí con `first_time_at()` en vez de
  vivir como columnas del turno. Tabla `appointment_transitions`. ADR-011.
- **Vigencia e intervalo de agenda**: `Availability.valid_from`/`valid_to` y
  `AgendaPolicy(slot_interval, max_overbookings_per_day)`. Tabla
  `agenda_policies`. ADR-012.
- **Sobreturno autorizado**: `create(..., allow_overbooking=True)` con tope
  diario por agenda, `Appointment.overbooked` y `OverbookingLimitReached`.
  ADR-013.
- Migración `0009_occupancy_and_history`. **Todo aditivo**: los 120
  tests previos pasan sin tocar ninguno, y una base con datos en `0008` migra
  conservando cada fila.

## v0.9.0 — 2026-07-22

- **`SentReminderRepository.list_sent(date_from, date_to)`** y
  **`DepositRepository.list_by_status(status)`**: consultas de lectura
  necesarias para el dashboard de MedLibra/Gestiolibra (recordatorios
  enviados y señas pendientes en un rango). Sin migración: solo
  lectura sobre columnas ya existentes.

## v0.8.0 — 2026-07-22

- **`Deposit.medio_pago`** (opcional, texto libre): `DepositManager.mark_paid()`
  ahora acepta el medio de pago usado, preservado en `request_refund()`.
  Migración `0008_deposit_medio_pago`. Segundo paso del plan de facturación
  de MedLibra con LibraCore (necesita saber cómo se cobró una seña para
  registrar el movimiento de caja correspondiente). Ver `DECISIONS.md` ADR-007.

## v0.7.0 — 2026-07-22

- **`InMemoryScheduler.complete()`**: expone la transición a `COMPLETED`
  (ya permitida por la máquina de estados desde `confirmed`/`in_progress`,
  sin método público hasta ahora). Primer paso del plan acordado con
  MedLibra para disparar facturación automática al completar un turno.
  Ver `DECISIONS.md` ADR-006.

## v0.6.0 — 2026-07-22

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
