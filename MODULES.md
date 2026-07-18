# Módulos de LibraGenda

## Implementados

- `domain`: recursos, servicios, disponibilidad, turnos, estados, sucursales y clientes.
- `scheduling`: solapamientos, bloqueos y excepciones.
- `application`: crear, confirmar, cancelar y reprogramar.
- `repositories`: interfaz de turnos + memoria.
- `sqlalchemy_repository` / `catalog_repository`: PostgreSQL/SQLAlchemy.
- `database`: configuración de engine/session factory.

## Próximos

- `notifications`: recordatorios y confirmaciones; solo puerto de envío al inicio.
- `payments`: señas/anticipos como puerto, sin lógica de proveedor.
- `recurrences`: generación de ocurrencias, sin mezclarla con `Appointment`.

## Fuera del motor

Autenticación de producto, roles, facturación, caja, clínica, recetas, cocina,
plantillas HTML y routers HTTP pertenecen a los consumidores.
