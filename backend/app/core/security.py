"""Security helpers: encryption, export integrity."""

from __future__ import annotations

import base64
import hashlib
import hmac
from pathlib import Path

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _derive_fernet(key: str) -> Fernet:
    digest = hashlib.sha256(key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_text(plaintext: str) -> str:
    settings = get_settings()
    if not settings.encryption_key:
        return plaintext
    return _derive_fernet(settings.encryption_key).encrypt(plaintext.encode()).decode()


def decrypt_text(ciphertext: str) -> str:
    settings = get_settings()
    if not settings.encryption_key:
        return ciphertext
    return _derive_fernet(settings.encryption_key).decrypt(ciphertext.encode()).decode()


def file_checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sign_payload(payload: bytes) -> str:
    settings = get_settings()
    return hmac.new(settings.secret_key.encode(), payload, hashlib.sha256).hexdigest()
