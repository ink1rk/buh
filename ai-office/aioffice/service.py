import hashlib
import json
import os
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from .calendars import LABELS, CalendarError, credential_flags, deliver_event, status_lines
from .costs import budget_text, fetch_litellm_spend, reconcile
from .db import audit
from .files import VOICE_REPLY, accept_file, describe_incoming, local_runner, transcribe
from .integrations import approval_effect, registry
from .job import PROFILES
from .policy import callback_actor, external_write_allowed, normalize_timezone, parse_due, payload_hash, private_owner

HELP = ('AI Office — задачи и заметки.\n'
        '/task текст — поручение\n/note текст — заметка\n/tasks — последние записи\n'
        '/done полный-UUID — завершить\n/cancel полный-UUID — отменить\n'
        '/remind 2026-10-20T14:00 текст — напоминание\n'
        '/job researcher текст — специалист (researcher, planner, developer, technical_expert)\n'
        '/files — сохранённые файлы и голосовые\n'
        '/calendar — Google и Яндекс\n'
        '/calendar create google|yandex 2030-01-01T12:00 текст — черновик, запись после кнопки\n'
        '/email draft адрес | тема | текст — черновик, без отправки\n'
        '/timezone [Europe/Moscow|+3] — проверить или задать часовой пояс\n/pause /resume /stopall\n'
        '/agents /models /budget /calendar /privacy\n'
        '/ask текст — вопрос ассистенту\n'
        'Почта наружу не уходит. Календарь пишет только ваше событие без участников и только после «Разрешить».')


def enqueue(conn, owner, message, dedupe, category='reply', task_id=None, reply_markup=None):
    payload = {'text': message, 'category': category, 'task_id': str(task_id) if task_id else None}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    conn.execute(text('INSERT INTO outbox_events(id,owner_id,chat_id,payload,dedupe_key) VALUES (:id,:o,:o,CAST(:p AS jsonb),:d) ON CONFLICT(dedupe_key) DO NOTHING'),
                 {'id': uuid.uuid4(), 'o': owner, 'p': json.dumps(payload, ensure_ascii=False), 'd': dedupe})


def create_task(conn, owner, title, kind='task', state='queued'):
    tid, correlation = uuid.uuid4(), uuid.uuid4()
    conn.execute(text('INSERT INTO tasks(id,owner_id,correlation_id,title,kind,state) VALUES (:id,:o,:c,:t,:k,:s)'),
                 {'id': tid, 'o': owner, 'c': correlation, 't': title[:4000], 'k': kind, 's': state})
    audit(conn, owner, 'task.created', str(tid), correlation)
    return tid


def _keyboard(token):
    return {'inline_keyboard': [[{'text': 'Разрешить', 'callback_data': 'a:' + token},
                                  {'text': 'Отклонить', 'callback_data': 'r:' + token}]]}


def _public_env():
    keys = ('GOOGLE_CALENDAR_TOKEN', 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REFRESH_TOKEN',
            'YANDEX_CALDAV_USER', 'YANDEX_CALDAV_PASSWORD', 'YANDEX_CALDAV_HREF')
    return {key: os.environ.get(key, '') for key in keys}


def _calendar_create_args(rest):
    provider, _, tail = rest.strip().partition(' ')
    if provider not in ('google', 'yandex'):
        return None
    when, _, title = tail.partition(' ')
    if not when or not title.strip():
        return ()
    return provider, when, title.strip()


def request_approval(conn, owner, kind, title, payload):
    tid = create_task(conn, owner, title, kind=kind, state='waiting_approval')
    token = str(uuid.uuid4())
    conn.execute(text('INSERT INTO approvals(id,owner_id,task_id,token_hash,payload_hash,payload,expires_at) VALUES (:id,:o,:t,:h,:p,CAST(:j AS jsonb),:e)'),
                 {'id': uuid.uuid4(), 'o': owner, 't': tid, 'h': hashlib.sha256(token.encode()).hexdigest(),
                  'p': payload_hash(payload), 'j': json.dumps(payload, ensure_ascii=False),
                  'e': datetime.now(UTC) + timedelta(minutes=15)})
    where = LABELS.get(payload.get('provider'), kind)
    enqueue(conn, owner,
            f'{tid} [waiting_approval] Черновик {where}. Почта не отправляется. Календарь без участников запишется только после «Разрешить».',
            'approval:' + str(tid), task_id=tid, reply_markup=_keyboard(token))
    return f'{tid} [waiting_approval] Подтверждение отправлено кнопками. Срок 15 минут.'


