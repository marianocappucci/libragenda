#!/usr/bin/env bash
# Aplica las migraciones de Alembic de LibraGenda contra la base de un
# consumidor (Gestiolibra, MedLibra, etc.), clonando el repo en el tag
# exacto pineado por ese consumidor.
#
# ⚠️ ESTE NO ES EL CAMINO NORMAL, desde la v0.10.0.
#
# Las migraciones AHORA viajan en el paquete (`libragenda/migrations/`), asi que
# lo habitual es correr, dentro del entorno del consumidor:
#
#     DATABASE_URL=... libragenda-migrar upgrade
#
# Eso usa lo que el consumidor YA tiene instalado, con lo cual no se puede
# desincronizar del pin. Este script queda para el caso que si lo justifica:
# aplicar las migraciones de un tag DISTINTO del instalado, sin tocar el
# entorno.
#
# Requiere git y red saliente -- que es exactamente lo que un contenedor no
# tiene, y el motivo por el que hubo que empaquetarlas. Ver DECISIONS.md,
# ADR-014.
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
