"""Серверы MCP стола. Протокол — тот же, что у моста с телефоном.

Отдельная виртуалка под MCP здесь хуже: пароли IMAP и CalDAV уже лежат на
машине Hermes, а Hermes сам поднимает сервер как дочерний процесс. Второй
хост только скопировал бы секреты и добавил переход по сети.

Финансовый сервер сюда не входит: приложения финансов больше нет, и инструменты
без него отвечали бы отказом.
"""
import json
import os
import urllib.parse
import urllib.request

from phone.mcp import Server, ToolError, no_arguments

READ = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True}
DESTRUCTIVE = {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True}
LOCAL_READ = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
LOCAL_WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}

KINDS = ("yandex", "gmail", "calendar", "notes", "telegram", "voice")

_MAIL = {
    "yandex": "Яндекс",
    "gmail": "Google (Gmail)",
}


def build(kind, mailbox_for=None, calendar_clients=None, notes=None,
          telegram=None, voice=None):
    if kind in _MAIL:
        return _mail_server(kind, mailbox_for)
    if kind == "calendar":
        return _calendar_server(calendar_clients)
    if kind == "notes":
        return _notes_server(notes)
    if kind == "telegram":
        return _telegram_server(telegram)
    if kind == "voice":
        return _voice_server(voice)
    raise ToolError(f"неизвестный сервер {kind}")


def _result(text, data):
    return {"text": text, "data": data}


def _guard(fn):
    from core.actions import ProviderError

    try:
        return fn()
    except ProviderError as exc:
        raise ToolError(str(exc)) from exc
    except OSError as exc:
        raise ToolError(f"{type(exc).__name__}: {exc}") from exc


