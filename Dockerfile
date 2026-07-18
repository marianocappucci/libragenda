FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY libragenda ./libragenda
COPY tests ./tests
COPY alembic.ini ./
COPY migrations ./migrations

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[dev]"

CMD ["pytest", "-q"]