def budget_reply(conn, owner, settings):
    amount = conn.execute(text('SELECT COALESCE(sum(amount_usd),0) FROM usage_costs WHERE owner_id=:o'), {'o': owner}).scalar_one()
    reserve = conn.execute(text("SELECT COALESCE(sum(reserve_usd),0) FROM llm_calls WHERE owner_id=:o AND created_at>now()-interval '7 days'"), {'o': owner}).scalar_one()
    spend = fetch_litellm_spend(getattr(settings, 'litellm_url', ''), getattr(settings, 'litellm_key', ''))
    status = 'feature_unavailable'
    row = reconcile(estimated_usd=amount, usage_api_status=status, litellm_spend_usd=spend)
    conn.execute(text('INSERT INTO cost_checks(id,owner_id,estimated_usd,usage_api_status,litellm_spend_usd,actual_confirmed) VALUES (:id,:o,:e,:s,:l,false)'),
                 {'id': uuid.uuid4(), 'o': owner, 'e': row['estimated_usd'], 's': status, 'l': row['litellm_spend_usd']})
    audit(conn, owner, 'cost.reconciled')
    return budget_text(estimated=amount, reserve_week=reserve, litellm_spend=spend, usage_api_status=status)


def command(conn, owner, message, settings):
    raw = message.get('text', '').strip()
    if not raw:
        return 'Вложения и голос пока не обрабатываются. Пришлите текст.'
    name, _, arg = raw.partition(' ')
    name = name.split('@')[0].lower()
    user = conn.execute(text('SELECT * FROM users WHERE id=:o FOR UPDATE'), {'o': owner}).mappings().one()
    if name in ('/start', '/help'):
        return HELP
    if name == '/privacy':
        return 'Текст, файлы и голосовые хранятся в вашей PostgreSQL. Голос не отправляется в платный сервис распознавания. При включённом ассистенте вопрос и последние 3 диалога передаются Cursor/Grok. Почта наружу не уходит. Календарь Google или Яндекс получает только подтверждённое событие без участников. Для выгрузки или удаления данных пока обратитесь к оператору.'
    if name == '/timezone':
        if arg.strip():
            try:
                zone = normalize_timezone(arg.strip())
            except Exception:
                return 'Укажите существующий IANA часовой пояс, например Europe/Moscow или +3.'
            conn.execute(text('UPDATE users SET timezone=:z WHERE id=:o'), {'z': zone, 'o': owner})
            audit(conn, owner, 'timezone.updated')
            return 'Часовой пояс сохранён: ' + zone
        return 'Часовой пояс: ' + (user['timezone'] or 'не подтверждён; напоминания выключены')
    if name in ('/pause', '/resume', '/stopall'):
        paused = name != '/resume'
        conn.execute(text('UPDATE users SET paused=:p WHERE id=:o'), {'o': owner, 'p': paused})
        if name == '/stopall':
            conn.execute(text("UPDATE tasks SET state='cancelled',version=version+1,updated_at=now() WHERE owner_id=:o AND state IN ('created','queued','running','waiting_approval','waiting_external')"), {'o': owner})
            conn.execute(text("UPDATE scheduled_triggers SET state='cancelled' WHERE owner_id=:o AND state='pending'"), {'o': owner})
            conn.execute(text("UPDATE outbox_events SET state='failed' WHERE owner_id=:o AND state='pending' AND payload->>'category'='reminder'"), {'o': owner})
        audit(conn, owner, name[1:])
        return 'Новые задания и напоминания приостановлены.' if paused else 'Приём заданий и напоминания возобновлены.'
    if name == '/tasks':
        rows = conn.execute(text('SELECT id,title,state,kind FROM tasks WHERE owner_id=:o ORDER BY created_at DESC LIMIT 8'), {'o': owner}).mappings().all()
        return '\n\n'.join(f"{r['id']} [{r['state']}] {r['kind']}: {r['title'][:250]}" for r in rows) or 'Заданий пока нет.'
    if name == '/files':
        rows = conn.execute(text('SELECT kind,mime,size_bytes,sha256,transcript IS NOT NULL AS has_transcript,created_at FROM stored_files WHERE owner_id=:o ORDER BY created_at DESC LIMIT 8'), {'o': owner}).mappings().all()
        return '\n'.join(f"{r['created_at']} {r['kind']} {r['mime']} {r['size_bytes']} {r['sha256'][:12]}" for r in rows) or 'Файлов пока нет.'
    if name in ('/done', '/cancel'):
        try:
            tid = uuid.UUID(arg.strip())
        except ValueError:
            return 'Укажите полный UUID из /tasks.'
        state = 'succeeded' if name == '/done' else 'cancelled'
        changed = conn.execute(text("UPDATE tasks SET state=:s,version=version+1,updated_at=now() WHERE id=:id AND owner_id=:o AND state NOT IN ('succeeded','failed','cancelled') RETURNING id"), {'s': state, 'id': tid, 'o': owner}).first()
        if not changed:
            return 'Активная задача с таким ID не найдена.'
        conn.execute(text("UPDATE scheduled_triggers SET state='cancelled' WHERE task_id=:id AND owner_id=:o AND state='pending'"), {'id': tid, 'o': owner})
        conn.execute(text("UPDATE outbox_events SET state='failed' WHERE owner_id=:o AND state='pending' AND payload->>'category'='reminder' AND payload->>'task_id'=:id"), {'o': owner, 'id': str(tid)})
        audit(conn, owner, 'task.' + state, str(tid))
        return f'{tid} [{state}]'
    if name == '/agents':
        llm = 'Ассистент: Grok 4.7 через Cursor, только текст.' if getattr(settings, 'llm_enabled', False) else 'LLM-исполнение выключено.'
        return 'Профили: assistant, researcher, planner, developer, technical_expert. ' + llm + ' /job ставит специалиста в очередь отдельного launcher: у Job нет токена Kubernetes и нет shell.'
    if name == '/models':
        base = 'assistant-fast → Cursor / grok-4.7, low, 256k, Fast выключен.' if getattr(settings, 'llm_enabled', False) else 'LLM-провайдеры не подключены. Платные запросы выключены.'
        extra = ' LiteLLM поднят без ключей провайдеров: журнал расходов локальный и не является счётом Cursor.' if getattr(settings, 'litellm_url', '') else ' LiteLLM не подключён к gateway.'
        return base + extra
    if name == '/budget':
        return budget_reply(conn, owner, settings)
    if name == '/calendar' and not arg.startswith('create '):
        providers = getattr(settings, 'calendar_providers', ('google', 'yandex'))
        return status_lines(user['timezone'] or settings.timezone, providers, _public_env())
    if user['paused']:
        return 'Приём заданий приостановлен. /resume — продолжить.'
    if name == '/calendar' and arg.startswith('create '):
        parsed = _calendar_create_args(arg[len('create '):])
        if parsed is None:
            return 'Укажите календарь: /calendar create google 2030-01-01T12:00 текст или yandex вместо google.'
        if parsed == ():
            return 'Формат: /calendar create google 2030-01-01T12:00 текст'
        provider, when, title = parsed
        if provider not in getattr(settings, 'calendar_providers', ('google', 'yandex')):
            return 'Доступны только google и yandex.'
        zone = user['timezone'] or settings.timezone
        try:
            parse_due(when, zone)
        except (ValueError, TypeError) as exc:
            return str(exc) if str(exc).startswith(('Сначала', 'Неоднозначное', 'Указанное', 'Время')) else 'Некорректная дата. Используйте ISO 8601.'
        return request_approval(conn, owner, 'calendar', title, {
            'kind': 'calendar', 'provider': provider, 'starts': when, 'title': title, 'timezone': zone,
        })
    if name == '/email':
        if not arg.startswith('draft '):
            return 'Почта не подключена. Черновик: /email draft адрес | тема | текст. Отправка выключена.'
        parts = [part.strip() for part in arg[len('draft '):].split('|', 2)]
        if len(parts) != 3 or not all(parts):
            return 'Формат: /email draft адрес | тема | текст'
        return request_approval(conn, owner, 'email', parts[1], {'kind': 'email', 'to': parts[0], 'subject': parts[1], 'body': parts[2]})
    if name == '/job':
        profile, _, title = arg.partition(' ')
        profile = profile.strip().lower()
        if profile not in PROFILES or not title.strip():
            return 'Формат: /job researcher|planner|developer|technical_expert текст'
        tid = create_task(conn, owner, title.strip(), 'specialist', 'queued')
        conn.execute(text('INSERT INTO specialist_jobs(task_id,owner_id,profile) VALUES (:t,:o,:p)'), {'t': tid, 'o': owner, 'p': profile})
        audit(conn, owner, 'specialist.queued', str(tid))
        return f'{tid} [queued] Профиль {profile} поставлен в очередь launcher.'
    if name == '/remind':
        date, _, title = arg.partition(' ')
        if not title.strip():
            return 'Формат: /remind 2026-10-20T14:00 текст'
        try:
            due = parse_due(date, user['timezone'])
        except (ValueError, TypeError) as exc:
            return str(exc) if str(exc).startswith(('Сначала', 'Неоднозначное', 'Указанное', 'Время')) else 'Некорректная дата. Используйте ISO 8601.'
        tid = create_task(conn, owner, title, kind='reminder')
        conn.execute(text('INSERT INTO scheduled_triggers(id,owner_id,task_id,due_at_utc,timezone,local_time,dedupe_key) VALUES (:id,:o,:t,:due,:z,:l,:d)'),
                     {'id': uuid.uuid4(), 'o': owner, 't': tid, 'due': due, 'z': user['timezone'], 'l': date, 'd': 'reminder:' + str(tid)})
        return f'{tid} [queued] Напоминание: {date} ({user["timezone"]}).'
    if raw.startswith('/') and name not in ('/task', '/note', '/ask'):
        return 'Неизвестная команда. /help'
    title = arg.strip() if name in ('/task', '/note', '/ask') else raw
    if not title:
        return 'После команды нужен текст.'
    kind = 'note' if name == '/note' else 'task'
    if getattr(settings, 'llm_enabled', False) and name not in ('/task', '/note'):
        tid = create_task(conn, owner, title, 'chat', 'queued')
        return f'{tid} [queued] Передано ассистенту Grok 4.7.'
    state = 'succeeded' if kind == 'note' else 'waiting_external'
    tid = create_task(conn, owner, title, kind, state)
    return f'{tid} [{state}] ' + ('Заметка сохранена.' if kind == 'note' else 'Поручение сохранено. Автоматическое исполнение ожидает подключения LLM.')


