from __future__ import annotations

import hashlib
import io
import os
import subprocess
import tarfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


def _key(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_bytes(data: bytes, passphrase: str) -> bytes:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key(passphrase, salt)).encrypt(nonce, data, None)
    return b"TMN1" + salt + nonce + ciphertext


def decrypt_bytes(blob: bytes, passphrase: str) -> bytes:
    if not blob.startswith(b"TMN1"):
        raise ValueError("unknown backup header")
    salt, nonce, ciphertext = blob[4:20], blob[20:32], blob[32:]
    return AESGCM(_key(passphrase, salt)).decrypt(nonce, ciphertext, None)


def pg_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1).replace("postgresql+psycopg2://", "postgresql://", 1)


def dump_database(database_url: str) -> bytes:
    return subprocess.check_output(
        ["pg_dump", "--format=custom", "--no-owner", "--dbname", pg_url(database_url)],
    )


def create_encrypted_backup(database_url: str, dest: Path, passphrase: str) -> dict:
    raw = dump_database(database_url)
    digest = hashlib.sha256(raw).hexdigest()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(encrypt_bytes(raw, passphrase))
    dest.with_suffix(dest.suffix + ".sha256").write_text(digest + "\n", encoding="utf-8")
    os.chmod(dest, 0o600)
    return {"sha256": digest, "bytes": dest.stat().st_size}


def _media_tar(media_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        files = sorted(path for path in media_dir.rglob("*") if path.is_file())
        for path in files:
            archive.add(path, arcname=path.relative_to(media_dir).as_posix())
    return buffer.getvalue()


def create_media_backup(media_dir: Path, dest: Path, passphrase: str) -> dict:
    raw = _media_tar(media_dir)
    digest = hashlib.sha256(raw).hexdigest()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(encrypt_bytes(raw, passphrase))
    dest.with_suffix(dest.suffix + ".sha256").write_text(digest + "\n", encoding="utf-8")
    os.chmod(dest, 0o600)
    return {"sha256": digest, "bytes": dest.stat().st_size}


def restore_media_backup(source: Path, media_dir: Path, passphrase: str, expected_sha256: str) -> None:
    raw = decrypt_bytes(source.read_bytes(), passphrase)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError("checksum mismatch")
    media_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r") as archive:
        archive.extractall(media_dir, filter="data")


def restore_encrypted_backup(source: Path, database_url: str, passphrase: str, expected_sha256: str) -> None:
    raw = decrypt_bytes(source.read_bytes(), passphrase)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError("checksum mismatch")
    subprocess.run(
        ["pg_restore", "--no-owner", "--clean", "--if-exists", "--dbname", pg_url(database_url)],
        input=raw,
        check=True,
    )
