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

## ADR-014 — Las migraciones viajan en el paquete, y el deploy de un consumidor no puede clonar

- Estado: aceptada. **Reemplaza la decisión del 2026-07-18** que las dejaba
  fuera del wheel (documentada en `CONVENTIONS.md`).
- Fecha: 2026-08-24
- Contexto: aquella decisión decía *"el deploy pipeline de cada consumidor
  clona el repo, no se agrega `migrations/` al wheel"*, para no tener dos
  fuentes de verdad del mismo artefacto. El argumento era razonable. **El
  supuesto era falso:** el deploy de un consumidor no es un pipeline con git —
  es un contenedor, sin repo que clonar, sin git instalado y sin red saliente
  garantizada. `scripts/run_migrations.sh` sólo podía correr donde ya había un
  checkout, o sea en el CI.
- **Lo que costó, medido el 2026-08-24 en el VPS:** ni Gestiolibra ni MedLibra
  tenían las migraciones aplicadas en **ninguna** instancia — ni siquiera la
  tabla `alembic_version`. Su esquema lo creaba `Base.metadata.create_all()` al
  arrancar. El CI de los dos sí las corría, clonando, así que su verde no decía
  nada sobre lo desplegado. Es el mismo patrón que la familia ya conocía como
  "el mecanismo que nadie invoca", con el agravante de que acá **no se podía**
  invocar desde donde hacía falta.
- Decisión: `migrations/` pasa a `libragenda/migrations/` —adentro del
  paquete, que es lo que la mete en `packages = ["libragenda"]`— y se agrega
  `libragenda/migrar.py` con un comando de consola, `libragenda-migrar`.
- **`script_location` se resuelve desde `__file__`, no desde el cwd.** Es la
  diferencia entre andar en el repo y andar en `site-packages`: un
  `alembic.ini` con ruta relativa sólo funciona parado en la raíz del repo, que
  es justo donde el contenedor no está.
- `scripts/run_migrations.sh` **se conserva** para el caso que lo justifica:
  aplicar un tag distinto del instalado sin tocar el entorno. Deja de ser el
  camino normal.
- **Dos defectos aparecieron construyendo esto, y los dos los encontró correr
  el end-to-end contra una base real — no los tests unitarios:**
  1. `postgresql://` a secas resuelve a **psycopg2**, que este paquete no
     declara: el consumidor recibía `ModuleNotFoundError` y el mensaje mandaba
     a instalar el driver equivocado. Se normaliza a `postgresql+psycopg://`.
  2. `env.py` prefería `DATABASE_URL` del entorno por sobre el `Config`, así
     que el argumento explícito de `upgrade(url)` **se ignoraba en silencio**:
     con la variable puesta migraba la base del entorno y devolvía éxito. Se
     agregó la opción `libragenda.url`, que gana sobre las dos.

  > 🔑 Los tests unitarios pasaban **con los dos defectos puestos**, porque
  > afirmaban sobre el valor que el módulo *setea* y no sobre el que alembic
  > *usa*. El test que los destapó es el que migra una base de verdad.
- Consecuencias: `[project.scripts]` nuevo, `build` sumado a las dependencias
  de dev —sin él, el test que verifica que las migraciones viajan en el wheel
  se **saltea**, y un skip se lee igual que un verde— y 13 tests nuevos,
  incluido uno que abre el `.whl` construido y mira adentro.

## ADR-015 — El esquema se crea de a un proceso por vez (`crear_esquema`)

