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

# Образ общий у API и обработчика. У обработчика нет порта 8000:
# для него проверка сразу успешна, для API — только ответ /health по IPv4.
HEALTHCHECK --interval=5s --timeout=5s --start-period=90s --retries=20 \
    CMD python -c "import pathlib,urllib.request; cmd=pathlib.Path('/proc/1/cmdline').read_bytes(); raise SystemExit(0 if b'arq' in cmd else urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3) and 0)"

CMD ["uvicorn", "itms.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
