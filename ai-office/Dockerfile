ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY aioffice /app/aioffice
COPY migrations /app/migrations
COPY tests /app/tests
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "aioffice.main"]

