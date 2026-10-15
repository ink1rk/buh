"""Google and Yandex calendars. Writes have no attendees and no invented credentials."""
import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

PROVIDERS = ('google', 'yandex')
LABELS = {'google': 'Google', 'yandex': 'Яндекс'}


class CalendarError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def credential_flags(env):
    google = bool(env.get('GOOGLE_CALENDAR_TOKEN') or (
        env.get('GOOGLE_CLIENT_ID') and env.get('GOOGLE_CLIENT_SECRET') and env.get('GOOGLE_REFRESH_TOKEN')))
    yandex = bool(env.get('YANDEX_CALDAV_USER') and env.get('YANDEX_CALDAV_PASSWORD'))
    return {'google': google, 'yandex': yandex}


def status_lines(timezone, providers, env):
    flags = credential_flags(env)
    zone_note = 'UTC+3' if timezone == 'Europe/Moscow' else 'IANA'
    lines = [f'Часовой пояс: {timezone} ({zone_note}).', 'Календари: ' + ', '.join(LABELS[item] for item in providers) + '.']
    for name in providers:
        if flags[name]:
            lines.append(f'{LABELS[name]}: данные заданы. Запись только после кнопки «Разрешить», без участников.')
        elif name == 'google':
            lines.append('Google: выбран, данные не заданы. Нужен GOOGLE_CALENDAR_TOKEN или тройка GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN.')
        else:
            lines.append('Яндекс: выбран, данные не заданы. Нужны YANDEX_CALDAV_USER и YANDEX_CALDAV_PASSWORD (пароль приложения).')
    lines.append('Создание: /calendar create google 2030-01-01T12:00 текст')
    lines.append('Создание: /calendar create yandex 2030-01-01T12:00 текст')
    return '\n'.join(lines)


def google_body(title, starts, timezone, uid):
    start = datetime.fromisoformat(starts)
    end = start + timedelta(hours=1)
    return {
        'summary': title[:500],
        'iCalUID': uid + '@ai-office.local',
        'start': {'dateTime': start.strftime('%Y-%m-%dT%H:%M:%S'), 'timeZone': timezone},
        'end': {'dateTime': end.strftime('%Y-%m-%dT%H:%M:%S'), 'timeZone': timezone},
    }


def _ics_text(value):
    return value.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '').replace(',', '\\,').replace(';', '\\;')


def yandex_ics(title, starts, timezone, uid):
    start = datetime.fromisoformat(starts)
    end = start + timedelta(hours=1)
    stamp = datetime.now().strftime('%Y%m%dT%H%M%SZ')
    return (
        'BEGIN:VCALENDAR\r\n'
        'VERSION:2.0\r\n'
        'PRODID:-//AI Office//RU\r\n'
        'BEGIN:VTIMEZONE\r\n'
        f'TZID:{timezone}\r\n'
        'BEGIN:STANDARD\r\n'
        'DTSTART:19700101T000000\r\n'
        'TZOFFSETFROM:+0300\r\n'
        'TZOFFSETTO:+0300\r\n'
        'TZNAME:MSK\r\n'
        'END:STANDARD\r\n'
        'END:VTIMEZONE\r\n'
        'BEGIN:VEVENT\r\n'
        f'UID:{uid}@ai-office.local\r\n'
        f'DTSTAMP:{stamp}\r\n'
        f'DTSTART;TZID={timezone}:{start.strftime("%Y%m%dT%H%M%S")}\r\n'
        f'DTEND;TZID={timezone}:{end.strftime("%Y%m%dT%H%M%S")}\r\n'
        f'SUMMARY:{_ics_text(title[:500])}\r\n'
        'END:VEVENT\r\n'
        'END:VCALENDAR\r\n'
    )


def yandex_collection(env):
    href = (env.get('YANDEX_CALDAV_HREF') or '').strip()
    if href:
        parsed = urllib.parse.urlparse(href)
        host = parsed.hostname or ''
        if parsed.username or parsed.password or parsed.scheme != 'https' or not (host == 'caldav.yandex.ru' or host.endswith('.yandex.ru')):
            raise CalendarError('yandex_href')
        return href.rstrip('/')
    user = env.get('YANDEX_CALDAV_USER') or ''
    if not user or any(char in user for char in ' /\\?#\r\n'):
        raise CalendarError('yandex_user')
    return 'https://caldav.yandex.ru/calendars/' + urllib.parse.quote(user, safe='@') + '/events-default'


def _open(opener, request):
    try:
        return opener(request, timeout=20)
    except urllib.error.HTTPError as exc:
        raise CalendarError('http_' + str(exc.code)) from None
    except (OSError, ValueError, json.JSONDecodeError):
        raise CalendarError('transport') from None


def _google_token(env, opener):
    if env.get('GOOGLE_CLIENT_ID') and env.get('GOOGLE_CLIENT_SECRET') and env.get('GOOGLE_REFRESH_TOKEN'):
        form = urllib.parse.urlencode({
            'client_id': env['GOOGLE_CLIENT_ID'],
            'client_secret': env['GOOGLE_CLIENT_SECRET'],
            'refresh_token': env['GOOGLE_REFRESH_TOKEN'],
            'grant_type': 'refresh_token',
        }).encode()
        request = urllib.request.Request('https://oauth2.googleapis.com/token', data=form, method='POST')
        with _open(opener, request) as response:
            body = json.load(response)
        token = body.get('access_token') if isinstance(body, dict) else None
        if not token:
            raise CalendarError('google_token')
        return token
    token = env.get('GOOGLE_CALENDAR_TOKEN') or ''
    if not token:
        raise CalendarError('google_credentials')
    return token


def deliver_event(provider, title, starts, timezone, uid, env, opener):
    """One calendar write. The caller already consumed the approval."""
    if provider not in PROVIDERS:
        raise CalendarError('provider')
    if provider == 'google':
        token = _google_token(env, opener)
        ical = uid + '@ai-office.local'
        query = urllib.parse.urlencode({'iCalUID': ical})
        lookup = urllib.request.Request(
            'https://www.googleapis.com/calendar/v3/calendars/primary/events?' + query,
            headers={'Authorization': 'Bearer ' + token},
        )
        with _open(opener, lookup) as response:
            found = json.load(response)
        items = found.get('items') if isinstance(found, dict) else None
        if items:
            return {'id': items[0].get('id') or ical, 'created': False}
        payload = google_body(title, starts, timezone, uid)
        if 'attendees' in payload:
            raise CalendarError('attendees')
        request = urllib.request.Request(
            'https://www.googleapis.com/calendar/v3/calendars/primary/events',
            data=json.dumps(payload).encode(),
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
            method='POST',
        )
        with _open(opener, request) as response:
            body = json.load(response)
        return {'id': (body or {}).get('id') or ical, 'created': True}
    user = env.get('YANDEX_CALDAV_USER') or ''
    password = env.get('YANDEX_CALDAV_PASSWORD') or ''
    if not user or not password:
        raise CalendarError('yandex_credentials')
    basic = base64.b64encode((user + ':' + password).encode()).decode()
    url = yandex_collection(env) + '/' + uid + '.ics'
    request = urllib.request.Request(
        url, data=yandex_ics(title, starts, timezone, uid).encode(), method='PUT',
        headers={'Authorization': 'Basic ' + basic, 'Content-Type': 'text/calendar; charset=utf-8'},
    )
    if '@' in (urllib.parse.urlparse(url).netloc):
        raise CalendarError('yandex_href')
    with _open(opener, request):
        return {'id': uid, 'created': True}
