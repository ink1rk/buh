import hashlib
import json
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def private_owner(update, owners):
    """Groups and forwarded callbacks never expand the owner allowlist."""
    message = update.get('message')
    if not isinstance(message, dict):
        return None
    user = message.get('from', {})
    chat = message.get('chat', {})
    uid = user.get('id')
    if uid not in owners or user.get('is_bot') or chat.get('type') != 'private' or chat.get('id') != uid:
        return None
    return uid


def callback_actor(update, owners):
    """Inline approvals are accepted only from the owner in a private chat."""
    query = update.get('callback_query')
    if not isinstance(query, dict):
        return None
    user = query.get('from') or {}
    message = query.get('message') or {}
    chat = message.get('chat') or {}
    uid = user.get('id')
    data = query.get('data') or ''
    if uid not in owners or user.get('is_bot') or chat.get('type') != 'private' or chat.get('id') != uid:
        return None
    if len(data) > 64 or not (data.startswith('a:') or data.startswith('r:')):
        return None
    try:
        uuid.UUID(data[2:])
    except ValueError:
        return None
    return uid


def parse_due(value: str, timezone: str, now=None):
    if not timezone:
        raise ValueError('Сначала подтвердите часовой пояс владельца.')
    due = datetime.fromisoformat(value)
    if due.tzinfo is None:
        zone = ZoneInfo(timezone)
        a, b = due.replace(tzinfo=zone, fold=0), due.replace(tzinfo=zone, fold=1)
        if a.utcoffset() != b.utcoffset():
            raise ValueError('Неоднозначное или отсутствующее время DST: укажите UTC offset.')
        due = a
        if due.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != datetime.fromisoformat(value):
            raise ValueError('Указанное локальное время не существует.')
    due = due.astimezone(UTC)
    if due <= (now or datetime.now(UTC)):
        raise ValueError('Время напоминания должно быть в будущем.')
    return due


def payload_hash(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def external_write_allowed(*, capability=False, approval=None, owner=None, payload=None, now=None):
    """No configured calendar/email/payment writer exists in this release."""
    if not capability or not approval:
        return False
    now = now or datetime.now(UTC)
    return bool(approval['owner_id'] == owner and approval['expires_at'] > now
                and approval['consumed_at'] is None and approval['payload_hash'] == payload_hash(payload))