- Estado: aceptada.
- Fecha: 2026-10-16
- Contexto: con `uvicorn --workers N` (ADR-044 de libracore; hoy N = 1 en toda la familia) cada worker corre el arranque del
  producto. MedLibra (`app/main.py`, `create_app`) y Gestiolibra crean sus tablas ahí con
  `Base.metadata.create_all(get_engine())`, sobre el `Base` de este paquete, al que suman las suyas. `create_all` **mira** qué
  tablas faltan y después las **crea**; en PostgreSQL esas dos cosas no son atómicas, así que dos procesos que arrancan
  juntos sobre una base sin las tablas contestan los dos «faltan» y el segundo `CREATE TABLE` choca en el catálogo
  (`relation … already exists` / `duplicate key … pg_type_typname_nsp_index`). Es el mismo defecto que ADR-053 de libracore
  (`init_core_schema`) y ADR-062 de libracommerce (`init_schema`) cerraron en sus motores. En una instancia migrada con
  `libragenda-migrar` las tablas ya están y `create_all` no hace nada: el choque sólo aparece con una tabla que la cadena
  no trae (o un alta de cliente que no migró primero), que es cuando nadie lo mira. Pasaba también en SQLite: dos
  procesos sobre el mismo archivo.
- Decisión: **`libragenda.crear_esquema(engine, metadata=None)`**, que corre `metadata.create_all` en **una transacción** que
  empieza tomando un candado **bloqueante**: el segundo proceso espera al primero y, cuando entra, ya encuentra las tablas.
  - PostgreSQL: `pg_try_advisory_xact_lock` reintentado cada 0,1 s en la conexión del DDL (dura hasta su `commit`; el DDL
    de PostgreSQL es transaccional, así que un arranque que falla no deja tablas a medias).
  - SQLite (archivo): `BEGIN IMMEDIATE`, el candado de escritura de la base, con el mismo reintento. En memoria no hace nada.
  - Pasados `espera` segundos (120) levanta `TimeoutError`: un arranque que se queda esperando en silencio es peor que
    uno que falla diciendo por qué.
  - La clave del candado asesor se deriva del nombre con SHA-256 (56 bits), igual que en los otros motores.
- **Por qué acá y no con `libracore.candados`:** LibraGenda no depende de libracore (`dependencies` = SQLAlchemy, alembic,
  psycopg) y no debe pasar a depender sólo por esto. El mecanismo es el mismo; la API está copiada en espíritu, no
  importada. Si algún día la familia lo sube a un paquete común, esto se reemplaza por esa llamada.
- Consecuencias:
  - `SqlAlchemyAppointmentRepository.from_url` y `SqlAlchemyTransitionLog.from_url` usan `crear_esquema`.
  - 🔴 **El cambio que falta lo hace el consumidor:** MedLibra y Gestiolibra tienen que reemplazar
    `Base.metadata.create_all(get_engine())` por `crear_esquema(get_engine())` al subir el pin a v0.12.0. Subir el pin sin
    tocar esa línea no cambia nada.
  - Es un candado **por base**: no protege los `create_all` de otros `MetaData` (el `AuditoriaBase` de MedLibra y Gestiolibra
    ya va dentro de `una_vez_al_arrancar`); quien los tenga puede pasar su `metadata` a `crear_esquema`.
  - Cubierto por `tests/test_esquema_concurrente.py`: dos creaciones simultáneas contra PostgreSQL y SQLite, con la ventana
    de la carrera ensanchada y **con su contraprueba** (el mismo arnés con `create_all` pelado SÍ choca).

## ADR-016 — El recurso secundario se traba y se valida con el primario, y el choque dice cuál fue

- Estado: aceptada.
- Fecha: 2026-10-17
- Contexto: MedLibra dejaba que dos profesionales se quedaran el mismo consultorio a la misma hora. Su ADR-030 modelaba la
  sala como una entidad del vertical y la chequeaba en `AppointmentService` **antes** de llamar a `reserve()`: leía los
  turnos, veía la sala libre y recién después el motor abría su transacción. Entre las dos cosas cabía el pedido del otro
  profesional —cada uno traba su propia fila de recurso, así que no se cruzaban—, y entraban los dos. El motivo declarado
  era que «el motor asocia un turno a un solo recurso»; ADR-009 ya había dejado de ser cierto eso. Se midió primero si el
  defecto era del motor: dos reservas simultáneas de profesionales distintos con la misma sala como secundario, contra
  PostgreSQL real (`tests/test_concurrencia_del_hueco.py`), **dan un solo turno en v0.12.0**, con su contraprueba (leer y
  validar afuera, escribir después, deja entrar los dos). `reserve()` ya tomaba `FOR UPDATE` sobre `occupied_resource_ids`
  —primario y secundarios— y `find_conflicts()` compara la intersección.
