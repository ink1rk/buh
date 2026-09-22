"""Объектное хранилище файлов: MinIO/S3 с включённым версионированием.

Для разработки и тестов доступен локальный бэкенд, повторяющий тот же интерфейс.
"""

from __future__ import annotations

import hashlib
import shutil
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

from itms.core.config import settings


class Storage(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def presigned_url(self, key: str, filename: str, expires_in: int = 300) -> str | None: ...

    def open_stream(self, key: str) -> BinaryIO:  # pragma: no cover - используется редко
        import io

        return io.BytesIO(self.get(key))


class LocalStorage(Storage):
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._path(key).write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def presigned_url(self, key: str, filename: str, expires_in: int = 300) -> str | None:
        return None

    def clear(self) -> None:  # pragma: no cover - для тестов
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)


class S3Storage(Storage):
    def __init__(self) -> None:
        import boto3
        from botocore.client import Config

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            use_ssl=settings.s3_use_ssl,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def ensure_bucket(self) -> None:
        """Создаёт бакет и включает версионирование объектов."""
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)
        self.client.put_bucket_versioning(
            Bucket=self.bucket, VersioningConfiguration={"Status": "Enabled"}
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def presigned_url(self, key: str, filename: str, expires_in: int = 300) -> str | None:
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentDisposition": (
                    f"attachment; filename*=UTF-8''{quote(filename)}"
                ),
            },
            ExpiresIn=expires_in,
        )


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = (
            LocalStorage(settings.local_storage_path)
            if settings.storage_backend == "local"
            else S3Storage()
        )
    return _storage


def set_storage(storage: Storage | None) -> None:  # pragma: no cover - для тестов
    global _storage
    _storage = storage


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_key(prefix: str, sha256: str, filename: str) -> str:
    suffix = Path(filename).suffix.lower()[:16]
    today = datetime.now().strftime("%Y/%m")
    return f"{prefix}/{today}/{sha256[:2]}/{sha256}{suffix}"
