# Decisiones arquitectónicas — LibraGenda

Registro ADR. Las decisiones no se borran; si dejan de aplicar, se marcan como reemplazadas.

## ADR-001 — Mantener LibraGenda como motor agnóstico de vertical

- Estado: aceptada
- Fecha: 2026-07-18
- Contexto: el motor será consumido por productos de servicios generales y salud.
- Decisión: mantener el motor genérico y excluir lógica clínica, gastronómica y de facturación.
- Consecuencias: cada vertical implementa su dominio específico sin contaminar el paquete común.

## ADR-002 — No crear una API HTTP propia por ahora

- Estado: aceptada provisionalmente
- Fecha: 2026-07-18
- Contexto: LibraGenda es un motor reutilizable integrado por productos verticales.
- Decisión: los consumidores configuran PostgreSQL y construyen sus repositorios; LibraGenda no levanta una API HTTP propia.
- Consecuencias: menor acoplamiento y despliegue más simple; debe revisarse si aparecen consumidores que necesiten una API independiente.

## ADR-003 — Mantener migraciones fuera del wheel

- Estado: aceptada
- Fecha: 2026-07-18
- Contexto: los consumidores necesitan aplicar el schema exacto de la versión pineada.
- Decisión: el deploy clona el repositorio en el tag exacto y ejecuta Alembic; el wheel contiene solo el paquete Python.
- Consecuencias: una única fuente de migraciones en Git y un paso explícito de deploy.

## ADR-004 — Base y usuario dedicados por producto y entorno

- Estado: **reemplazada parcialmente por ADR-005** (2026-07-22) — sigue
  aplicando tal cual si un producto usa PostgreSQL, pero PostgreSQL dejó
  de ser el destino de producción por defecto de la familia.
- Fecha: 2026-07-18
- Contexto: LibraGenda, Gestiolibra y MedLibra conviven en PostgreSQL.
- Decisión: cada producto y entorno usa una base y usuario propios, sin schema compartido.
- Consecuencias: aislamiento de datos y menor riesgo de interferencia entre consumidores.

## ADR-005 — SQLite por defecto para toda la familia Libra (silo por cliente)

- Estado: aceptada
- Fecha: 2026-07-22
- Contexto: al scopear si MedLibra debía componer LibraCore para
  facturación, salió a la luz que Contalibra/Restolibra despliegan con
  arquitectura silo real — una instancia/contenedor aislado por cliente,
  cada uno con su propia base SQLite — y que Gestiolibra/MedLibra ya
  prevén exactamente el mismo patrón de despliegue (Docker,
  `panel_admin.py`, sin infraestructura de producción propia todavía). En
  ese modelo, tener Gestiolibra/MedLibra en PostgreSQL mientras el resto
  de la familia usa SQLite no aportaba nada — obligaba a correr (o
  planear correr) dos motores de base de datos en paralelo sin necesidad
  real, y complicaba de raíz cualquier composición futura con LibraCore
  (que ya está construido sobre SQLite sin capa de abstracción). Decisión
  del usuario, explícita: "registremos que todos los productos de la
  familia normalicen el uso de sqlite a menos que el sistema amerite otra
  cosa".
- Decisión: SQLite es el motor de base de datos **por defecto** para
  todo producto de la familia Libra, incluido el propio LibraGenda como
  motor consumido por ellos. `configure(url)` sigue aceptando cualquier
  URL soportada por SQLAlchemy — Postgres no se eliminó como opción,
  sigue disponible para el caso puntual que lo amerite (ver
  `CONVENTIONS.md`) — pero deja de ser el default documentado. Se agregó
  `PRAGMA foreign_keys=ON` automático para toda conexión SQLite (antes
  solo se aplicaban opciones de pool para el caso especial
  `sqlite:///:memory:`, sin tocar FKs) — sin esto, SQLite no fuerza
  integridad referencial y un bug de ese tipo (borrado de fila padre
  antes que su extensión con FK) ya pasó desapercibido una vez en
  MedLibra hasta verificar contra Postgres real (ver `DECISIONS.md` de
  MedLibra, ADR-011). Se corrigieron además migraciones que asumían
  soporte de `ALTER` para constraints (`create_foreign_key`/
  `drop_constraint`/`create_unique_constraint` fuera de `create_table`),
  que SQLite no soporta directamente — envueltas en
  `op.batch_alter_table()` (rebuild copy-and-move en SQLite, `ALTER`
  nativo sin cambios de comportamiento en Postgres) o, cuando la
  constraint nace en la misma migración que la tabla, declaradas
  directamente en `create_table()` en vez de una `ALTER` separada.
