"""Trusted launcher. The gateway has no Kubernetes token; this process does, and jobs do not."""
import base64
import json
import logging
import os
import secrets
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from .costs import budget_blocks
from .db import audit
from .job import specialist_job, specialist_prompt
from .llm import finish_call
from .service import enqueue

log = logging.getLogger('aioffice')
RESERVE = Decimal('0.50')
TRANSPORT = 'Launcher queued a specialist job. LLM is disabled, so no paid call was made.'


class Kubernetes:
    def __init__(self, request):
        self.request = request

    def get_job(self, name):
        status, body = self.request('GET', '/apis/batch/v1/namespaces/ai-jobs/jobs/' + name)
        if status == 404:
            return None
        if status >= 300:
            raise RuntimeError('Kubernetes job read failed')
        return body

    def create_job(self, job):
        status, body = self.request('POST', '/apis/batch/v1/namespaces/ai-jobs/jobs', job)
        if status not in (200, 201, 409):
            raise RuntimeError('Kubernetes job create failed')
        return body

    def secret_exists(self, name):
        status, _body = self.request('GET', '/api/v1/namespaces/ai-jobs/secrets/' + name)
        if status == 200:
            return True
        if status == 404:
            return False
        raise RuntimeError('Kubernetes secret read failed')

    def ensure_secret(self, name, token):
        if self.secret_exists(name):
            return
        secret = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': name, 'namespace': 'ai-jobs'},
                  'type': 'Opaque', 'data': {'token': base64.b64encode(token.encode()).decode()}}
        created, _body = self.request('POST', '/api/v1/namespaces/ai-jobs/secrets', secret)
        if created not in (200, 201, 409):
            raise RuntimeError('Kubernetes secret create failed')


def in_cluster_request(method, path, body=None):
    host = os.environ['KUBERNETES_SERVICE_HOST']
    port = os.environ.get('KUBERNETES_SERVICE_PORT', '443')
    token = open('/var/run/secrets/kubernetes.io/serviceaccount/token', encoding='utf-8').read()
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f'https://{host}:{port}{path}', data=data, method=method,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    context = urllib.request.ssl.create_default_context(cafile='/var/run/secrets/kubernetes.io/serviceaccount/ca.crt')
    try:
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw) if raw else {}
        except ValueError:
            parsed = {}
        return exc.code, parsed


def _budget_open(conn, owner):
    budget = conn.execute(text("SELECT COALESCE(sum(reserve_usd) FILTER(WHERE created_at>now()-interval '7 days'),0) AS week, COALESCE(sum(reserve_usd) FILTER(WHERE created_at>date_trunc('month',now())),0) AS month FROM llm_calls WHERE owner_id=:o"), {'o': owner}).mappings().one()
    return not budget_blocks(budget['week'], budget['month'], RESERVE)


def _bridge(settings, prompt):
    request = urllib.request.Request(
        settings.bridge_url + '/complete', data=json.dumps({'text': prompt}).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + settings.bridge_token})
    with urllib.request.urlopen(request, timeout=85) as response:
        result = json.load(response)
    if not result.get('text') or result.get('model') != 'grok-4.7' or result.get('tools_enabled') is not False:
        raise ValueError('Invalid bridge result')
    return result


