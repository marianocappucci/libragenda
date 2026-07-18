# Roadmap de LibraGenda

## Fase 0 — baseline (completa)

Scaffold, empaquetado, dominio inicial, reglas, casos de uso, repositorios,
PostgreSQL, Alembic, Docker y tag `v0.1.0`.

## Fase 1 — endurecimiento del motor (completa)

- Repositorios CRUD completos para disponibilidad, bloqueos y excepciones.
- Tests de migración contra PostgreSQL.
- Reglas de timezone por sucursal, feriados y consistencia recurso-sucursal.
- CI para push/tag.

## Fase 2 — capacidades de agenda (siguiente)

- Recurrencias.
- Recordatorios mediante puerto de notificaciones.
- Señás mediante puerto de pagos.

## Fase 3 — consumo vertical

- Gestiolibra usa LibraGenda en un entorno dev real.
- MedLibra consume el mismo contrato sin contaminar el motor con clínica.
- Tag estable posterior a la primera integración real.
