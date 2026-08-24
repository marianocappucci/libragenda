"""Que las migraciones VIAJEN en el wheel y se puedan correr desde el paquete.

🔴 **El motivo es un defecto medido, no una mejora teórica.** Hasta la
`v0.10.0` `migrations/` vivía en la raíz del repo, fuera de
`packages = ["libragenda"]`, así que no entraba al wheel. Un consumidor que
instala LibraGenda con pip adentro de su imagen no tenía con qué aplicarlas:
`scripts/run_migrations.sh` **clona el repo**, y en un contenedor no hay repo.

Resultado medido el 2026-08-24 en el VPS: ni Gestiolibra ni MedLibra tenían
`alembic_version` en ninguna instancia. Su esquema lo creaba
`Base.metadata.create_all()` al arrancar, y el CI —que sí las corría, clonando—
daba verde sin decir nada sobre las instancias.

🔑 **El test que importa es el del wheel construido.** Afirmar sobre
`pyproject.toml` mediría la intención; afirmar sobre el árbol del repo mediría
el checkout. Lo único que contesta la pregunta real —«¿el consumidor las
recibe?»— es abrir el `.whl` y mirar adentro.
"""

from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


# ── El paquete instalado sabe dónde están ────────────────────────────────


def test_el_directorio_de_migraciones_esta_dentro_del_paquete():
    from libragenda import migrar

    assert migrar.DIRECTORIO.is_dir(), migrar.DIRECTORIO
    # Dentro del paquete y no al lado: es lo que hace que entre al wheel.
    assert migrar.DIRECTORIO.parent.name == "libragenda"


def test_estan_las_revisiones_y_el_env():
    from libragenda import migrar

    revisiones = sorted(p.name for p in (migrar.DIRECTORIO / "versions").glob("*.py"))
    # No se fija el número exacto —crece con cada migración nueva— pero sí que
    # la primera esté: si `versions/` viajara vacío, el `upgrade` no haría nada
    # y **no fallaría**, que es el peor resultado posible.
    assert "0001_initial_schema.py" in revisiones
    assert len(revisiones) >= 8
    assert (migrar.DIRECTORIO / "env.py").is_file()


def test_la_configuracion_apunta_al_paquete_y_no_al_cwd(monkeypatch, tmp_path):
    """🔑 Se resuelve desde `__file__`, que es la diferencia entre andar en el
    repo y andar en site-packages."""
    from libragenda import migrar

    monkeypatch.chdir(tmp_path)  # lejos de la raíz del repo
    cfg = migrar.configuracion("postgresql://u:p@h/db")
    ubicacion = Path(cfg.get_main_option("script_location"))

    assert ubicacion.is_absolute()
    assert (ubicacion / "versions" / "0001_initial_schema.py").is_file()


def test_sin_url_falla_diciendo_que_falta(monkeypatch):
    """Un `upgrade` sin base no puede salir en silencio ni con un traceback de
    SQLAlchemy que no nombre la causa."""
    from libragenda import migrar

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(migrar.SinURL, match="DATABASE_URL"):
        migrar.configuracion()


def test_toma_la_url_del_entorno(monkeypatch):
    """Control positivo del test de arriba: con la variable puesta, resuelve.

    Sin esto, un `SinURL` incondicional pasaría aquel test."""
    from libragenda import migrar

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    assert migrar.configuracion().get_main_option("sqlalchemy.url") == (
        "postgresql+psycopg://u:p@h/db"
    )


# ── El driver ────────────────────────────────────────────────────────────


def test_el_prefijo_pelado_se_manda_a_psycopg3(monkeypatch):
    """🔴 SQLAlchemy resuelve `postgresql://` a **psycopg2**, y este paquete
    declara psycopg **3** y nada más.

    Medido antes de arreglarlo: `libragenda-migrar` contra un
    `postgresql://…` moría con `ModuleNotFoundError: No module named
    'psycopg2'` — un error que manda a instalar el driver equivocado en medio
    de un deploy.
    """
    from libragenda import migrar

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    assert migrar.configuracion().get_main_option("sqlalchemy.url") == (
        "postgresql+psycopg://u:p@h/db"
    )


def test_env_py_tambien_normaliza(monkeypatch):
    """🔴 **El test que faltaba, y por eso el arreglo no funcionaba.**

    `migrations/env.py::get_url()` lee `DATABASE_URL` del entorno y **no mira**
    la opción que `configuracion()` pone en el `Config`. O sea que normalizar
    sólo del lado de `migrar.py` dejaba el camino real —el de cualquier
    contenedor, que siempre tiene la variable puesta— sin arreglar.

    Los dos tests de arriba pasaban igual, porque afirmaban sobre el valor que
    este módulo **setea**, no sobre el que alembic **usa**. Lo destapó correr el
    end-to-end contra una base de verdad.
    """
    import importlib.util

    from libragenda import migrar

    ruta = migrar.DIRECTORIO / "env.py"
    fuente = ruta.read_text(encoding="utf-8")
    # Se lee el fuente en vez de importarlo: `env.py` ejecuta las migraciones al
    # importarse (las dos últimas líneas), así que importarlo acá las correría.
    assert "normalizar_url" in fuente, (
        "env.py no normaliza el driver: `postgresql://` va a resolver a psycopg2"
    )
    assert importlib.util.find_spec("libragenda.migrar") is not None