def prepare_specialist(engine, settings, task):
    """One budgeted bridge call at most. A missing result is not retried."""
    if not settings.llm_enabled:
        return TRANSPORT
    with engine.begin() as conn:
        call = conn.execute(text('SELECT state FROM llm_calls WHERE task_id=:t FOR UPDATE'), {'t': task['id']}).mappings().first()
        if call and call['state'] == 'finished':
            return None
        if call and call['state'] in ('uncertain', 'reserved', 'failed'):
            conn.execute(text("UPDATE llm_calls SET state='uncertain',finished_at=COALESCE(finished_at,now()) WHERE task_id=:t AND state<>'finished'"), {'t': task['id']})
            conn.execute(text("UPDATE tasks SET state='waiting_external',version=version+1,updated_at=now() WHERE id=:t AND state='running'"), {'t': task['id']})
            enqueue(conn, task['owner_id'], f"{task['id']} [waiting_external] Повторный платный вызов специалиста не выполняется.", 'specialist-once:' + str(task['id']))
            return False
        if not _budget_open(conn, task['owner_id']):
            conn.execute(text("UPDATE tasks SET state='waiting_external',version=version+1,updated_at=now() WHERE id=:t"), {'t': task['id']})
            enqueue(conn, task['owner_id'], f"{task['id']} [waiting_external] Лимит резерва LLM исчерпан. /budget", 'budget:' + str(task['id']))
            return False
        conn.execute(text("INSERT INTO llm_calls(id,task_id,owner_id,model,state,reserve_usd) VALUES (:id,:t,:o,'grok-4.7','reserved',:r)"),
                     {'id': uuid.uuid4(), 't': task['id'], 'o': task['owner_id'], 'r': RESERVE})
    try:
        result = _bridge(settings, specialist_prompt(task['profile'], task['title']))
    except Exception as exc:
        log.warning('Specialist bridge uncertain; exception_type=%s', type(exc).__name__)
        finish_call(engine, task, None)
        return False
    with engine.begin() as conn:
        estimate = result.get('estimated_usd')
        conn.execute(text("UPDATE llm_calls SET state='finished',estimated_usd=:e,usage=CAST(:u AS jsonb),finished_at=now() WHERE task_id=:t"),
                     {'e': estimate, 'u': json.dumps(result.get('usage')), 't': task['id']})
        if estimate is not None:
            conn.execute(text("INSERT INTO usage_costs(id,owner_id,task_id,provider,amount_usd,billing_state) VALUES (:id,:o,:t,'cursor/grok-4.7',:e,'estimated')"),
                         {'id': uuid.uuid4(), 'o': task['owner_id'], 't': task['id'], 'e': estimate})
        conn.execute(text('INSERT INTO specialist_results(task_id,owner_id,profile,body) VALUES (:t,:o,:p,:b) ON CONFLICT DO NOTHING'),
                     {'t': task['id'], 'o': task['owner_id'], 'p': task['profile'], 'b': result['text'][:16000]})
        audit(conn, task['owner_id'], 'specialist.llm_finished', str(task['id']))
    return result['text'][:16000]


def submit_job(engine, kube, settings, task, body):
    image = settings.app_image
    secret_name = 'ex-' + str(task['id']).replace('-', '')[:20]
    job_name = 'sp-' + str(task['id']).replace('-', '')
    if kube.get_job(job_name):
        with engine.begin() as conn:
            conn.execute(text('UPDATE specialist_jobs SET job_name=:n WHERE task_id=:t AND job_name IS NULL'), {'n': job_name, 't': task['id']})
        return job_name
    secret_ready = kube.secret_exists(secret_name)
    with engine.begin() as conn:
        existing = conn.execute(text('SELECT consumed_at FROM execution_tokens WHERE task_id=:t'), {'t': task['id']}).mappings().first()
        conn.execute(text('INSERT INTO specialist_results(task_id,owner_id,profile,body) VALUES (:t,:o,:p,:b) ON CONFLICT DO NOTHING'),
                     {'t': task['id'], 'o': task['owner_id'], 'p': task['profile'], 'b': body[:16000]})
        if existing and existing['consumed_at'] is not None:
            return job_name
        if existing and secret_ready:
            audit(conn, task['owner_id'], 'specialist.submitted', str(task['id']))
        elif existing:
            conn.execute(text('DELETE FROM execution_tokens WHERE task_id=:t AND consumed_at IS NULL'), {'t': task['id']})
            existing = None
        if existing is None:
            token = secrets.token_urlsafe(32)
            conn.execute(text('INSERT INTO execution_tokens(token_hash,owner_id,task_id,expires_at) VALUES (:h,:o,:t,:e)'),
                         {'h': __import__('hashlib').sha256(token.encode()).hexdigest(), 'o': task['owner_id'], 't': task['id'], 'e': datetime.now(UTC) + timedelta(minutes=30)})
            audit(conn, task['owner_id'], 'specialist.submitted', str(task['id']))
        else:
            token = None
    if token is not None:
        kube.ensure_secret(secret_name, token)
    kube.create_job(specialist_job(task['id'], image=image, secret_name=secret_name, profile=task['profile']))
    with engine.begin() as conn:
        conn.execute(text('UPDATE specialist_jobs SET job_name=:n WHERE task_id=:t'), {'n': job_name, 't': task['id']})
    return job_name


