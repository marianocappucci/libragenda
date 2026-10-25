# Changelog — LibraGenda

## v0.14.0 — 2026-10-25

- 🔴 **`clients` pasa a `agenda_clients`** (ADR-018, migración `0010_agenda_clients`). LibraCore tiene su propia tabla
  `clients` (id entero) y con una sola base por producto las dos no pueden convivir: `libracore-unir-bases` cortaba con
  «la tabla clients existe en el core y en el dominio». Es un `RENAME`, sin copiar ni borrar filas; las claves foráneas
  que la apuntan la siguen solas, y la clave primaria pasa a `agenda_clients_pkey`. Downgrade simétrico (no se puede en
  una base ya unida con LibraCore: aborta con un mensaje que lo dice). `ClientRow` y `AppointmentRow.client_id` usan el
  nombre nuevo.
- 🔴 **La tabla de versión de Alembic es `alembic_version_libragenda`** (ADR-017), no `alembic_version` (que es la de
  LibraCore). **Se autorrenombra**: `libragenda-migrar upgrade` sobre una base de antes mueve la revisión sola, dentro de
  la transacción de la migración; no toca una `alembic_version` que sea del motor.
- Una guarda de que ningún nombre de tabla de LibraGenda choque con los de LibraCore y LibraAuth
  (`tests/test_nombres_de_tablas.py`).

  ⚠️ **Lo que tiene que hacer cada consumidor (GestioLibra y MedLibra, cada uno en su PR):**
  1. subir el pin a `v0.14.0`;
  2. cambiar `ForeignKey("clients.id")` por `ForeignKey("agenda_clients.id")` (`client_billing`, `patients`, `walkins`) y
     cualquier SQL o `Table("clients")` que apunte a la tabla de LibraGenda;
  3. correr `libragenda-migrar upgrade` **antes** de arrancar la aplicación nueva (un pin nuevo con la base sin migrar
     crea una `agenda_clients` vacía con `create_all`, y la migración aborta);
  4. si algo lee `alembic_version` esperando la revisión de LibraGenda, que lea `alembic_version_libragenda`;
  5. en una base nueva, que `libragenda-migrar` corra **antes** que `libracore-migrar` (la `0002` crea `clients`).

  Sin cambio de puerto ni de dominio. Cubierto por `tests/test_migracion_agenda_clients.py` (SQLite y PostgreSQL: base
  nueva, base de antes con datos, repetición, tabla ajena intacta, downgrade/upgrade, convivencia con una `clients` y una
  `alembic_version` de LibraCore) y `tests/test_nombres_de_tablas.py`.

## v0.13.0 — 2026-10-17

- 🔴 **Un recurso secundario (un consultorio) se traba y se valida en la misma transacción que el primario** (ADR-016).
  Lo que MedLibra necesitaba —que dos profesionales no se queden el mismo consultorio a la misma hora— **ya lo hacía el
  motor** desde ADR-009: `reserve()` y `relocate()` toman `SELECT … FOR UPDATE` sobre **todos** los `occupied_resource_ids`
  y `find_conflicts()` compara la intersección. El defecto estaba en el consumidor, que chequeaba la sala aparte y afuera de
  esa transacción. Lo que faltaba acá era poder **usarlo bien**:

  - `AppointmentConflict.resource_ids`: cuáles de los recursos del turno chocaron (el primario y/o los secundarios, en ese
    orden). Un vertical puede decir «consultorio ocupado» o «profesional ocupado» sin volver a mirar los turnos —que, afuera
    del candado, es la carrera que se está cerrando—. Vacío si quien levanta la excepción no lo dice: `AppointmentConflict(id)`
    sigue andando.
  - `InMemoryScheduler.reschedule(…, secondary_resource_ids=None)`: mover un turno puede cambiarlo de sala, y la sala nueva
    se valida y se traba junto con el horario nuevo. `None` conserva las que tiene; `()` las libera.
  - `reserve()`/`relocate()` traban las filas de recurso **en orden de id** (`ORDER BY resources.id`): con dos recursos por
    turno, dos reservas que comparten profesional y sala hacen cola en el mismo orden y no pueden matarse por deadlock.
    No era un defecto medido —el plan de PostgreSQL daba el mismo orden a las dos—; es lo que lo garantiza.

  Sin migración y sin cambio de puerto: cambios aditivos. Cubierto por `tests/test_concurrencia_del_hueco.py` (dos
  profesionales a la misma sala, a la vez, en PostgreSQL real; **verde también contra v0.12.0**, que es la prueba de que el
  motor ya cerraba la carrera) y `tests/test_postgres_real.py` (el orden de los candados, que sí se pone rojo sin el cambio).

