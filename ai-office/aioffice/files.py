"""Local file and voice storage. Audio is not sent to a paid transcriber."""
import hashlib

MAX_BYTES = 2_000_000
VOICE_REPLY = 'Голосовое сохранено локально. Аудио не отправляется во внешний сервис распознавания.'
ALLOW = {
    'document': {'application/pdf', 'text/plain', 'text/markdown', 'application/json', 'image/png', 'image/jpeg'},
    'voice': {'audio/ogg', 'audio/opus'},
    'audio': {'audio/mpeg', 'audio/ogg', 'audio/mp4', 'audio/wav', 'audio/x-wav'},
    'photo': {'image/jpeg', 'image/png'},
}


def file_allowed(kind, mime, size):
    return isinstance(size, int) and 0 < size <= MAX_BYTES and mime in ALLOW.get(kind, ())


def accept_file(kind, mime, size, data):
    if not isinstance(data, (bytes, bytearray)) or len(data) != size or not file_allowed(kind, mime, size):
        raise ValueError('Файл отклонён: тип или размер вне allowlist.')
    return hashlib.sha256(data).hexdigest()


def describe_incoming(message):
    if not isinstance(message, dict):
        return None
    if message.get('voice'):
        item = message['voice']
        return 'voice', item.get('mime_type') or 'audio/ogg', item.get('file_size'), item.get('file_id'), item.get('file_unique_id')
    if message.get('audio'):
        item = message['audio']
        return 'audio', item.get('mime_type') or '', item.get('file_size'), item.get('file_id'), item.get('file_unique_id')
    if message.get('document'):
        item = message['document']
        return 'document', item.get('mime_type') or '', item.get('file_size'), item.get('file_id'), item.get('file_unique_id')
    photos = message.get('photo')
    if isinstance(photos, list) and photos:
        item = max(photos, key=lambda row: row.get('file_size') or 0)
        return 'photo', 'image/jpeg', item.get('file_size'), item.get('file_id'), item.get('file_unique_id')
    return None


def local_runner(command, data):
    """Run one local executable. The command is not a shell line and has no network client."""
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile() as handle:
        handle.write(data)
        handle.flush()
        completed = subprocess.run([command, handle.name], check=False, capture_output=True, timeout=20)
    if completed.returncode != 0:
        return None
    text = completed.stdout.decode('utf-8', errors='replace').strip()
    return text[:4000] or None


def transcribe(kind, data, command, runner):
    """runner is not called unless a local binary is configured. No network client."""
    if kind not in ('voice', 'audio') or not command:
        return None
    return runner(command, data)
