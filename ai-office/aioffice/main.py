import hashlib
import json
import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from .config import Settings
from .db import audit, engine_for, migrate
from .policy import payload_hash
from .runtime import Runtime
from .llm import LLMRuntime
from .service import enqueue

settings = None
engine = None
runtime = None


@asynccontextmanager
async def lifespan(app):
    global settings, engine, runtime
    settings = Settings.from_env()
    engine = engine_for(settings.database_url)
    migrate(engine)
    with engine.begin() as conn:
        for owner in settings.owners:
            conn.execute(text('INSERT INTO users(id,timezone) VALUES (:o,:z) ON CONFLICT(id) DO UPDATE SET timezone=CASE WHEN EXCLUDED.timezone<>\'\' THEN EXCLUDED.timezone ELSE users.timezone END'), {'o': owner, 'z': settings.timezone})
    stop = threading.Event()
    runtime = Runtime(engine, settings, stop)
    thread = threading.Thread(target=runtime.run, name='telegram-poller', daemon=True)
    llm_thread = threading.Thread(target=LLMRuntime(engine, settings, stop).run, name='assistant-worker', daemon=True)
    thread.start()
    llm_thread.start()
    yield
    stop.set()
    thread.join(timeout=40)
    llm_thread.join(timeout=85)
    engine.dispose()


app = FastAPI(title='AI Office', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get('/health/live')
def live():
    return {'status': 'alive'}


@app.get('/health/ready')
def ready():
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception:
        raise HTTPException(503, 'Database unavailable') from None
    if settings.polling and (runtime.failed or not runtime.leader or time.monotonic() - runtime.last_poll > 90):
        raise HTTPException(503, 'Telegram poller unavailable')
    return {'status': 'ready', 'llm_enabled': settings.llm_enabled}


@app.get('/metrics', response_class=PlainTextResponse)
def metrics():
    with engine.connect() as conn:
        uncertain = conn.execute(text("SELECT count(*) FROM outbox_events WHERE state='uncertain'")).scalar_one()
    return f'ai_office_telegram_leader {int(runtime.leader)}\nai_office_delivery_uncertain {uncertain}\nai_office_llm_enabled {int(settings.llm_enabled)}\n'


class ArtifactBody(BaseModel):
    content: str = Field(min_length=1, max_length=16000)


@app.post('/internal/tasks/{task_id}/artifact')
def save_artifact(task_id: uuid.UUID, body: ArtifactBody, authorization: str = Header(default='')):
    token = authorization.removeprefix('Bearer ') if authorization.startswith('Bearer ') else ''
    digest = hashlib.sha256(token.encode()).hexdigest()
    content = body.model_dump()
    checksum = payload_hash(content)
    with engine.begin() as conn:
        execution = conn.execute(text('SELECT * FROM execution_tokens WHERE token_hash=:h AND task_id=:t FOR UPDATE'), {'h': digest, 't': task_id}).mappings().first()
        if not token or not execution or execution['expires_at'] <= datetime.now(UTC):
            raise HTTPException(403, 'Invalid execution capability')
        existing = conn.execute(text('SELECT content_hash FROM artifacts WHERE task_id=:t AND owner_id=:o'), {'t': task_id, 'o': execution['owner_id']}).mappings().first()
        if existing:
            if existing['content_hash'] != checksum:
                raise HTTPException(409, 'Artifact already committed with different content')
            return {'saved': True, 'duplicate': True}
        if execution['consumed_at'] is not None:
            raise HTTPException(403, 'Capability consumed')
        task = conn.execute(text('SELECT state FROM tasks WHERE id=:t AND owner_id=:o FOR UPDATE'), {'t': task_id, 'o': execution['owner_id']}).mappings().first()
        if not task or task['state'] != 'running':
            raise HTTPException(409, 'Task is not running')
        conn.execute(text('INSERT INTO artifacts(id,owner_id,task_id,content,content_hash) VALUES (:id,:o,:t,CAST(:c AS jsonb),:h)'),
                     {'id': uuid.uuid4(), 'o': execution['owner_id'], 't': task_id, 'c': json.dumps(content), 'h': checksum})
        conn.execute(text('UPDATE execution_tokens SET consumed_at=now() WHERE token_hash=:h'), {'h': digest})
        conn.execute(text("UPDATE tasks SET state='succeeded',version=version+1,updated_at=now() WHERE id=:t AND owner_id=:o"), {'t': task_id, 'o': execution['owner_id']})
        enqueue(conn, execution['owner_id'], body.content[:3500] + f'\n\n{task_id} [succeeded]', 'artifact:' + str(task_id), task_id=task_id)
        audit(conn, execution['owner_id'], 'artifact.committed', str(task_id))
    return {'saved': True, 'duplicate': False}


def _execution(task_id, authorization):
    token = authorization.removeprefix('Bearer ') if authorization.startswith('Bearer ') else ''
    digest = hashlib.sha256(token.encode()).hexdigest()
    with engine.connect() as conn:
        execution = conn.execute(text('SELECT * FROM execution_tokens WHERE token_hash=:h AND task_id=:t'), {'h': digest, 't': task_id}).mappings().first()
    if not token or not execution or execution['expires_at'] <= datetime.now(UTC):
        raise HTTPException(403, 'Invalid execution capability')
    return execution


@app.get('/internal/tasks/{task_id}/specialist')
def specialist_body(task_id: uuid.UUID, authorization: str = Header(default='')):
    execution = _execution(task_id, authorization)
    with engine.connect() as conn:
        body = conn.execute(text('SELECT body FROM specialist_results WHERE task_id=:t AND owner_id=:o'), {'t': task_id, 'o': execution['owner_id']}).scalar()
    content = body or 'Specialist job reached the internal API. No shell, external tool, or paid transcription ran inside the job.'
    return {'content': content[:16000]}


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
    uvicorn.run(app, host='0.0.0.0', port=8080, access_log=False)