- Decisión: **no se agrega un mecanismo nuevo; se completa el que ADR-009 dejó.** La sala sigue siendo un `Resource` genérico
  y un recurso secundario del turno (el motor no aprende la palabra «consultorio»), y un turno con la sala ocupada falla
  igual que uno con el horario ocupado: `AppointmentConflict`. Tres cosas hacían falta para que un consumidor la use bien:
  - **`AppointmentConflict.resource_ids`**: cuáles de los recursos que el turno ocupa chocaron, en el orden de
    `occupied_resource_ids`. Sin esto el vertical no puede distinguir «el profesional está ocupado» de «la sala está
    ocupada», y la única forma de averiguarlo es volver a mirar los turnos afuera del candado, que es el defecto. La
    excepción conserva `args` (`str(exc)` sigue siendo el id) y el default es vacío.
  - **`reschedule(…, secondary_resource_ids=None)`**: mover un turno puede cambiarlo de sala (el consultorio del bloque que
    cubre el horario nuevo). Sin el parámetro el vertical tendría que guardar la sala nueva con `save()` después de mover,
    fuera de la transacción. `None` conserva los secundarios; `()` los libera.
  - **Orden de candados**: `reserve()` y `relocate()` piden las filas con `ORDER BY resources.id`. Con un solo recurso por
    turno no importaba; con dos, dos transacciones que comparten profesional y sala deben tomarlas en el mismo orden o
    pueden cruzarse. No hay un deadlock medido —el plan daba el mismo orden a las dos—, es la garantía en vez de la
    casualidad.
- Consecuencias:
  - Cambio 100% aditivo, sin migración y sin tocar el puerto `AppointmentRepository`: `relocate` ya validaba y escribía el
    turno completo, secundarios incluidos (`_sync_secondary_rows`).
  - 🔴 **Lo que el consumidor tiene que hacer** (MedLibra, su ADR-042): dar de alta cada sala como `Resource`, ponerla en
    `secondary_resource_ids` del turno, dejar de chequearla aparte y traducir `AppointmentConflict.resource_ids` a su
    mensaje. Los `TimeBlock` de la sala (mantenimiento) ya se chequean contra todos los recursos ocupados; el vertical tiene
    que cargárselos al `InMemoryScheduler` si quiere usarlos.
  - Un `Resource` de sala aparece en cualquier listado de recursos del vertical; filtrarlo es del vertical (el motor no tiene
    «tipo» de recurso y no lo gana por esto).
  - Un sobreturno (`allow_overbooking`) relaja el choque de **todos** los recursos, la sala incluida; un vertical que no
    quiera sobreturnos sobre una sala no debe pedirlos.

## ADR-017 — La tabla de versión de Alembic es propia (`alembic_version_libragenda`), con autorrenombre

- Estado: aceptada.
- Fecha: 2026-10-25
- Contexto: hasta la v0.13.0 la cadena de LibraGenda guardaba su revisión en `alembic_version`, que es el nombre por
  defecto de Alembic y **también** el de la cadena de LibraCore (`libracore-migrar`). No importaba mientras cada producto
  tenía dos bases (GestioLibra y MedLibra: el dominio con LibraGenda, el core con LibraCore). Con **una sola base por
  producto** (decisión del humano, 2026-10-22; ya hecha en LibraClub y LibraCargo) las dos cadenas migran en la misma
  base, y dos cadenas sobre una tabla de versión se pisan la revisión: la segunda en correr cree que la primera es suya y
  muere con *Can't locate revision*. Además `libracore-unir-bases` corta con una tabla de versión repetida de cadenas
  distintas (ADR-078 de LibraCore, punto 4). LibraCommerce, LibraClub, LibraCargo, LibraDesk, GestioLibra y MedLibra ya
  usan `alembic_version_<nombre>`; LibraGenda era la que faltaba.
