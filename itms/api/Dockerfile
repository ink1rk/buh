# Контекст сборки — каталог /itms: в образ попадают и API, и фоновый обработчик.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY api/pyproject.toml /app/pyproject.toml
COPY api/itms /app/itms
RUN pip install --upgrade pip && pip install .

COPY api/alembic.ini /app/alembic.ini
COPY api/alembic /app/alembic
COPY worker /app/worker

RUN useradd --create-home --uid 10001 itms && chown -R itms:itms /app
USER itms

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "itms.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
