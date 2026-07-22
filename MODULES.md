# Módulos de LibraGenda

## Implementados

- `domain`: recursos, servicios, disponibilidad, turnos, estados, sucursales,
  clientes, feriados (`Holiday`) y series (`Appointment.series_id`).
- `scheduling`: solapamientos, bloqueos, excepciones, feriados por sucursal y
  consistencia recurso-sucursal.
- `timezones`: conversión explícita UTC ↔ hora local de sucursal (el motor
  no infiere zonas horarias por su cuenta).
- `recurrence`: `RecurrenceRule` + `generate_occurrences()`, generación pura
  de ocurrencias semanales, desacoplada de `Appointment`.
- `notifications`: `ReminderPolicy` + `due_reminders()` (regla pura de
  vencimiento) + `NotificationPort` (puerto de envío, sin texto/canal —
  eso es del consumidor).
- `reminder_dispatcher`: conecta la regla de recordatorios con el puerto y
  el ledger de enviados (`SentReminderRepository`), evitando reenvíos.
- `payments`: `Deposit`/`DepositStatus` (una seña por turno, monto lo decide
  el llamador) + `PaymentPort` (puerto de cobro/reembolso, sin lógica de
  proveedor). `DepositManager` valida las transiciones (pending→paid/failed,
  paid→refunded) y llama al puerto antes de persistir. `mark_paid()` acepta
  un `medio_pago: str | None` opcional (texto libre, ej. "efectivo",
  "transferencia" — el motor no lo valida ni lo mapea a ningún proveedor);
  se preserva en `request_refund()`. El motor **no** bloquea
  `Appointment.confirm()` por seña impaga — es tracking separado; cada
  vertical decide su propia política de gating.
- `application`: crear, confirmar, completar, cancelar, reprogramar, y operar
  sobre series completas (`list_series`/`cancel_series`). `complete()`
  transiciona a `COMPLETED` desde `confirmed`/`in_progress` (ya permitido por
  `_ALLOWED_TRANSITIONS`, sin método público hasta ahora); sin `reason`, no es
  una cancelación. `cancel`/`reschedule`/`cancel_series` aceptan un
  `reason: str | None` opcional (motivo de cancelación o reprogramación); el
  motor no lo valida más allá de "no vacío si se da" ni aplica política de
  anticipación — eso es decisión de cada vertical.
- `repositories`: interfaz de turnos + memoria; interfaz de recordatorios
  enviados + memoria; interfaz de depósitos + memoria.
- `sqlalchemy_repository` / `catalog_repository` / `availability_repository`
  / `reminder_repository` / `deposit_repository`: persistencia SQLAlchemy,
  SQLite por defecto (Postgres soportado, ver ADR-005 de `DECISIONS.md`).
- `database`: configuración de engine/session factory. Activa
  `PRAGMA foreign_keys=ON` automáticamente para cualquier conexión SQLite.

## Próximos

Sin ítems pendientes de Fase 2 (ver `ROADMAP.md`).

## Fuera del motor

Autenticación de producto, roles, facturación, caja, clínica, recetas, cocina,
plantillas HTML y routers HTTP pertenecen a los consumidores.