def apply_callback(conn, owner, query, settings):
    """Consume the approval inside the open transaction. The network call happens after commit."""
    data = query.get('data') or ''
    decision = 'approve' if data.startswith('a:') else 'reject'
    token = data[2:]
    digest = hashlib.sha256(token.encode()).hexdigest()
    approval = conn.execute(text('SELECT * FROM approvals WHERE token_hash=:h AND owner_id=:o FOR UPDATE'), {'h': digest, 'o': owner}).mappings().first()
    if not approval:
        return 'Запрос подтверждения не найден.', None
    if approval['consumed_at'] is not None:
        return 'Решение уже принято. Повтор ничего не вызывает.', None
    payload = approval['payload']
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        payload = {}
    allowed = external_write_allowed(capability=True, approval=approval, owner=owner, payload=payload)
    providers = registry(calendar_provider=getattr(settings, 'calendar_provider', ''), email_provider=getattr(settings, 'email_provider', ''))
    kind = payload.get('kind')
    provider = payload.get('provider') or ''
    flags = credential_flags(_public_env())
    chosen = provider if kind == 'calendar' else providers.get(kind, '')
    effect = approval_effect(allowed=allowed, decision=decision, provider=chosen, kind=kind, credentials=flags.get(provider, False))
    if effect['reason'] == 'denied':
        return 'Подтверждение недействительно или истекло. Внешний вызов не выполняется.', None
    consumed = conn.execute(text('UPDATE approvals SET consumed_at=now(), decision=:d WHERE id=:id AND consumed_at IS NULL RETURNING id'), {'d': decision, 'id': approval['id']}).first()
    if not consumed:
        return 'Решение уже принято. Повтор ничего не вызывает.', None
    if effect['task_state']:
        conn.execute(text('UPDATE tasks SET state=:s,version=version+1,updated_at=now() WHERE id=:t AND owner_id=:o'),
                     {'s': effect['task_state'], 't': approval['task_id'], 'o': owner})
    audit(conn, owner, 'approval.' + effect['reason'], str(approval['task_id']))
    if effect['outbound']:
        call = {'task_id': approval['task_id'], 'approval_id': str(approval['id']), 'provider': provider,
                'title': payload.get('title') or '', 'starts': payload.get('starts') or '',
                'timezone': payload.get('timezone') or settings.timezone}
        enqueue(conn, owner, f"{approval['task_id']} [running] Подтверждено. Записываю событие в {LABELS.get(provider, provider)} без участников.",
                'calendar-start:' + str(approval['id']), task_id=approval['task_id'])
        return None, call
    if effect['reason'] == 'rejected':
        return f"{approval['task_id']} [cancelled] Отклонено. Внешний сервис не вызывался.", None
    if effect['reason'] == 'credentials_missing':
        return f"{approval['task_id']} [waiting_external] Подтверждено локально. Данных {LABELS.get(provider, provider)} нет, исходящий вызов не выполнялся.", None
    if effect['reason'] == 'provider_not_configured':
        return f"{approval['task_id']} [waiting_external] Подтверждено локально. Провайдер не выбран, исходящий вызов не выполнялся.", None
    return f"{approval['task_id']} [waiting_external] Подтверждено локально. Запись во внешний сервис не реализована и не выполнялась.", None


