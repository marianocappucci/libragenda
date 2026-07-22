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
