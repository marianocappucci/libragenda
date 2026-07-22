# Tasks — LibraGenda

Trabajo concreto vigente. Las decisiones estratégicas permanecen en `ROADMAP.md`; este archivo no es un historial.

## En curso

Ninguna en curso registrada. Fase 3 (consumo vertical) quedó completa con el
tag `v0.4.2` — ver `ROADMAP.md`. Falta definir el foco de la siguiente fase
(sin Fase 4 planificada todavía).

## Próximas

- [ ] Definir alcance de Fase 4 (o si el siguiente trabajo pasa a los
      verticales — Gestiolibra/MedLibra — en vez del motor).
- [ ] Aplicar `scripts/run_migrations.sh` al pipeline de deploy real de
      Gestiolibra y MedLibra cuando cada uno tenga uno (hoy ninguno tiene
      CI/CD más allá de tests).

Resuelto (no era pendiente real, TASKS.md no lo reflejaba): la API HTTP
propia ya se decidió en ADR-002 (`DECISIONS.md`) — no se crea por ahora,
revisar solo si aparece un consumidor que la necesite.

Resuelto (2026-07-22): SQLite pasa a ser el destino de producción por
defecto de toda la familia Libra (`PRAGMA foreign_keys=ON` automático,
migraciones `0002`/`0003`/`0005` corregidas para no depender de `ALTER`
de constraints). Postgres sigue soportado. Ver `DECISIONS.md` ADR-005.

## Bloqueadas

Ninguna bloqueada registrada.