- Consecuencias: verificado migrando y revirtiendo (`upgrade head` /
  `downgrade base`) contra un archivo SQLite real y, por separado, contra
  PostgreSQL real, confirmando que ambos caminos siguen funcionando sin
  cambios de comportamiento — el fix es estructural (compatible con
  ambos dialectos), no un parche solo-SQLite. Cada consumidor decide su
  propia URL vía `configure()`; este ADR fija cuál es el default
  recomendado para la familia, no una obligación técnica del motor.

## ADR-006 — Exponer `complete()` como método público del turno

- Estado: aceptada
- Fecha: 2026-07-22
- Contexto: al retomar el plan de integración de facturación/caja de
  MedLibra con LibraCore (pausado el 2026-07-22 por alcance real —
  ver `DECISIONS.md`/`TASKS.md` de MedLibra), el primer paso acordado era
  que LibraGenda exponga una forma de completar un turno, ya que MedLibra
  necesita ese evento como disparador de la facturación automática (saldo
  de consulta + seña cobrada). El estado `AppointmentStatus.COMPLETED` y
  las transiciones que lo permiten (`confirmed`/`in_progress` →
  `completed`) ya existían en `_ALLOWED_TRANSITIONS` desde el diseño
  original de la máquina de estados — nadie había necesitado completar un
  turno programáticamente hasta ahora, así que no tenía método público en
  `InMemoryScheduler` (mismo patrón que `confirm()`/`cancel()`, sin
  gap de diseño real, solo de superficie de API).
- Decisión: `InMemoryScheduler.complete(appointment_id)` reutiliza
  `_transition()` como los demás verbos de estado. Sin `reason` (no es
  una cancelación ni una reprogramación, no aplica el campo). Sin
  migración: `status` ya acepta el valor `completed` desde el esquema
  original.
- Consecuencias: 4 tests nuevos (transición válida desde `confirmed` y
  desde `in_progress`, rechazo desde `pending`, rechazo de completar dos
  veces). Verificado con la suite completa contra SQLite (112 tests) y
  contra PostgreSQL real (115 tests, incluye los 3 tests de migración que
  solo corren con `DATABASE_URL` seteado). Cambio 100% aditivo: ningún
  test ni comportamiento previo cambia. Sigue pendiente el resto del plan
  (extraer la orquestación de facturación de Contalibra a LibraCore;
  MedLibra construye la integración encima) — ver `TASKS.md` de MedLibra.

## ADR-007 — Agregar `medio_pago` opcional a `Deposit`

- Estado: aceptada
- Fecha: 2026-07-22
- Contexto: segundo paso del plan de facturación de MedLibra con
  LibraCore, después de ADR-006. Para registrar el cobro de una seña como
  movimiento de caja en `libracore.db.caja` (`create_caja_movimiento`,
  que requiere `medio_pago`) y para decidir cómo facturarla, MedLibra
  necesita saber con qué medio se pagó — dato que `Deposit` no
  capturaba en ningún lado del motor (el `ManualPaymentPort` de
  Gestiolibra/MedLibra confirma el pago a mano, pero solo con
  `mark-paid`/`mark-failed`/`refund`, sin registrar el medio).
- Decisión: `Deposit.medio_pago: str | None = None` (texto libre, sin
  validar contenido ni mapear a ningún proveedor — mismo criterio que
  `Appointment.reason`). `DepositManager.mark_paid(deposit_id,
  medio_pago=None)` lo acepta opcional; `request_refund()` lo preserva
  del depósito pagado. Migración `0008_deposit_medio_pago` (columna
  nullable, sin default).
