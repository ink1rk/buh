"""Health endpoints and update intake. Polling and webhooks are not both enabled."""

from __future__ import annotations

import os

from fastapi import FastAPI

app = FastAPI(title="ai-office-gateway", version="0.1.0")
MODE = os.environ.get("GATEWAY_MODE", "polling")


@app.get("/health/live")
def live() -> dict:
    return {"status": "live"}


@app.get("/health/ready")
def ready() -> dict:
    if MODE not in {"polling", "webhook"}:
        return {"status": "not-ready", "mode": MODE}
    return {"status": "ready", "mode": MODE}


@app.get("/metrics")
def metrics() -> str:
    return "ai_office_gateway_up 1\n"