- Decisión: la tabla de versión pasa a `alembic_version_libragenda` (`libragenda.migrar.TABLA_DE_VERSION`), la que lee
  `migrations/env.py`. Y **el renombre lo hace la propia migración**, no el operador:
  `adoptar_la_tabla_de_version_vieja` corre adentro de `begin_transaction()`, antes de las revisiones.
  - Renombra `alembic_version` a la propia **sólo si** la propia no existe, la vieja existe y **todas** sus revisiones son
    de esta cadena. Una `alembic_version` vacía, o con alguna revisión ajena (la de LibraCore en una base unida), no se
    toca: esa tabla es del motor.
  - También renombra la restricción `alembic_version_pkc` a `alembic_version_libragenda_pkc`. Un `RENAME` de tabla no
    renombra su clave primaria, y en PostgreSQL el índice de la clave es un objeto del schema: con el nombre repetido la
    cadena de LibraCore moriría al crear la suya (*relation "alembic_version_pkc" already exists*; medido acá con el test
    `test_convive_con_las_tablas_de_libracore_en_la_misma_base`, y en LibraCargo el 2026-10-05).
  - Va en la misma transacción que las migraciones: en PostgreSQL, si una revisión falla, el renombre se deshace.
- Consecuencias:
  - Un consumidor no hace nada: `libragenda-migrar upgrade` (o `alembic upgrade head`) adopta la tabla vieja sola. Una
    base nueva crea la propia directamente.
  - 🔴 Cualquier cosa que lea `alembic_version` esperando la revisión de LibraGenda tiene que leer la nueva. En los
    consumidores: los chequeos de «migraciones al día» y los scripts de deploy. `libraauth-migrar` y `libracore-migrar`
    no se ven afectados.
  - `libragenda-migrar stamp` sobre una base que nunca tuvo la cadena crea la tabla propia (no la vieja).
  - `libragenda-migrar current` también adopta: leer la revisión de una base de antes la renombra. Es lo que hace falta
    para que conteste bien.

## ADR-018 — `clients` pasa a `agenda_clients`, y ninguna tabla de LibraGenda puede llamarse como una del motor

- Estado: aceptada.
- Fecha: 2026-10-25
- Contexto: LibraCore declara su tabla `clients` (id entero, nueve claves foráneas que la apuntan, `libracore:libracore/db/
  schema.py`) y LibraGenda la suya (id `VARCHAR(100)`). Por eso GestioLibra y MedLibra tuvieron siempre dos bases
  (`docker/postgres-init/10-base-de-libracore.sql` lo dice). Con una sola base por producto no pueden convivir, y
  `libracore-unir-bases` corta con «La tabla clients existe en el core y en el dominio» (medido el 2026-10-25 sobre un
  dominio v0.13.0 y un core de `origin/develop`, junto con el choque de `alembic_version` del ADR-017: «2 impedimentos»).
  No se renombra la de LibraCore: la usan todos los productos.
- Decisión:
  - **Migración `0010_agenda_clients`: `ALTER TABLE clients RENAME TO agenda_clients`**, y nada más. No copia ni borra
    una fila. Las claves foráneas que apuntan a la tabla la siguen solas (PostgreSQL y SQLite >= 3.26): la de
    `appointments` y las de los productos (`client_billing` de GestioLibra; `patients` y `walkins` de MedLibra). La tabla
    no tiene secuencia (el id es texto). Se renombra además su clave primaria (`clients_pkey` → `agenda_clients_pkey`):
    no choca (PostgreSQL le pone `clients_pkey1` a la clave sin nombre de la `clients` del motor, medido), pero dejaría
    dos claves con el nombre cruzado. El downgrade es simétrico.
  - El modelo es `ClientRow.__tablename__ = "agenda_clients"` y `AppointmentRow.client_id` apunta a `agenda_clients.id`.
    El prefijo `agenda_` es la convención para cualquier tabla de LibraGenda que pueda chocar.
  - **Una guarda** (`tests/test_nombres_de_tablas.py`): ningún nombre de tabla de LibraGenda —modelos y cadena de
    migraciones— puede estar entre los de LibraCore y LibraAuth. LibraGenda no depende de LibraCore, así que el CI compara
    contra una copia de la lista; si `libracore` está instalado, otro test compara la copia contra su cadena real y se
    pone rojo cuando el motor suma una tabla.
  - Si la migración encuentra `agenda_clients` ya creada (la aplicación arrancó con `create_all` y el código nuevo antes
    de migrar) **aborta con un mensaje que lo dice** y no toca nada: no borra tablas a ciegas.