- Consecuencias: 6 tests nuevos (dominio: rechaza medio_pago en blanco,
  acepta valor; manager: mark_paid con/sin medio_pago, refund lo
  preserva; repositorio: round-trip). Verificado con la suite completa
  contra SQLite (118 tests) y PostgreSQL real (121 tests) + migración
  `upgrade head` → `downgrade -1` → `upgrade head` contra un archivo
  SQLite real, confirmando que el `batch_alter_table` del downgrade
  funciona (lección de ADR-005: `drop_column` fuera de batch mode no
  funciona en SQLite). Cambio 100% aditivo. Sigue pendiente el paso
  final del plan: MedLibra construye la integración de facturación
  encima de esto y de `libracore.arca_facturacion` (ver `TASKS.md` de
  MedLibra).

## ADR-008 — Consultas de lectura para dashboards: `list_sent()` y `list_by_status()`

- Estado: aceptada
- Fecha: 2026-07-22
- Contexto: MedLibra (y después Gestiolibra) empezaron el dashboard de
  Fase 2 pidiendo "recordatorios enviados en un rango" y "señas
  pendientes de confirmar" — ninguna de las dos consultas existía en el
  motor. `SentReminderRepository` solo sabía responder "¿está enviado
  este par (turno, política)?" (`sent_pairs`, pensado para el propio
  `ReminderDispatcher` evitando reenvíos, no para reportar). `DepositRepository`
  solo sabía buscar por id o por turno — sin forma de listar por estado.
- Decisión: `SentReminderRepository.list_sent(date_from, date_to) ->
  list[tuple[str, str, datetime]]` (appointment_id, policy_id, sent_at) y
  `DepositRepository.list_by_status(status: DepositStatus) -> list[Deposit]`.
  Ambas puramente de lectura, sin ninguna política de negocio — el motor
  no decide qué cuenta como "reciente" ni arma ningún reporte, cada
  vertical arma su propio dashboard encima. Mismo criterio que el resto
  de los métodos de listado del motor (`list_series`, `list()` de
  `AppointmentRepository`).
- Consecuencias: sin migración (ambas leen columnas que ya existían:
  `sent_reminders.sent_at`, `deposits.status`). Tag `v0.9.0`. 3 tests
  nuevos, verificado con la suite completa contra SQLite (123 tests) y
  PostgreSQL real (123 tests). `InMemorySentReminderRepository` pasó de
  guardar solo el par `(appointment_id, policy_id)` en un `set` a
  guardar también `sent_at` en un `dict` — necesario para que el
  adaptador en memoria pueda filtrar por rango igual que el real.

---

> **ADR-009 a ADR-013 salen de una misma decisión de alcance** (2026-08-04):
> el reparto entre este motor y MedLibra para su sistema de agendas de salud,
> bajo la regla **"LibraGenda es dueño de la ocupación del tiempo; el vertical,
> de lo que le pasa a una persona durante la jornada"**. Los cinco son
> aditivos y ninguno obliga a tocar Gestiolibra. Lo que quedó **afuera** por
> esa misma regla: el eje asistencial de estados (sala de espera, llamado), las
> especialidades, las coberturas y el llamador de pacientes — todo eso vive en
> el vertical. Ver la página `medlibra-agendas-y-flujo-de-atencion` del wiki.

## ADR-009 — El consultorio entra como recurso secundario genérico, no como entidad "sala"

- Estado: aceptada
- Fecha: 2026-08-04
- Contexto: MedLibra necesita detectar que dos profesionales quedaron
  agendados en el mismo consultorio a la misma hora. Hasta hoy un turno
  ocupaba **exactamente un** `Resource`, y todo el motor colgaba de
  `appointment.resource_id`: disponibilidad, bloqueos, excepciones,
  chequeo de sucursal y solapamiento. Modelar el consultorio como un
  `Resource` más no alcanzaba: el turno solo podía apuntar a uno de los
  dos, así que se detectaba el choque de profesional o el de sala, nunca
  los dos.
