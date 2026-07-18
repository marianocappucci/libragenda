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

## Fase 3 — consumo vertical (en curso)

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
- MedLibra consume el mismo contrato sin contaminar el motor con clínica.
- Tag estable posterior a la primera integración real.