def store_incoming(conn, owner, message, data, settings):
    described = describe_incoming(message)
    if not described:
        return 'Вложения и голос пока не обрабатываются. Пришлите текст.'
    kind, mime, size, _file_id, unique_id = described
    if not unique_id:
        return 'Файл без идентификатора отклонён.'
    try:
        digest = accept_file(kind, mime, size if isinstance(size, int) else len(data), data)
    except ValueError:
        return 'Файл отклонён: тип или размер вне allowlist (до 2 МБ, документы/изображения/аудио).'
    transcript = transcribe(kind, data, getattr(settings, 'local_transcriber', ''), local_runner)
    conn.execute(text('INSERT INTO stored_files(id,owner_id,kind,mime,size_bytes,sha256,content,unique_id,transcript) VALUES (:id,:o,:k,:m,:s,:h,:c,:u,:t) ON CONFLICT (owner_id, unique_id) DO NOTHING'),
                 {'id': uuid.uuid4(), 'o': owner, 'k': kind, 'm': mime, 's': len(data), 'h': digest, 'c': data, 'u': unique_id, 't': transcript})
    audit(conn, owner, 'file.stored', digest)
    if kind in ('voice', 'audio'):
        return VOICE_REPLY
    return f'Файл сохранён: {kind}, {len(data)} байт, sha256 {digest[:12]}. Список: /files'