- Decisión: `Appointment.secondary_resource_ids: tuple[str, ...] = ()`, y
  `find_conflicts()` compara la **intersección** de los recursos ocupados
  (`occupied_resource_ids`, primario + secundarios) en vez de
  `resource_id ==`. **El motor no aprende la palabra "consultorio"**:
  aprende que un turno puede ocupar más de un recurso, que es el mismo
  problema de un box de taller, una estación de lavado o un equipo
  compartido. Los atributos de sala (piso, sector, equipamiento,
  especialidades permitidas) quedan en el vertical como fila de
  extensión sobre `Resource` — mismo patrón que MedLibra ya usa para
  `PatientRow` sobre `Client`.
  - **Horarios y bloqueos se tratan distinto, a propósito**: las ventanas
    semanales, feriados y excepciones se le piden **solo al recurso
    primario** —una sala es una cosa, no una agenda, y exigirle ventana
    horaria a un consultorio sería declararle jornada laboral a una
    habitación—, pero los `TimeBlock` se chequean contra **todos** los
    recursos ocupados. Eso hace que un consultorio en mantenimiento sea
    inreservable **sin un solo concepto nuevo**: es el `TimeBlock` que ya
    existía. Igual para la licencia de un profesional.
  - `check_resource_branch` también pasa a correr sobre todos los
    recursos ocupados: una sala de otra sede es tan inválida como un
    profesional de otra sede.
- Consecuencias: tabla `appointment_resources` (join, con `position` solo
  para que la tupla vuelva en el orden en que se escribió) y migración
  `0009`. Con la tupla vacía —el default— el comportamiento es
  **idéntico** al anterior: los 120 tests previos pasaron sin tocar
  ninguno. **Un bug real apareció acá y lo encontró un test**: reasignar
  la colección entera en `save()` hace que SQLAlchemy inserte antes de
  borrar los huérfanos, y un recurso presente antes y después choca
  contra el unique `(appointment_id, resource_id)`; se reconcilia en el
  lugar (`_sync_secondary_rows`), tocando solo lo que cambió.

## ADR-010 — `start()` como verbo público

- Estado: aceptada
- Fecha: 2026-08-04
- Contexto: la transición `confirmed` → `in_progress` existe en
  `_ALLOWED_TRANSITIONS` desde el diseño original de la máquina de
  estados, pero nunca tuvo método público — exactamente el mismo hueco de
  superficie que tenía `complete()` antes de ADR-006. MedLibra lo
  necesita para "iniciar atención".
- Decisión: `InMemoryScheduler.start(appointment_id)` sobre el mismo
  `_transition()` que los demás verbos. Sin `reason` (no es una
  cancelación ni una reprogramación) y sin migración (`status` ya acepta
  el valor).
- Consecuencias: 3 tests nuevos, incluido el que fija que **no** se puede
  arrancar un turno todavía sin confirmar. Cambio 100% aditivo.

## ADR-011 — La auditoría es un registro de transiciones, y de ahí salen las marcas de tiempo

- Estado: aceptada
- Fecha: 2026-08-04
- Contexto: el diseño de agendas pide auditoría (usuario, fecha, acción,
  estado anterior, estado nuevo, motivo) y además tiempos reales de
  atención — hora de inicio, hora de fin, duración real. La salida obvia
  era sumar columnas `started_at`/`ended_at` al turno.
- Decisión: **no** hay columnas de tiempo en el turno. Hay un registro
  append-only de transiciones (`AppointmentTransition`,
  `TransitionLogRepository`), y las marcas de tiempo se **leen** de ahí
  con `first_time_at(transitions, status)`. Un estado y el instante en
  que se alcanzó son el mismo hecho: guardarlos en dos lugares es
  garantizar que alguna vez se contradigan. La creación del turno se
  registra también, con `from_status` vacío — si no, lo primero que le
  pasó a la reserva sería lo único ausente de su historia.
  - `actor` es texto libre: el motor **no tiene noción de identidad** y no
    valida contra ninguna tabla de usuarios. Cada consumidor nombra sus
    usuarios como quiera.
  - Una **reprogramación también se audita**, con `from_status` igual al
    estado que conservó. Mover un turno merece quedar registrado aunque
    no sea un cambio de estado; dejarlo afuera vuelve incontestable
    "quién lo movió y cuándo".
  - El scheduler recibe un `clock` inyectable, sin el cual la historia no
    sería verificable en un test.