def launch_one(engine, kube, settings):
    with engine.begin() as conn:
        row = conn.execute(text("""SELECT t.*, s.profile FROM tasks t
            JOIN specialist_jobs s ON s.task_id=t.id JOIN users u ON u.id=t.owner_id
            WHERE t.kind='specialist' AND NOT u.paused AND s.job_name IS NULL
              AND (t.state='queued' OR t.state='running')
            ORDER BY t.created_at FOR UPDATE OF t SKIP LOCKED LIMIT 1""")).mappings().first()
        if not row:
            return False
        if row['state'] == 'queued':
            conn.execute(text("UPDATE tasks SET state='running',version=version+1,updated_at=now() WHERE id=:t"), {'t': row['id']})
        task = dict(row)
    if settings.llm_enabled:
        prepared = prepare_specialist(engine, settings, task)
        if prepared is False:
            return True
        if prepared is None:
            with engine.connect() as conn:
                prepared = conn.execute(text('SELECT body FROM specialist_results WHERE task_id=:t'), {'t': task['id']}).scalar()
            if not prepared:
                with engine.begin() as conn:
                    conn.execute(text("UPDATE tasks SET state='waiting_external',version=version+1,updated_at=now() WHERE id=:t"), {'t': task['id']})
                    enqueue(conn, task['owner_id'], f"{task['id']} [waiting_external] Результат специалиста не сохранён. Повторный платный вызов не выполняется.", 'specialist-missing:' + str(task['id']))
                return True
    else:
        prepared = TRANSPORT
    try:
        submit_job(engine, kube, settings, task, prepared)
    except ValueError:
        with engine.begin() as conn:
            conn.execute(text("UPDATE tasks SET state='waiting_external',version=version+1,updated_at=now() WHERE id=:t AND state='running'"), {'t': task['id']})
            enqueue(conn, task['owner_id'], f"{task['id']} [waiting_external] Образ специалиста не закреплён digest.", 'specialist-image:' + str(task['id']))
    return True


class Launcher:
    def __init__(self, engine, settings, stop, kube=None):
        self.engine, self.settings, self.stop = engine, settings, stop
        self.kube = kube or Kubernetes(in_cluster_request)

    def run(self):
        if not self.settings.launcher_enabled:
            return
        while not self.stop.is_set():
            try:
                with self.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as lock:
                    if not lock.execute(text('SELECT pg_try_advisory_lock(185115005)')).scalar_one():
                        self.stop.wait(5)
                        continue
                    try:
                        while not self.stop.is_set():
                            lock.execute(text('SELECT 1'))
                            if not launch_one(self.engine, self.kube, self.settings):
                                self.stop.wait(2)
                    finally:
                        lock.execute(text('SELECT pg_advisory_unlock(185115005)'))
            except Exception as exc:
                log.error('Launcher retry; exception_type=%s', type(exc).__name__)
                self.stop.wait(5)


def main():
    import threading
    from .config import Settings
    from .db import engine_for, migrate
    settings = Settings.from_env()
    engine = engine_for(settings.database_url)
    migrate(engine)
    Launcher(engine, settings, threading.Event()).run()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
    main()