- Consecuencias:
  - 🔴 **Para los consumidores (GestioLibra y MedLibra, en sus propios PR):**
    1. subir el pin de libragenda a v0.14.0;
    2. cambiar todo `ForeignKey("clients.id")` por `ForeignKey("agenda_clients.id")` (`client_billing`, `patients`,
       `walkins`) y toda consulta SQL a mano o `Table("clients")` que apunte a la tabla de LibraGenda;
    3. correr `libragenda-migrar upgrade` **antes** de arrancar la aplicación nueva: un producto con el pin viejo y la
       base ya migrada no arranca (no existe `clients`), y uno con el pin nuevo y la base sin migrar crea una
       `agenda_clients` vacía con `create_all`;
    4. **en una base nueva, la cadena de LibraGenda tiene que correr antes que la de LibraCore**: la revisión `0002`
       crea `clients` y, si LibraCore ya creó la suya, falla. (No se cambió la `0002` para no romper las bases que ya la
       aplicaron.) El orden de los productos ya es ese: `libragenda-migrar`, `libraauth-migrar`, `libracore-migrar`.
  - `libragenda-migrar downgrade` más allá de la `0010` no se puede hacer en una base ya unida con LibraCore (`clients`
    es la del motor): aborta con el mensaje de revertir primero la unión.
  - **Fuera de alcance: LibraCommerce.** Su tabla `branches` se llama como la de LibraGenda. Ningún producto usa los dos
    motores en una misma base (los de agenda no usan LibraCommerce; LibraDesk lo usa y no usa las tablas de LibraGenda),
    y la guarda no lo cubre. Si algún día se juntan, hay que renombrar una de las dos.
  - Los nombres de las demás tablas de LibraGenda (`branches`, `resources`, `services`, `appointments`, `deposits`, …)
    no chocan con los de LibraCore ni con los de LibraAuth (verificado el 2026-10-25 contra `origin/develop`, v1.192.1).


## ADR-019 — Atender un turno en un nodo sin conexión: fila propia, `turno.atendido` y un aplicador idempotente

- Estado: aceptada.
- Fecha: 2026-10-25
- Contexto: GestioLibra y MedLibra van a tener versión de escritorio (un nodo de LibraEdge en la PC del local). Decisiones
  del humano (2026-10-21, 2026-10-22 y 2026-10-25): sin internet la agenda es **de sólo consulta**, pero **atender** un
  turno ya dado (en curso, completado, «no vino») y cobrarlo se puede; y si en la web lo cancelaron o lo movieron
  mientras tanto, **la atención y el cobro valen** y el turno queda **«a revisar»**. En el nodo, `appointments` es una fila
  del espejo y la guarda de LibraEdge (ADR-019 de ese repo, SQLSTATE `LE001`) no deja escribirla; escribir ahí tampoco
  sirve, porque el próximo cambio del central la pisaría. Como lo comparten los dos productos, va **en LibraGenda**, no
  en cada uno (el arreglo de fondo vive en el motor).
- Qué ya existía (se miró antes): el molde de LibraClub (`servicios/reservas_nodo.py`, su ADR-022): configuración global
  con el `nodo` y los ganchos que encolan en la transacción, un aplicador idempotente para el despachador del central, y
  `libraedge` importado sólo al usarse. Las reglas de estado de LibraGenda (`_ALLOWED_TRANSITIONS`) y el historial de
  transiciones (`appointment_transitions`), de donde salen las horas de «empezó» y «terminó» (`first_time_at`).