- Consecuencias: tabla `appointment_transitions`, migración `0009`,
  `InMemoryTransitionLog` y `SqlAlchemyTransitionLog`. El log **no tiene
  update ni delete**: una historia editable no responde nada. El
  scheduler siempre escribe —si no le pasan un adaptador usa el de
  memoria—, así que `history()` funciona sin configurar nada.

## ADR-012 — Vigencia en la disponibilidad e intervalo entre turnos

- Estado: aceptada
- Fecha: 2026-08-04
- Contexto: `Availability` era una ventana semanal plana, sin noción de
  desde cuándo y hasta cuándo rige. Cambiar el horario de un profesional
  obligaba a borrar la ventana vieja, con lo cual la agenda perdía la
  capacidad de explicar por qué un turno del mes pasado era válido. Y no
  había forma de pedir aire entre pacientes.
- Decisión: `Availability.valid_from`/`valid_to`, ambos opcionales e
  independientes, inclusivos, chequeados en `contains()` vía
  `applies_on()`. Sin ninguno de los dos la ventana rige siempre — que es
  de lo que dependen todas las ventanas creadas antes de que esto
  existiera. Y `AgendaPolicy(resource_id, slot_interval,
  max_overbookings_per_day)` para las reglas de agenda que no son
  horario: el intervalo ensancha el candidato de los dos lados en
  `find_conflicts(gap=...)`.
- Consecuencias: columnas `valid_from`/`valid_to` en `availability`, tabla
  `agenda_policies`, migración `0009`. `policy_for()` devuelve un default
  permisivo para todo recurso sin política, así que un consumidor que
  nunca configure nada se comporta igual que antes.

## ADR-013 — El sobreturno es overbooking autorizado, y vive en el motor

- Estado: aceptada
- Fecha: 2026-08-04
- Contexto: el motor rechaza todo solapamiento con `AppointmentConflict`,
  así que hoy un sobreturno es **imposible**, no incompleto. La tentación
  era resolverlo en el vertical, insertando el turno por afuera del
  scheduler.
- Decisión: el motor es dueño de la regla de solapamiento, así que tiene
  que ser dueño de su **excepción sancionada**:
  `create(appointment, allow_overbooking=True)`, y lo mismo en
  `reschedule()`. Si quedara en el vertical, MedLibra tendría que
  **esquivar el motor** para crear un sobreturno — justo el agujero en la
  validación que este diseño quiere evitar.
  - `allow_overbooking` relaja **solo** la regla de conflicto. Nunca
    horarios, feriados ni bloqueos: un sobreturno se mete apretado en un
    día de trabajo, no en un día franco.
  - El turno guardado queda con `overbooked=True` **solo si realmente se
    superpuso con algo**. Pedir permiso para sobreturnear y no
    necesitarlo es una reserva común; marcarla igual inflaría el mismo
    conteo que el tope quiere controlar.
  - El tope diario sale de `AgendaPolicy.max_overbookings_per_day`, y su
    default es **0** — una agenda que nunca dijo aceptar sobreturnos no
    debería empezar a aceptarlos en silencio. Por eso pedir
    `allow_overbooking=True` sin política configurada levanta
    `OverbookingLimitReached`, que es distinto de `AppointmentConflict`:
    uno dice "está ocupado y no pediste sobreturnear", el otro "pediste, y
    la agenda ya tuvo suficiente por hoy".
  - Quién lo autorizó y por qué es **del vertical**: el motor guarda que
    fue deliberado, no la justificación.
- Consecuencias: columna `appointments.overbooked`, migración `0009`, 10
  tests nuevos incluyendo que un sobreturno cancelado libera lugar bajo el
  tope y que el tope se cuenta por día.
