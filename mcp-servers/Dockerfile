FROM python:3.12-slim

ARG SERVICE=ad
ENV SERVICE=${SERVICE} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8080 \
    MCP_STATELESS=true \
    MCP_JSON_RESPONSE=true

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin app

COPY mcp_common ./mcp_common
COPY ad ./ad
COPY exchange ./exchange
COPY onec ./onec

USER app
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"

CMD ["sh", "-c", "exec python -m \"$SERVICE\""]