- Decisión:
  - **LibraGenda no depende de LibraEdge ni de LibraCore.** El producto pasa la función que encola
    (`AtencionesEnNodo.encolar(sesion, tipo, agregado, id_local, datos)`, corre en la transacción de la sesión) y el
    despachador al que se registra el aplicador (`registrar_en`). Así lo hace LibraClub. Es global y del proceso
    (`configurar`); fuera de un nodo `atender_en_nodo` se niega (`NoEsUnNodo`): en el central se atiende con el scheduler.
  - **La fila propia del nodo es `agenda_node_attendances`** (una por atención, con `orden` por turno; migración
    `0011_node_attendances`, aditiva y con downgrade). Sin clave foránea a `appointments`: el espejo reapunta y borra filas
    de esa tabla y no tiene que llevarse la atención puesta. `UNIQUE(appointment_id, orden)` cierra la carrera de dos
    pestañas. La tabla **no se espeja**. El nodo muestra la agenda con esa fila encima (`atenciones_del_nodo`,
    `estado_efectivo`) y valida con las reglas de siempre contra ese estado efectivo (`can_transition`, ahora público):
    en curso → completado vale, completado → «no vino» no. Desde un nodo un turno sólo pasa a `in_progress`,
    `completed` o `no_show`: no se cancela ni se confirma.
  - **La operación es `turno.atendido`**, `aggregate_type = "turno"`, `schema_version = 1`, `version = 1`. Lleva
    `atencion_id` (uuid4 del nodo: **la clave de idempotencia**), `turno_id`, `estado`, `at` (ISO con zona: la hora real,
    que es la que queda en el historial), `actor`, `visto` (cómo veía el nodo el turno: estado, inicio, duración y
    recurso) y **`extra`**, un diccionario libre para que el producto adjunte lo suyo —los pagos en GestioLibra y
    MedLibra—. LibraGenda lo guarda y lo devuelve, no lo mira. Las ids de turno son los del central: el nodo no da
    turnos, así que no hay ids provisorios acá.
  - **El aplicador del central (`aplicar_turno_atendido`) es idempotente por `atencion_id`**: la tabla
    `agenda_applied_attendances` guarda cada atención aplicada y su clave primaria lo hace un solo efecto, también con
    dos entregas a la vez (`INSERT … ON CONFLICT DO NOTHING`; el turno se traba con `FOR UPDATE` antes de mirarlo). Un
    `atencion_id` reusado con otro contenido es un error (`AtencionInvalida`, un `ValueError`: el receptor lo manda a
    revisión manual), no se pisa. Aplica la transición con `can_transition` y escribe el historial con la **hora del
    nodo**, no la de ahora. Trabaja en la sesión del llamador y no commitea.
  - **Si el turno cambió en la web, la atención igual queda** (decisión del humano). Va a la lista «a revisar»
    (`resultado = 'a_revisar'`, `turnos_a_revisar`, `marcar_revisada`) con un motivo:

    | El turno en el central | Efecto sobre el turno | Motivo |
    |---|---|---|
    | como lo vio el nodo; transición válida | cambia de estado | (ninguno, `aplicada`) |
    | se movió (inicio, duración o recurso) y la transición es válida | cambia de estado | `movido` |
    | cancelado | no se toca (terminal) | `cancelado` |
    | ya atendido (en curso, completado o «no vino») y la transición no es válida o es la misma | no se toca | `ya_atendido` |
    | en otro estado desde el que no se puede (p. ej. `pending`) | no se toca | `transicion_invalida` |
    | no existe | — | `turno_inexistente` |

    Elecciones, para que el humano las pueda corregir: (a) un turno **movido** se completa igual —la atención pasó, la
    caja sube con ese turno y dejarlo sin completar lo mostraría pendiente de algo que ya se cobró—; (b) uno **cancelado**
    no se resucita solo: se anota y alguien decide; (c) **«ya atendido» incluye el mismo estado** (completado en la web y
    en el nodo): puede haberse cobrado dos veces, y es justo lo que alguien tiene que mirar. Una atención en curso del
    nodo sobre un turno que la web ya empezó **no** es conflicto si la siguiente transición es válida.
  - **Lo cobrado se conserva siempre.** `extra` queda en el registro aunque el turno vaya a revisar, y el hook
    `al_aplicar(sesion, atencion)` corre —en la misma transacción y **sólo la primera vez**— también para las atenciones
    `a_revisar`. Ahí MedLibra manda la consulta y sus pagos a ContaLibra (el central lo hace, no la PC), y GestioLibra
    registra lo que le haga falta. Si el hook levanta, no queda nada y el receptor reintenta.
  - **La lista «a revisar» es una consulta de dominio, la pantalla es otro PR.** `agenda_applied_attendances` es una tabla
    del central que el producto puede espejar al nodo (sólo lectura), así que se ve en las dos puntas. `marcar_revisada`
    es del central; no cambia el turno (acomodarlo es del scheduler, a mano).
  - **Sin `SAVEPOINT` en los caminos de escritura.** Con `pysqlite` un `SAVEPOINT` abierto antes de la primera escritura
    de la transacción la confirma al soltarse, y la atención quedaría escrita aunque lo que el producto hace después en la
    misma transacción falle (medido con el test del hook que falla). Por eso se usa `INSERT … ON CONFLICT DO NOTHING`
    (PostgreSQL y SQLite); otro motor cae al camino con `SAVEPOINT`.