def process_callback(engine, update, settings, opener=None):
    update_id = update.get('update_id')
    query = update.get('callback_query') or {}
    if not isinstance(update_id, int):
        return 'Нет доступа'
    owner = callback_actor(update, settings.owners)
    call = None
    with engine.begin() as conn:
        inserted = conn.execute(text('INSERT INTO telegram_updates(update_id,owner_id) VALUES (:id,:o) ON CONFLICT DO NOTHING RETURNING update_id'), {'id': update_id, 'o': owner}).first()
        if not inserted:
            return 'Решение уже принято. Повтор ничего не вызывает.'
        conn.execute(text('UPDATE poll_state SET next_offset=GREATEST(next_offset,:n) WHERE id=1'), {'n': update_id + 1})
        if not owner:
            return 'Нет доступа'
        conn.execute(text('INSERT INTO users(id,timezone) VALUES (:o,:z) ON CONFLICT DO NOTHING'), {'o': owner, 'z': settings.timezone})
        reply, call = apply_callback(conn, owner, query, settings)
        if reply:
            enqueue(conn, owner, reply, 'callback:' + str(update_id))
    if not call:
        return 'Принято'
    try:
        created = deliver_event(call['provider'], call['title'], call['starts'], call['timezone'], call['approval_id'], _public_env(), opener or urllib.request.urlopen)
        reply = f"{call['task_id']} [succeeded] Событие записано в {LABELS.get(call['provider'], call['provider'])}: {created['id']}"
        state, action = 'succeeded', 'calendar.written'
    except CalendarError:
        reply = f"{call['task_id']} [waiting_external] Подтверждение уже принято. Запись в календарь не выполнена, повтор кнопкой не создаёт второе событие."
        state, action = 'waiting_external', 'calendar.write_failed'
    with engine.begin() as conn:
        conn.execute(text('UPDATE tasks SET state=:s,version=version+1,updated_at=now() WHERE id=:t AND owner_id=:o'),
                     {'s': state, 't': call['task_id'], 'o': owner})
        audit(conn, owner, action, str(call['task_id']))
        enqueue(conn, owner, reply, 'calendar-result:' + call['approval_id'], task_id=call['task_id'])
    return 'Принято'