def _mail_server(account_name, mailbox_for):
    title = _MAIL[account_name]
    server = Server(
        f"desk-{account_name}", "1.0.0",
        f"Почта {title} владельца. Инструменты сами ходят в ящик. "
        "Не говори, что почта только для чтения, и не проси пароль: его нет в "
        "этом разговоре. Папки для частых писем создаёт "
        f"{account_name}_create_sender_folders — имена берутся из подсчёта, "
        "не из догадки и письма не трогает. Перенос и удаление — "
        f"{account_name}_move и {account_name}_delete, только по uid из "
        f"{account_name}_recent и только когда владелец явно попросил. "
        "За раз не больше 20 писем. Отправку письма не делай, пока владелец "
        "явно не скажет «отправь».")

    def mailbox():
        if mailbox_for is not None:
            return mailbox_for(account_name)
        from providers.email import Mailbox
        from core.config import config
        account = next((item for item in config.email.accounts
                        if item.name == account_name), None)
        if account is None:
            raise ToolError(f"ящик {title} не настроен")
        return Mailbox(account)

    @server.tool(
        f"{account_name}_status",
        f"Жив ли ящик {title} и какой у него адрес. Пароль не возвращает.",
        no_arguments(), title=f"Ящик {title}", annotations=READ)
    def status():
        def run():
            box = mailbox()
            box.check()
            return _result(
                f"{title}: ящик {box.account.user} отвечает.",
                {"account": account_name, "address": box.account.user, "ok": True})
        return _guard(run)

    @server.tool(
        f"{account_name}_folders",
        f"Список папок ящика {title}.",
        no_arguments(), title=f"Папки {title}", annotations=READ)
    def folders():
        names = _guard(lambda: mailbox().list_folders())
        shown = ", ".join(names) if names else "папок нет"
        return _result(f"{title}: {shown}.", {"account": account_name, "folders": names})

    @server.tool(
        f"{account_name}_recent",
        f"Последние письма {title}: от кого, тема и дата. Тело письма не тянет.",
        {"type": "object",
         "properties": {
             "folder": {"type": "string", "description": "папка, по умолчанию INBOX"},
             "limit": {"type": "integer", "minimum": 1, "maximum": 40, "default": 15},
         },
         "additionalProperties": False},
        title=f"Последние письма {title}", annotations=READ)
    def recent(folder=None, limit=15):
        payload = _guard(lambda: mailbox().recent(folder or None, limit))
        if not payload["letters"]:
            text = f"{title}: в {payload['folder']} писем не видно."
        else:
            lines = [f"{title}, {payload['folder']}:"]
            for item in payload["letters"]:
                who = item["name"] or item["address"]
                uid = item.get("uid") or ""
                prefix = f"uid {uid}, " if uid else ""
                lines.append(
                    f"— {prefix}{who} <{item['address']}>: {item['subject'] or 'без темы'}")
            text = "\n".join(lines)
        return _result(text, payload)

    @server.tool(
        f"{account_name}_frequent_senders",
        f"Кто чаще всего писал в последних письмах {title}. "
        "Это подсчёт по ящику, а не предположение.",
        {"type": "object",
         "properties": {
             "folder": {"type": "string"},
             "sample": {"type": "integer", "minimum": 1, "maximum": 500, "default": 200},
         },
         "additionalProperties": False},
        title=f"Частые отправители {title}", annotations=READ)
    def frequent(folder=None, sample=200):
        payload = _guard(lambda: mailbox().frequent_senders(folder or None, sample))
        return _result(_senders_text(title, payload), payload)

    @server.tool(
        f"{account_name}_create_folder",
        f"Создать одну папку в {title}. Письма не перемещает.",
        {"type": "object",
         "properties": {"name": {"type": "string", "description": "имя новой папки"}},
         "required": ["name"], "additionalProperties": False},
        title=f"Создать папку {title}", annotations=WRITE)
    def create_folder(name):
        payload = _guard(lambda: mailbox().create_folder(name))
        if payload["created"]:
            text = f"{title}: папка «{payload['folder']}» создана."
        else:
            text = f"{title}: папка «{payload['folder']}» уже была."
        return _result(text, payload)

    @server.tool(
        f"{account_name}_create_sender_folders",
        f"Создать в {title} папки для отправителей, которые повторяются "
        "в последней выборке не меньше min_count раз. Уже существующие не "
        "трогает. Письма не перекладывает и не удаляет.",
        {"type": "object",
         "properties": {
             "folder": {"type": "string", "description": "где считать, по умолчанию INBOX"},
             "sample": {"type": "integer", "minimum": 1, "maximum": 500, "default": 200},
             "min_count": {"type": "integer", "minimum": 2, "maximum": 100, "default": 5},
             "max_folders": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10},
         },
         "additionalProperties": False},
        title=f"Папки для частых писем {title}", annotations=WRITE)
    def create_sender_folders(folder=None, sample=200, min_count=5, max_folders=10):
        payload = _guard(lambda: mailbox().create_sender_folders(
            folder or None, sample, min_count, max_folders))
        lines = [_senders_text(title, payload)]
        if payload["created"]:
            lines.append("Созданы: " + ", ".join(
                item["folder"] for item in payload["created"]) + ".")
        else:
            lines.append("Новых папок не создано.")
        if payload["already"]:
            lines.append("Уже были: " + ", ".join(
                item["folder"] for item in payload["already"]) + ".")
        return _result("\n".join(lines), payload)

    @server.tool(
        f"{account_name}_move",
        f"Перенести письма {title} в существующую папку. "
        "uids — номера uid из recent, не тема и не порядковый номер в списке. "
        "Вызывай только когда владелец явно просит перенести эти письма.",
        {"type": "object",
         "properties": {
             "uids": {"type": "array", "items": {"type": "string"},
                      "minItems": 1, "maxItems": 20,
                      "description": "uid писем из recent"},
             "destination": {"type": "string", "description": "куда положить"},
             "folder": {"type": "string", "description": "откуда, по умолчанию INBOX"},
         },
         "required": ["uids", "destination"], "additionalProperties": False},
        title=f"Перенести письма {title}", annotations=WRITE)
    def move(uids, destination, folder=None):
        payload = _guard(lambda: mailbox().move(uids, destination, folder or None))
        return _result(_touched(title, "перенесено", payload, payload["destination"]), payload)

    @server.tool(
        f"{account_name}_delete",
        f"Удалить письма {title}. uids — номера uid из recent. "
        "Остальные письма папки не трогает. Вызывай только когда владелец "
        "явно просит удалить эти письма.",
        {"type": "object",
         "properties": {
             "uids": {"type": "array", "items": {"type": "string"},
                      "minItems": 1, "maxItems": 20,
                      "description": "uid писем из recent"},
             "folder": {"type": "string", "description": "где лежат, по умолчанию INBOX"},
         },
         "required": ["uids"], "additionalProperties": False},
        title=f"Удалить письма {title}", annotations=DESTRUCTIVE)
    def delete(uids, folder=None):
        payload = _guard(lambda: mailbox().delete(uids, folder or None))
        return _result(_touched(title, "удалено", payload), payload)

    return server


