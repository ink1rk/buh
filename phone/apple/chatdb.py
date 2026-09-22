#!/usr/bin/env python3
"""Переписка из базы Messages.

iCloud кладёт на Mac ту же переписку, что и на iPhone: iMessage, а если
включена пересылка SMS — то и её. Лежит она в `~/Library/Messages/chat.db`,
обычным SQLite. Это единственный способ получать сообщения без участия
человека: iOS не отдаёт их ни ярлыку, ни приложению.

Читается только форма разговора: кто, когда, в какую сторону, сколько
знаков. Текст не покидает Mac — для «кто ждёт ответа» он не нужен, а
хранить чужую переписку на сервере не стоит вообще никогда.
"""
import os
import shutil
import sqlite3
import tempfile

APPLE_EPOCH = 978307200          # 1 января 2001 года, начало времён у Apple


def default_path():
    return os.path.expanduser("~/Library/Messages/chat.db")


def _seconds(value):
    """Дата сообщения: наносекунды с 2001 года, а в старых базах — секунды."""
    if not value:
        return 0.0
    value = float(value)
    if value > 1e11:
        value /= 1e9
    return value + APPLE_EPOCH


def text_length(text, blob):
    """Сколько знаков в сообщении, не сохраняя самих знаков.

    С macOS Ventura текст лежит не в колонке `text`, а внутри `attributedBody`
    — архиве NSAttributedString. Полноценно разбирать его незачем: нам нужна
    только длина, поэтому достаём строку грубо и считаем символы.
    """
    if text:
        return len(text)
    if not blob:
        return 0
    marker = blob.find(b"NSString")
    if marker == -1:
        return 0
    body = blob[marker + 8:]
    # Между именем класса и строкой лежит несколько служебных байтов; сколько
    # именно — зависит от версии macOS. Берём первое смещение, за которым
    # длина сходится с тем, сколько байтов осталось.
    for skip in (5, 4, 6, 3, 2, 1, 0):
        chunk = body[skip:]
        if not chunk:
            continue
        if chunk[0] == 0x81:
            length, data = int.from_bytes(chunk[1:3], "little"), chunk[3:]
        else:
            length, data = chunk[0], chunk[1:]
        if 0 < length <= len(data):
            return len(data[:length].decode("utf-8", "replace"))
    return 0


def open_db(path, copy=True):
    """Копия базы, а не сама база: Messages держит её открытой и пишет в неё."""
    path = path or default_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f"нет базы переписки: {path}")
    if not copy:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True), None
    temp = tempfile.mkdtemp(prefix="phone-chatdb-")
    copied = os.path.join(temp, "chat.db")
    shutil.copy2(path, copied)
    for suffix in ("-wal", "-shm"):
        if os.path.exists(path + suffix):
            shutil.copy2(path + suffix, copied + suffix)
    return sqlite3.connect(copied), temp


QUERY = """
SELECT m.ROWID          AS rowid,
       m.guid           AS guid,
       m.date           AS date,
       m.is_from_me     AS is_from_me,
       m.service        AS service,
       m.cache_has_attachments AS attachments,
       m.text           AS text,
       m.attributedBody AS body,
       h.id             AS handle,
       c.display_name   AS chat_name,
       c.room_name      AS room
  FROM message m
  LEFT JOIN handle h ON h.ROWID = m.handle_id
  LEFT JOIN chat_message_join j ON j.message_id = m.ROWID
  LEFT JOIN chat c ON c.ROWID = j.chat_id
 WHERE m.ROWID > ?
 ORDER BY m.ROWID
 LIMIT ?
"""


def read_messages(path=None, after_rowid=0, limit=5000, groups=False):
    """Сообщения после указанной строки — в формате, который ждёт мост.

    Возвращает и сами сообщения, и самую дальнюю прочитанную строку. Иначе
    групповые чаты, которые мы пропускаем, оставляли бы курсор на месте,
    и агент крутил бы одни и те же пять тысяч строк вечно.
    """
    conn, temp = open_db(path)
    try:
        conn.row_factory = sqlite3.Row
        out = []
        last = after_rowid
        for row in conn.execute(QUERY, (after_rowid, limit)):
            last = max(last, row["rowid"])
            if row["room"] and not groups:
                # Групповой чат — это не «мне не ответили», это фон.
                continue
            out.append({
                "external_id": row["guid"] or f"chatdb:{row['rowid']}",
                "app": "sms" if (row["service"] or "").upper() == "SMS" else "imessage",
                "direction": "outgoing" if row["is_from_me"] else "incoming",
                "peer_number": row["handle"] or "",
                "peer_name": row["chat_name"] or "",
                "chars": text_length(row["text"], row["body"]),
                "attachments": int(row["attachments"] or 0),
                "ts": _seconds(row["date"]),
                "rowid": row["rowid"],
            })
        return {"items": out, "last_rowid": last}
    finally:
        conn.close()
        if temp:
            shutil.rmtree(temp, ignore_errors=True)
