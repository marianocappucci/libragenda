#!/usr/bin/env bash
# Aplica las migraciones de Alembic de LibraGenda contra la base de un
# consumidor (Gestiolibra, MedLibra, etc.), clonando el repo en el tag
# exacto pineado por ese consumidor.
#
# Las migraciones no viajan en el wheel de pip (ver CONVENTIONS.md, seccion
# "Configuracion y deploy") -- este script es la forma reproducible de
# aplicarlas en cualquier pipeline de deploy, en lugar de sincronizar un
# checkout local a mano.
#
# Uso:
#   LIBRAGENDA_REF=v0.3.0 DATABASE_URL=postgresql://user:pass@host/db \
#     ./scripts/run_migrations.sh
#
# Variables de entorno:
#   LIBRAGENDA_REF   tag exacto de LibraGenda a aplicar (obligatorio, ej. v0.3.0)
#   DATABASE_URL     URL de conexion de la base del consumidor (obligatorio)
#   LIBRAGENDA_REPO  URL del repo a clonar (default: origin de GitHub)

set -euo pipefail

: "${LIBRAGENDA_REF:?LIBRAGENDA_REF es obligatorio (ej. v0.3.0)}"
: "${DATABASE_URL:?DATABASE_URL es obligatorio}"
LIBRAGENDA_REPO="${LIBRAGENDA_REPO:-https://github.com/marianocappucci/libragenda.git}"

workdir="$(mktemp -d)"
cleanup() { rm -rf "$workdir"; }
trap cleanup EXIT

echo "Clonando LibraGenda @ ${LIBRAGENDA_REF}..." >&2
git clone --quiet --depth 1 --branch "$LIBRAGENDA_REF" "$LIBRAGENDA_REPO" "$workdir"

cd "$workdir"
python3 -m venv .venv
.venv/bin/pip install --no-cache-dir --quiet --upgrade pip
.venv/bin/pip install --no-cache-dir --quiet "alembic>=1.13,<2" "SQLAlchemy>=2.0,<3" "psycopg[binary]>=3.1,<4"
.venv/bin/pip install --no-cache-dir --quiet -e .

DATABASE_URL="$DATABASE_URL" .venv/bin/alembic -c alembic.ini upgrade head

echo "Migraciones de LibraGenda ${LIBRAGENDA_REF} aplicadas contra la base indicada." >&2
