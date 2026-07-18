# LibraGenda

Motor genérico reutilizable de turnos y agenda para productos de la familia
Libra. Es un módulo independiente y peer de
[LibraCore](https://github.com/marianocappucci/libracore): ningún motor
depende del otro.

Los primeros consumidores previstos son TurnoLibra y MedLibra. El motor debe
mantenerse agnóstico del vertical: un recurso puede ser una persona, un
consultorio, una cabina, una máquina o cualquier otra cosa reservable.

## Estado

Primera API de dominio definida, sin persistencia ni framework. Incluye
`Resource`, `Service`, `Availability`, `Appointment` y `AppointmentStatus`.
La siguiente capa deberá resolver reglas de agenda (solapamientos, bloqueos y
excepciones) antes de incorporar persistencia o integración vertical.

## Desarrollo

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Versionado

Semver mediante tags de Git (`vX.Y.Z`), con versión derivada automáticamente
por `hatch-vcs`. Los consumidores deben pinear una versión exacta.
