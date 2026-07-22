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