def _touched(title, verb, payload, destination=None):
    where = f" из {payload['folder']}"
    if destination:
        where += f" в {destination}"
    lines = [f"{title}: {verb} {len(payload['uids'])}{where}."]
    for item in payload["letters"]:
        who = item.get("name") or item.get("address") or "письмо"
        address = item.get("address") or ""
        subject = item.get("subject") or "без темы"
        who = f"{who} <{address}>" if address else who
        lines.append(f"— uid {item['uid']}, {who}: {subject}")
    return "\n".join(lines)


def _senders_text(title, payload):
    if not payload["senders"]:
        return f"{title}: в выборке из {payload['sampled']} писем отправителей нет."
    lines = [f"{title}: по {payload['sampled']} письмам в {payload['folder']}."]
    for item in payload["senders"][:15]:
        who = item["name"] or item["address"]
        lines.append(f"— {who} <{item['address']}>: {item['count']}")
    return "\n".join(lines)


def _calendar_server(calendar_clients):
    server = Server(
        "desk-calendar", "1.0.0",
        "Календарь владельца по CalDAV. Сейчас это Яндекс, если он настроен. "
        "Google Calendar появляется здесь же, когда задан аккаунт google: "
        "пароль IMAP Gmail календарь Google не открывает. "
        "Событие на весь день — не созвон в полночь. Занятое время не забивай "
        "новой встречей, пока владелец сам не попросил записать поверх.")

    def clients():
        if calendar_clients is not None:
            return calendar_clients()
        from providers.calendar import clients as factory
        return factory()

    @server.tool(
        "calendar_status",
        "Какие календари настроены и как они называются на сервере. "
        "Google отмечен отдельно.",
        no_arguments(), title="Календари", annotations=READ)
    def status():
        found = _guard(lambda: [(item.account.name, item.check()) for item in clients()])
        names = [name for name, _ in found]
        google = "google" in names
        if not names:
            text = ("Календарь не настроен. Google Calendar сам не подключится: "
                    "нужен аккаунт CalDAV google, пароль Gmail его не заменяет.")
        else:
            text = "Календари: " + ", ".join(names) + "."
            if not google:
                text += " Google Calendar не подключён."
        return _result(text, {"accounts": [
            {"account": name, "calendars": calendars} for name, calendars in found],
            "google": google})

    @server.tool(
        "calendar_events",
        "Встречи на ближайшие дни. Пустой список без ошибки значит, что встреч нет.",
        {"type": "object",
         "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 60,
                                 "default": 14}},
         "additionalProperties": False},
        title="Расписание", annotations=READ)
    def events(days=14):
        import datetime
        from core.config import config

        def run():
            start = datetime.datetime.now(config.tz)
            end = start + datetime.timedelta(days=int(days))
            found = []
            for client in clients():
                for event in client.events(start, end):
                    item = event.as_dict()
                    item["when"] = _when(event)
                    found.append(item)
            found.sort(key=lambda item: item.get("start") or 0)
            return found

        found = _guard(run)
        if not found:
            text = "В ближайшие дни встреч нет."
        else:
            lines = ["Ближайшее:"]
            for item in found[:20]:
                lines.append(f"— {item['when']}: {item['summary'] or 'без названия'}")
            text = "\n".join(lines)
        return _result(text, {"events": found})

    @server.tool(
        "calendar_create",
        "Записать встречу. Время — ISO, часовой пояс владельца, если не указан.",
        {"type": "object",
         "properties": {
             "summary": {"type": "string"},
             "start": {"type": "string", "description": "начало, ISO 8601"},
             "end": {"type": "string", "description": "конец, ISO 8601"},
             "minutes": {"type": "integer", "minimum": 5, "maximum": 1440, "default": 60},
             "account": {"type": "string", "description": "yandex или google"},
             "location": {"type": "string"},
             "description": {"type": "string"},
             "calendar": {"type": "string"},
         },
         "required": ["summary", "start"], "additionalProperties": False},
        title="Записать встречу", annotations=WRITE)
    def create(summary, start, end=None, minutes=60, account=None, location="",
               description="", calendar=None):
        from providers.calendar import _moment
        import datetime

        def run():
            chosen = _pick_account(clients(), account)
            start_at = _moment(start)
            end_at = _moment(end) if end else start_at + datetime.timedelta(minutes=int(minutes))
            if end_at <= start_at:
                raise ToolError("конец встречи не позже начала")
            return chosen.create(summary.strip(), start_at, end=end_at,
                                 description=description or "", location=location or "",
                                 calendar=calendar)

        payload = _guard(run)
        return _result(
            f"Встреча «{summary.strip()}» записана в {payload.get('calendar') or 'календарь'}.",
            payload)

    return server


