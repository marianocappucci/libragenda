FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0.dev0

WORKDIR /app
COPY pyproject.toml README.md uv.lock .python-version ./
COPY libragenda ./libragenda
COPY tests ./tests
COPY alembic.ini ./
COPY migrations ./migrations

# F1 (2026-09-05): el entorno sale de uv.lock, no de la resolucion del dia.
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_NO_CACHE=1 PATH="/opt/venv/bin:$PATH"
RUN uv sync --frozen --extra dev

CMD ["pytest", "-q"]
