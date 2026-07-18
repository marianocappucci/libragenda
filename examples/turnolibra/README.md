# TurnoLibra — ejemplo de integración

Este ejemplo representa la aplicación vertical: configura LibraGenda, monta
FastAPI y usa sus repositorios/casos de uso. LibraGenda sigue siendo un
paquete, no un servicio HTTP independiente.

```python
from examples.turnolibra.app import create_app
app = create_app(os.environ["LIBRAGENDA_DATABASE_URL"])
```

En producción, ejecutar Alembic antes de iniciar la aplicación. El
`create_all()` del ejemplo existe solo para que el smoke test sea autónomo.