def process_update(engine, update, settings, fetch_file=None):
    update_id = update.get('update_id')
    if not isinstance(update_id, int) or 'callback_query' in update:
        return False
    owner = private_owner(update, settings.owners)
    message = update.get('message') or {}
    with engine.begin() as conn:
        inserted = conn.execute(text('INSERT INTO telegram_updates(update_id,owner_id) VALUES (:id,:o) ON CONFLICT DO NOTHING RETURNING update_id'), {'id': update_id, 'o': owner}).first()
        if inserted and owner:
            conn.execute(text('INSERT INTO users(id,timezone) VALUES (:o,:z) ON CONFLICT DO NOTHING'), {'o': owner, 'z': settings.timezone})
            paused = conn.execute(text('SELECT paused FROM users WHERE id=:o'), {'o': owner}).scalar_one()
            incoming = describe_incoming(message)
            if incoming and not message.get('text'):
                if paused:
                    reply = 'Приём заданий приостановлен. /resume — продолжить.'
                elif fetch_file is None:
                    reply = 'Файл получен, но загрузка сейчас недоступна.'
                else:
                    _kind, _mime, size, file_id, _unique = incoming
                    if isinstance(size, int) and size > 2_000_000:
                        reply = 'Файл отклонён: размер больше 2 МБ.'
                    else:
                        try:
                            data = fetch_file(file_id)
                        except Exception:
                            reply = 'Не удалось скачать файл из Telegram. Он не отправлялся в другой сервис.'
                            data = None
                        reply = store_incoming(conn, owner, message, data, settings) if data is not None else reply
            else:
                reply = command(conn, owner, message, settings)
            enqueue(conn, owner, reply, 'telegram:' + str(update_id))
        conn.execute(text('UPDATE poll_state SET next_offset=GREATEST(next_offset,:n) WHERE id=1'), {'n': update_id + 1})
    return bool(inserted and owner)


def schedule_due(engine, now=None):
    now = now or datetime.now(UTC)
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT s.*,t.title FROM scheduled_triggers s JOIN users u ON u.id=s.owner_id JOIN tasks t ON t.id=s.task_id WHERE s.state='pending' AND s.due_at_utc<=:now AND NOT u.paused ORDER BY s.due_at_utc FOR UPDATE OF s SKIP LOCKED LIMIT 100"), {'now': now}).mappings().all()
        for row in rows:
            missed = now - row['due_at_utc'] > timedelta(hours=24)
            state = 'missed' if missed else 'enqueued'
            message = ('Пропущено напоминание старше 24 часов: ' if missed else 'Напоминание: ') + row['title'][:3000] + f"\n{row['task_id']}"
            enqueue(conn, row['owner_id'], message, row['dedupe_key'], category='reminder', task_id=row['task_id'])
            conn.execute(text('UPDATE scheduled_triggers SET state=:s WHERE id=:id'), {'s': state, 'id': row['id']})
            audit(conn, row['owner_id'], 'reminder.' + state, str(row['task_id']))
    return len(rows)