def _pick_account(clients, name):
    if not clients:
        raise ToolError("календарь не настроен")
    if not name:
        return clients[0]
    needle = name.strip().lower()
    for client in clients:
        if needle in (client.account.name, client.account.address):
            return client
    known = ", ".join(client.account.name for client in clients)
    raise ToolError(f"календаря {name} нет. Есть: {known}")


def _when(event):
    if event.all_day:
        return event.start.strftime("%d.%m") + ", весь день"
    return event.start.strftime("%d.%m %H:%M")


def _notes_server(notes):
    server = Server(
        "desk-notes", "1.0.0",
        "Заметки Obsidian владельца. Писать можно только внутрь vault. "
        "Перед ответом «я этого не помню» сначала notes_search.")

    def api():
        if notes is not None:
            return notes
        from desk import cli
        return cli

    @server.tool(
        "notes_search",
        "Найти заметку в vault по фразе из текста или имени файла.",
        {"type": "object",
         "properties": {
             "query": {"type": "string"},
             "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
         },
         "required": ["query"], "additionalProperties": False},
        title="Найти заметку", annotations=LOCAL_READ)
    def search(query, limit=20):
        payload = api().search_notes(query, limit)
        if not payload["hits"]:
            text = f"В заметках нет «{query}»."
        else:
            text = "Нашёл:\n" + "\n".join(f"— {hit}" for hit in payload["hits"])
        return _result(text, payload)

    @server.tool(
        "notes_write",
        "Записать заметку во vault. По умолчанию в 00 Inbox.",
        {"type": "object",
         "properties": {
             "title": {"type": "string"},
             "body": {"type": "string"},
             "folder": {"type": "string", "default": "00 Inbox"},
         },
         "required": ["title", "body"], "additionalProperties": False},
        title="Записать заметку", annotations=LOCAL_WRITE)
    def write(title, body, folder="00 Inbox"):
        try:
            payload = api().write_note(title, body, folder)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        return _result(f"Заметка «{payload['title']}» записана.", payload)

    return server


def _telegram_server(telegram):
    server = Server(
        "desk-telegram", "1.0.0",
        "Непрочитанное личного Telegram владельца. Чужие чаты не забирай и не "
        "включай сбор входящих. Отправку от имени владельца не делай, пока он "
        "не сказал, кому и какой текст.")

    @server.tool(
        "telegram_unread",
        "Непрочитанные диалоги и каналы личного аккаунта. Текст чужих чатов не собирает.",
        no_arguments(), title="Непрочитанное Telegram", annotations=LOCAL_READ)
    def unread():
        if telegram is not None:
            payload = telegram()
        else:
            payload = _local_get(os.environ.get("TG_USER_URL", "http://127.0.0.1:8810"),
                                 "/unread")
        return _result(_brief("Непрочитанное", payload), payload if isinstance(payload, dict)
                       else {"unread": payload})

    return server


def _voice_server(voice):
    server = Server(
        "desk-voice", "1.0.0",
        "Голос Edge, ru-RU-DmitryNeural. Ключ не нужен. "
        "В Telegram голосовые ответы включает сам Hermes. Этот инструмент — "
        "когда владелец просит сохранить запись.")

    @server.tool(
        "voice_speak",
        "Озвучить короткую фразу через Edge TTS и вернуть путь к файлу.",
        {"type": "object",
         "properties": {"text": {"type": "string"}},
         "required": ["text"], "additionalProperties": False},
        title="Сказать вслух", annotations=LOCAL_WRITE)
    def speak(text):
        if voice is not None:
            payload = voice(text)
        else:
            from desk.cli import speak as edge_speak
            payload = edge_speak(text)
        if not payload.get("ok", True) and payload.get("error"):
            raise ToolError(payload["error"])
        return _result("Фраза озвучена.", payload)

    return server


def _local_get(base, path):
    """Локальный сервис напрямую, без HTTP-прокси.

    Клиент MCP запускает процесс с урезанным окружением, и NO_PROXY туда
    может не доехать. Пустой ProxyHandler не смотрит в окружение вообще.
    """
    host = urllib.parse.urlparse(base).hostname
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ToolError("telegram: сервис только на этой машине")
    url = base.rstrip("/") + path
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=15) as response:
            return json.loads(response.read().decode())
    except Exception as exc:  # noqa: BLE001 — модели нужна причина, не трассировка
        raise ToolError(f"telegram: {type(exc).__name__}: {exc}") from exc


def _brief(title, payload):
    if isinstance(payload, dict) and payload.get("error"):
        return f"{title}: {payload['error']}"
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) > 1200:
        text = text[:1200] + "…"
    return f"{title}: {text}"