def test_un_driver_explicito_no_se_pisa(monkeypatch):
    """Control del test de arriba: sólo se toca el prefijo pelado. Quien pida
    psycopg2 a propósito se queda con psycopg2 — si no, la normalización sería
    una decisión escondida en vez de un default."""
    from libragenda import migrar

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@h/db")
    assert migrar.configuracion().get_main_option("sqlalchemy.url") == (
        "postgresql+psycopg2://u:p@h/db"
    )


# ── La CLI ───────────────────────────────────────────────────────────────


def test_un_comando_que_no_existe_sale_distinto_de_cero(capsys):
    """Un typo en un pipeline de deploy no puede leerse como exito."""
    from libragenda import migrar

    assert migrar.main(["invento"]) == 2


def test_la_ayuda_sale_con_cero(capsys):
    from libragenda import migrar

    assert migrar.main(["--help"]) == 0
    assert "migraciones en:" in capsys.readouterr().out


def test_sin_url_la_cli_sale_1(monkeypatch, capsys):
    from libragenda import migrar

    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert migrar.main(["upgrade"]) == 1
    assert "DATABASE_URL" in capsys.readouterr().err


# ── El que decide de verdad: migrar una base real ────────────────────────


def test_migra_una_base_real_con_la_url_pelada():
    """🔴 **La regresión que los unitarios no veían.**

    Corre el camino completo —`migrar.upgrade()` → `env.py` → las revisiones—
    contra PostgreSQL de verdad, y **con `postgresql://` sin sufijo de driver**,
    que es la forma que moría con `ModuleNotFoundError: No module named
    'psycopg2'`.

    Los tests de `normalizar_url` de arriba pasaban con el defecto puesto,
    porque afirmaban sobre el valor que `configuracion()` setea y no sobre el
    que alembic termina usando: `env.py` lee `DATABASE_URL` del entorno y no
    mira el `Config`.

    Sin `DATABASE_URL` se saltea, como el resto de los tests que piden base.
    """
    url_ci = os.environ.get("DATABASE_URL")
    if not url_ci:
        pytest.skip("sin DATABASE_URL: no hay PostgreSQL contra el que migrar")

    import psycopg
    from sqlalchemy.engine import make_url

    from libragenda import migrar

    base = f"libragenda_e2e_{os.getpid()}"
    servidor = make_url(url_ci).set(drivername="postgresql", database="postgres")
    admin = str(servidor).replace("***", servidor.password or "")

    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{base}"')
        c.execute(f'CREATE DATABASE "{base}"')
    try:
        # 🔑 A propósito con el prefijo PELADO, que es el caso que fallaba.
        destino = str(make_url(url_ci).set(drivername="postgresql", database=base))
        destino = destino.replace("***", make_url(url_ci).password or "")

        migrar.upgrade(destino)

        with psycopg.connect(destino, autocommit=True) as c:
            revision = c.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            tablas = c.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ).fetchone()[0]
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{base}" WITH (FORCE)')

    assert revision, "no quedo revision estampada"
    # Más de una tabla además de `alembic_version`: si las revisiones viajaran
    # vacías, el upgrade saldría en verde sin crear nada.
    assert tablas > 5, f"la base quedo con {tablas} tablas"


# ── El que decide el empaquetado: el wheel construido ────────────────────


@pytest.mark.slow
def test_las_migraciones_viajan_en_el_wheel(tmp_path):
    """🔴 **La prueba real.** Construye el wheel y mira adentro.

    Es lenta (construye el paquete) y vale cada segundo: es la única afirmación
    que responde «¿el consumidor las recibe?». Los tests de arriba miden el
    checkout, que siempre las tiene.
    """
    r = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        cwd=RAIZ, capture_output=True, text=True,
    )
    if r.returncode != 0:
        pytest.skip(f"no se pudo construir el wheel: {r.stderr[-300:]}")

    wheels = list(tmp_path.glob("*.whl"))
    assert wheels, "el build no dejo ningun .whl"

    with zipfile.ZipFile(wheels[0]) as z:
        nombres = z.namelist()

    versiones = [n for n in nombres if "/migrations/versions/" in n and n.endswith(".py")]
    assert any(n.endswith("0001_initial_schema.py") for n in versiones), (
        f"la primera revision no viajo en el wheel; migraciones halladas: {versiones}"
    )
    assert len(versiones) >= 8, f"viajaron solo {len(versiones)} revisiones"
    assert any(n.endswith("libragenda/migrations/env.py") for n in nombres), (
        "falta env.py: sin el, alembic no puede correr"
    )

    # 🔑 Control negativo: los `__pycache__` NO tienen que viajar. Si esto
    # fallara, el `exclude` del pyproject no esta haciendo nada — y entonces
    # tampoco se puede confiar en que el resto de la config del wheel lo haga.
    assert not [n for n in nombres if "__pycache__" in n], "viajaron .pyc"