- Fuera de alcance (a propósito):
  - **La demanda espontánea (`walkins`) de MedLibra** vive en el producto (`app/services/walkins.py`, ADR-031 de MedLibra),
    no en LibraGenda. La costura es `encolar_en_nodo(sesion, tipo, agregado, id_local, datos)`: el producto encola su
    propia operación (`walkin.registrado`) por la misma configuración, y no hace nada fuera de un nodo. El «no vino» sí
    está cubierto acá (`no_show`).
  - **Dar, mover o cancelar turnos en el nodo** (agenda de sólo consulta). Si algún día se dieran, el molde es el
    `en_conflicto` de LibraClub, decidido en el central.
  - **El cobro, la factura y los movimientos de caja**: son del producto (`GANCHOS_DE_CAJA`, `cola_arca`), que los saca
    del `extra`.
  - **La transacción del receptor.** `registrar_en` abre por defecto una sesión propia de `libragenda.database` y la
    confirma sola: es seguro porque el aplicador es idempotente (si el receptor falla después, la entrega se repite y no
    hace nada). Un producto que quiera todo en la transacción del receptor pasa su propio `abrir_sesion(conexion)`. **No
    se probó contra el receptor real de LibraEdge** (LibraGenda no lo tiene como dependencia).
- Consecuencias:
  - 🔴 **Para GestioLibra y MedLibra (PR 9 y 10 del plan):** subir el pin a v0.15.0 y correr `libragenda-migrar upgrade`
    **antes** de arrancar (dos tablas nuevas); `configurar(AtencionesEnNodo(...))` al armar la app; en el aprovisionamiento
    del central, **no** espejar `agenda_node_attendances` y sí `agenda_applied_attendances` (sin claves foráneas, sin
    `AltaEnNodo`); registrar el aplicador con `registrar_en(despachador, abrir_sesion=..., al_aplicar=...)` en el
    despachador del central; y en el endpoint de «atender», llamar a `atender_en_nodo` en la misma transacción que el
    cobro, con los pagos en `extra`. Mostrar la agenda con `atenciones_del_nodo` encima del espejo.
  - Las dos tablas nuevas llevan el prefijo `agenda_` (ADR-018) y la guarda de nombres las cubre.
  - Tras `unir-bases`, las dos tablas viajan con la base (no chocan con ninguna del motor).
