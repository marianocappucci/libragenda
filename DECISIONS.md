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

- Estado: aceptada
- Fecha: 2026-07-18
- Contexto: LibraGenda, Gestiolibra y MedLibra conviven en PostgreSQL.
- Decisión: cada producto y entorno usa una base y usuario propios, sin schema compartido.
- Consecuencias: aislamiento de datos y menor riesgo de interferencia entre consumidores.
