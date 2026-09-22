#!/usr/bin/env python3
"""Резервная копия iPhone: те же базы, если Mac с iCloud нет.

Finder (или раньше iTunes) кладёт локальную копию в
`~/Library/Application Support/MobileSync/Backup/<UDID>/`. Внутри — не папки
приложений, а файлы с именами-хешами и каталог `Manifest.db`, который говорит,
какой хеш чем был. Оттуда достаются ровно две вещи, до которых iOS иначе
не дотянуться: `sms.db` (переписка) и `CallHistory.storedata` (журнал звонков).

Здоровье из копии не читаем. Apple держит его в отдельном зашифрованном
хранилище, и единственный честный полный снимок — выгрузка из приложения
«Здоровье». Зато звонки и сообщения из незашифрованной копии — те же, что
на телефоне, без ярлыков и без участия человека.

Зашифрованную копию не пытаемся открыть: без пароля это мусор, а с паролем
это уже другая программа.
"""
import os
import plistlib
import shutil
import sqlite3
import tempfile

BACKUP_ROOT = os.path.expanduser(
    "~/Library/Application Support/MobileSync/Backup")

# domain, relativePath — как Apple называет файл внутри копии.
SOURCES = {
    "messages": ("HomeDomain", "Library/SMS/sms.db"),
    "calls": ("HomeDomain", "Library/CallHistoryDB/CallHistory.storedata"),
}


class EncryptedBackup(RuntimeError):
    """Копия закрыта паролем — содержимое файлов без него не прочитать."""


class NoBackup(FileNotFoundError):
    """Локальной копии нет: либо её никогда не делали, либо это не Mac."""


def _plist(path):
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as fh:
        try:
            return plistlib.load(fh)
        except Exception:
            return {}


def _ts(value):
    if value is None:
        return 0
    if hasattr(value, "timestamp"):
        return value.timestamp()
    return 0


def describe(path):
    info = _plist(os.path.join(path, "Info.plist"))
    manifest = _plist(os.path.join(path, "Manifest.plist"))
    status = _plist(os.path.join(path, "Status.plist"))
    date = (_ts(status.get("Date")) or _ts(info.get("Last Backup Date"))
            or _ts(manifest.get("Date")) or os.path.getmtime(path))
    return {
        "path": path,
        "udid": os.path.basename(path.rstrip("/")),
        "name": info.get("Device Name") or info.get("Display Name") or "",
        "model": info.get("Product Type") or "",
        "os_version": info.get("Product Version") or "",
        "date": date,
        "encrypted": bool(manifest.get("IsEncrypted")),
        "finished": status.get("SnapshotState") in (None, "finished"),
    }


def find_backups(root=None):
    root = root or BACKUP_ROOT
    if not os.path.isdir(root):
        return []
    found = []
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        if not os.path.exists(os.path.join(path, "Manifest.db")):
            continue
        found.append(describe(path))
    return sorted(found, key=lambda item: item["date"], reverse=True)


def latest(root=None, allow_encrypted=False):
    backups = find_backups(root)
    if not allow_encrypted:
        backups = [b for b in backups if not b["encrypted"]]
    if not backups:
        where = root or BACKUP_ROOT
        raise NoBackup(
            f"локальной резервной копии iPhone нет в {where}. "
            "На Mac: Finder → iPhone → «Создать резервную копию», без пароля. "
            "Либо включите «Сообщения в iCloud» — тогда chat.db появится сам.")
    return backups[0]


def file_path(backup_dir, file_id):
    """iOS 10+ кладёт файл в подпапку из первых двух символов хеша."""
    nested = os.path.join(backup_dir, file_id[:2], file_id)
    if os.path.exists(nested):
        return nested
    flat = os.path.join(backup_dir, file_id)
    if os.path.exists(flat):
        return flat
    return None


def lookup(backup_dir, domain, relative):
    db = os.path.join(backup_dir, "Manifest.db")
    if not os.path.exists(db):
        raise FileNotFoundError(f"нет Manifest.db в {backup_dir}")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT fileID FROM Files WHERE domain=? AND relativePath=?",
            (domain, relative)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def extract_file(backup_dir, domain, relative, dest):
    file_id = lookup(backup_dir, domain, relative)
    if not file_id:
        return None
    source = file_path(backup_dir, file_id)
    if not source:
        return None
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    shutil.copy2(source, dest)
    return dest


class Extracted:
    def __init__(self, root, files, meta):
        self.root = root
        self.files = files
        self.meta = meta

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def extract(path=None, root=None):
    """Достать переписку и журнал звонков из копии во временную папку."""
    if path is None:
        meta = latest(root)
        path = meta["path"]
    else:
        meta = describe(path)
    if meta["encrypted"]:
        raise EncryptedBackup(
            f"копия «{meta['name'] or meta['udid']}» зашифрована паролем. "
            "Снимите пароль в Finder или используйте выгрузку Здоровья "
            "и «Сообщения в iCloud» на Mac — они пароля копии не требуют.")
    temp = tempfile.mkdtemp(prefix="phone-backup-")
    files = {}
    for kind, (domain, relative) in SOURCES.items():
        dest = os.path.join(temp, os.path.basename(relative))
        if extract_file(path, domain, relative, dest):
            files[kind] = dest
            # WAL, если его успели включить в копию — иначе база отстанет.
            for suffix in ("-wal", "-shm"):
                extract_file(path, domain, relative + suffix, dest + suffix)
    if not files:
        shutil.rmtree(temp, ignore_errors=True)
        raise FileNotFoundError(
            "в копии нет ни sms.db, ни журнала звонков — "
            "телефон, с которого её сняли, их не отдавал.")
    return Extracted(temp, files, meta)
