# Módulos de LibraGenda

## Implementados

- `domain`: recursos, servicios, disponibilidad, turnos, estados, sucursales,
  clientes, feriados (`Holiday`) y series (`Appointment.series_id`).
  `Appointment.secondary_resource_ids` — recursos extra que el turno ocupa
  además del primario (una sala, un box, un equipo compartido); el motor no
  les asigna significado, solo ocupación. `Availability.valid_from`/`valid_to`
  — vigencia opcional de una ventana semanal; sin ninguno de los dos, rige
  siempre. `AppointmentTransition` + `first_time_at()` — el historial de
  estados y las marcas de tiempo que se leen de él, en vez de columnas.
- `scheduling`: solapamientos, bloqueos, excepciones, feriados por sucursal y
  consistencia recurso-sucursal. `find_conflicts()` compara la **intersección**
  de recursos ocupados, así que un profesional y una sala se bloquean entre
  sí; acepta un `gap` que exige aire entre turnos. Las ventanas semanales,
  feriados y excepciones se le piden solo al recurso **primario** (una sala no
  tiene horario de atención), pero los `TimeBlock` corren contra **todos** los
  recursos ocupados — de ahí que un consultorio en mantenimiento sea
  inreservable sin ningún concepto nuevo. `AgendaPolicy` — intervalo entre
  turnos y tope diario de sobreturnos por recurso, con default permisivo vía
  `policy_for()`.
- `timezones`: conversión explícita UTC ↔ hora local de sucursal (el motor
  no infiere zonas horarias por su cuenta).
- `recurrence`: `RecurrenceRule` + `generate_occurrences()`, generación pura
  de ocurrencias semanales, desacoplada de `Appointment`.
- `notifications`: `ReminderPolicy` + `due_reminders()` (regla pura de
  vencimiento) + `NotificationPort` (puerto de envío, sin texto/canal —
  eso es del consumidor).
- `reminder_dispatcher`: conecta la regla de recordatorios con el puerto y
  el ledger de enviados (`SentReminderRepository`), evitando reenvíos.
  `SentReminderRepository.list_sent(date_from, date_to)` — recordatorios
  enviados en un rango, para reportes (necesidad real de MedLibra/
  Gestiolibra, no una consulta especulativa).
- `payments`: `Deposit`/`DepositStatus` (una seña por turno, monto lo decide
  el llamador) + `PaymentPort` (puerto de cobro/reembolso, sin lógica de
  proveedor). `DepositManager` valida las transiciones (pending→paid/failed,
  paid→refunded) y llama al puerto antes de persistir. `mark_paid()` acepta
  un `medio_pago: str | None` opcional (texto libre, ej. "efectivo",
  "transferencia" — el motor no lo valida ni lo mapea a ningún proveedor);
  se preserva en `request_refund()`. `list_by_status(status)` — señas por
  estado (ej. pendientes), para reportes. El motor **no** bloquea
  `Appointment.confirm()` por seña impaga — es tracking separado; cada
  vertical decide su propia política de gating.
- `application`: crear, confirmar, **arrancar**, completar, cancelar,
  reprogramar, y operar sobre series completas (`list_series`/`cancel_series`).
  `complete()` transiciona a `COMPLETED` desde `confirmed`/`in_progress` (ya
  permitido por `_ALLOWED_TRANSITIONS`, sin método público hasta ahora); sin
  `reason`, no es una cancelación. `start()` hace lo propio hacia
  `IN_PROGRESS`, mismo hueco de superficie. `cancel`/`reschedule`/
  `cancel_series` aceptan un `reason: str | None` opcional (motivo de
  cancelación o reprogramación); el motor no lo valida más allá de "no vacío
  si se da" ni aplica política de anticipación — eso es decisión de cada
  vertical. `create()`/`reschedule()` aceptan `allow_overbooking`: la
  excepción **sancionada** a la regla de solapamiento, acotada por el tope
  diario de la `AgendaPolicy` — relaja solo el conflicto, nunca horarios,
  feriados ni bloqueos, y marca `Appointment.overbooked` únicamente si el
  turno se superpuso de verdad. Todos los verbos aceptan un `actor` opcional
  que va al historial; `history()` devuelve las transiciones del turno,
  creación incluida.
- `repositories`: interfaz de turnos + memoria; interfaz de recordatorios
  enviados + memoria; interfaz de depósitos + memoria; interfaz del historial
  de transiciones + memoria (`TransitionLogRepository`, append-only: sin
  update ni delete, porque una historia editable no responde nada).
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
