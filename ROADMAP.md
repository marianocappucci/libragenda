# Roadmap de LibraGenda

## Fase 0 — baseline (completa)

Scaffold, empaquetado, dominio inicial, reglas, casos de uso, repositorios,
PostgreSQL, Alembic, Docker y tag `v0.1.0`.

## Fase 1 — endurecimiento del motor (completa)

- Repositorios CRUD completos para disponibilidad, bloqueos y excepciones.
- Tests de migración contra PostgreSQL.
- Reglas de timezone por sucursal, feriados y consistencia recurso-sucursal.
- CI para push/tag.

## Fase 2 — capacidades de agenda (en curso)

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
- Señás mediante puerto de pagos (siguiente).

## Fase 3 — consumo vertical

- Gestiolibra usa LibraGenda en un entorno dev real.
- MedLibra consume el mismo contrato sin contaminar el motor con clínica.
- Tag estable posterior a la primera integración real.
