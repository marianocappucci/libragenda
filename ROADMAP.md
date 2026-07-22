# Roadmap de LibraGenda

## Fase 0 — baseline (completa)

Scaffold, empaquetado, dominio inicial, reglas, casos de uso, repositorios,
PostgreSQL, Alembic, Docker y tag `v0.1.0`.

## Fase 1 — endurecimiento del motor (completa)

- Repositorios CRUD completos para disponibilidad, bloqueos y excepciones.
- Tests de migración contra PostgreSQL.
- Reglas de timezone por sucursal, feriados y consistencia recurso-sucursal.
- CI para push/tag.

## Fase 2 — capacidades de agenda (completa)

- Recurrencias (completo). `RecurrenceRule` + `generate_occurrences()`
  semanal-en-días-fijos, desacoplado de `Appointment` (solo genera
  datetimes). `Appointment.series_id` opcional agrupa las ocurrencias;
  `InMemoryScheduler.list_series()`/`cancel_series()` operan sobre el grupo.
- Recordatorios mediante puerto de notificaciones (completo).
  `ReminderPolicy` (lead time nombrado) + `due_reminders()` pura + puerto
  `NotificationPort` (el motor no arma el texto del mensaje, eso es del
  consumidor). `ReminderDispatcher` conecta la regla con el puerto y el
  ledger de enviados (`sent_reminders`, con unique constraint) para no
  reenviar. Persistencia SQL + versión en memoria.
- Señas mediante puerto de pagos (completo). `Deposit`/`DepositStatus` (una
  seña por turno, monto lo decide el llamador, no un % configurado en
  `Service`) + `PaymentPort` (cobro/reembolso, sin lógica de proveedor).
  `DepositManager` valida transiciones (pending→paid/failed, paid→refunded)
  y llama al puerto antes de persistir. **Sin gating**: el motor no bloquea
  `confirm()` por seña impaga — cada vertical decide su propia política.
  Persistencia SQL (`deposits`, unique constraint en `appointment_id`) +
  versión en memoria.

## Fase 3 — consumo vertical (completa)

- Gestiolibra usa LibraGenda en un entorno dev real (completo). Pin
  actualizado a `v0.3.0`, base `gestiolibra` dedicada (Postgres 16 del VPS
  Donweb, mismo contenedor que la de LibraGenda, usuario propio
  `gestiolibra_dev`) migrada con la cadena Alembic completa (`0001`→`0006`)
  aplicada desde un checkout de esa versión exacta (las migraciones no
  viajan en el paquete pip). Verificado con un flujo real de alta de
  sucursal/recurso/servicio/cliente + crear/confirmar turno usando los
  repositorios SQLAlchemy reales (no el `create_all()` del demo) contra esa
  base migrada — no solo que el pin instale, sino que el schema real
  funcione end-to-end. Confirmó que las Fases 1-2 fueron aditivas: el
  smoke test sqlite preexistente de Gestiolibra siguió pasando sin tocar
  código de la app.
- MedLibra consume el mismo contrato sin contaminar el motor con clínica
  (completo). Repo creado desde cero (`github.com/marianocappucci/medlibra`,
  privado) con el mismo scaffold que Gestiolibra: FastAPI, LibraGenda
  `v0.3.0` pineado, sin ningún dominio clínico todavía (eso es Fase 1 propia
  de MedLibra). Base `medlibra` dedicada (mismo Postgres 16 del VPS Donweb,
  usuario propio `medlibra_dev`, sin compartir schema con LibraGenda ni con
  Gestiolibra) migrada con la misma cadena Alembic (`0001`→`0006`) y
  verificada end-to-end con los repositorios SQLAlchemy reales. Prueba que
  dos consumidores verticales distintos (turnos genéricos vs. salud) usan
  el mismo motor sin que LibraGenda necesite saber cuál es cuál.
- Tag estable posterior a la primera integración real (completo). `v0.4.0`
  cerró la integración inicial; el consumo real en Gestiolibra/MedLibra
  siguió encontrando gaps genuinos (CRUD faltante en el catálogo maestro,
  fix de datetimes cross-dialecto) que se corrigieron en `v0.4.1`/`v0.4.2`
  — exactamente el tipo de hallazgo que esta fase buscaba sacar a la luz.
  `v0.4.2` es el tag estable que cierra la fase.

## Post-Fase 3 — motivo de cancelación/reprogramación (completo)

Gestiolibra (en curso) y MedLibra (próxima) tenían de forma independiente
"cancelar y reprogramar turnos con motivos" en su propio roadmap — señal de
que era mejor resolverlo una vez en el motor que dejar que cada vertical
inventara su propia tabla lateral. `Appointment.reason` (opcional, sin
validar contenido ni política de anticipación) + `cancel()`/`reschedule()`/
`cancel_series()` aceptan `reason`. Migración `0007_appointment_reason`.

## Post-Fase 3 — SQLite por defecto para toda la familia (completo)

Surgió al scopear si MedLibra debía componer LibraCore para facturación:
Contalibra/Restolibra despliegan con arquitectura silo real (instancia +
base SQLite aislada por cliente) y Gestiolibra/MedLibra ya prevén el
mismo patrón — mantener estos dos en Postgres no aportaba nada y
complicaba cualquier composición futura con LibraCore (SQLite-only, sin
capa de abstracción). Decisión del usuario: SQLite pasa a ser el default
documentado de toda la familia (Postgres sigue soportado, no obligatorio).
`configure()` activa `PRAGMA foreign_keys=ON` para toda conexión SQLite
(antes solo se aplicaban opciones de pool al caso especial
`sqlite:///:memory:`). Corregidas migraciones que asumían `ALTER` de
constraints, no soportado directamente por SQLite (`0002`, `0003`,
`0005`) — batch mode o declaración en `create_table()`, sin cambio de
comportamiento en Postgres. Ver `DECISIONS.md` ADR-005.

## Post-Fase 3 — `complete()` del turno (completo)

Primer paso del plan acordado para retomar la integración de
facturación/caja de MedLibra con LibraCore (pausada el 2026-07-22 por
alcance real): el estado `COMPLETED` ya existía en la máquina de
transiciones (`_ALLOWED_TRANSITIONS` permitía `confirmed`/`in_progress`
→ `completed`) pero sin método público en `InMemoryScheduler` — un
consumidor no tenía forma de marcar un turno como completado, que es lo
que MedLibra necesita como disparador de facturación automática.
`InMemoryScheduler.complete(appointment_id)` expone esa transición, sin
`reason` (no es una cancelación). Sin migración nueva: la columna
`status` ya soporta el valor. Ver `DECISIONS.md` ADR-006.

## Post-Fase 3 — `medio_pago` en depósitos/señas (completo)

Segundo paso del mismo plan de facturación de MedLibra: para registrar el
cobro de una seña en el módulo de caja de LibraCore
(`libracore.db.caja.create_caja_movimiento`) hace falta saber el medio de
pago usado (efectivo, transferencia, etc.), dato que `Deposit` no tenía.
`DepositManager.mark_paid(deposit_id, medio_pago=None)` lo acepta opcional
(texto libre, sin validar contenido ni mapear a proveedor — mismo trato que
`Appointment.reason`) y lo preserva en `request_refund()`. Migración
`0008_deposit_medio_pago`. Ver `DECISIONS.md` ADR-007.