## v0.12.0 — 2026-10-16

- 🔴 **El esquema se crea de a un proceso por vez** (`libragenda.crear_esquema`, ADR-015). MedLibra y Gestiolibra crean sus
  tablas en el arranque con `Base.metadata.create_all(get_engine())`; con `uvicorn --workers 2` el arranque corre dos
  veces juntas, `create_all` mira qué falta y después crea (no es atómico en PostgreSQL), y sobre una base sin las tablas
  el segundo `CREATE TABLE` choca en el catálogo (`relation … already exists`). En SQLite, lo mismo con dos procesos sobre
  el mismo archivo. `crear_esquema(engine, metadata=None)` corre el mismo `create_all` en una transacción que empieza
  tomando un candado bloqueante (PostgreSQL: `pg_try_advisory_xact_lock`; SQLite: `BEGIN IMMEDIATE`): el segundo proceso
  espera al primero y encuentra las tablas. `TimeoutError` a los 120 s. **Sin dependencia nueva**: no usa libracore.

  `SqlAlchemyAppointmentRepository.from_url` y `SqlAlchemyTransitionLog.from_url` ya lo usan.

  ⚠️ **No cambia nada hasta que el consumidor lo llame**: reemplazar `Base.metadata.create_all(get_engine())` por
  `crear_esquema(get_engine())` en el `create_app()` de MedLibra y de Gestiolibra. Sin migración ni cambio de puerto.

  Cubierto por `tests/test_esquema_concurrente.py` (dos creaciones simultáneas en PostgreSQL y SQLite, con contraprueba:
  el mismo arnés con `create_all` pelado choca).

## v0.11.0 — 2026-09-16

- 🔴 **Reagendar toma el mismo lock que reservar** (`relocate`). `reschedule()`
  validaba el choque y después escribía con `save()`, **fuera** de la
  transacción: dos reagendados hacia el mismo hueco libre validaban los dos
  contra un estado sin el otro, y entraban los dos. Es la carrera que
  `reserve()` cerró el 2026-08-05 para el alta, viva en el camino espejo — y
  alcanzable por HTTP, porque Gestiolibra y MedLibra exponen
  `POST /appointments/{id}/reschedule`.

  El puerto `AppointmentRepository` gana `relocate(appointment, validator)`:
  mismo contrato que `reserve` pero para un turno que ya existe — toma
  `SELECT … FOR UPDATE` sobre los recursos ocupados, valida y **actualiza**
  dentro de una sola transacción. Bloquea **las mismas filas** que `reserve`,
  que es lo que además serializa un movimiento contra un alta: los dos compiten
  por un hueco, así que tienen que hacer cola en la misma fila.

  ⚠️ **Cambia el puerto**: un consumidor que implemente `AppointmentRepository`
  a mano —Gestiolibra y MedLibra lo hacen, con su envoltorio de hora local—
  tiene que agregar `relocate` antes de subir a esta versión.

  Cubierto por `tests/test_concurrencia_del_hueco.py`, que corre dos escrituras
  simultáneas contra PostgreSQL real, **con su contraprueba**: el test hermano
  reproduce el doble booking por el camino sin lock, así que el verde del
  primero no puede deberse a que los hilos nunca se cruzaron.

## v0.10.0 — 2026-08-24

> 📌 **Esta entrada estaba bajo `[Unreleased]` por error.** Medido el
> 2026-09-16: su commit (`e938dac`) es **ancestro del tag `v0.10.0`**, o sea que
> viajó en esa versión y llevaba tres semanas figurando como sin publicar. Es el
> tipo de dato que hace que un consumidor no suba el pin creyendo que la mejora
> todavía no existe.

- **Las migraciones viajan en el paquete** (ADR-014). `migrations/` pasó a
  `libragenda/migrations/` y se aplican con el comando que instala el propio
  paquete: `DATABASE_URL=… libragenda-migrar upgrade`.

  🔴 **Revierte la decisión del 2026-07-18**, que las dejaba fuera del wheel
  asumiendo que el deploy de un consumidor podía clonar el repo. No puede: es
  un contenedor. El costo, medido el 2026-08-24: ni Gestiolibra ni MedLibra
  tenían las migraciones aplicadas en ninguna instancia, ni la tabla
  `alembic_version`.

  `scripts/run_migrations.sh` se conserva para aplicar un tag distinto del
  instalado; deja de ser el camino normal. Se arreglaron además dos cosas que
  sólo se ven corriendo contra una base real: `postgresql://` a secas resolvía
  a psycopg2 (que el paquete no declara), y el argumento explícito de
  `upgrade(url)` se ignoraba en silencio cuando `DATABASE_URL` estaba puesta.

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
