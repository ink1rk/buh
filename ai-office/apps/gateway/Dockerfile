FROM python:3.12.7-slim
WORKDIR /app
RUN useradd --uid 10001 --create-home app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY packages /app/packages
COPY apps /app/apps
USER 10001
ENV PYTHONPATH=/app/packages/contracts:/app/packages/security:/app/apps/gateway
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "gateway.app:app", "--host", "127.0.0.1", "--port", "8080"]
