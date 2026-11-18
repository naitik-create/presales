"""Storage abstraction (§16). Only the local filesystem backend is implemented; business code uses put/get/delete."""
import hashlib
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.core import StoredFile

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".txt", ".md", ".zip", ".png", ".jpg", ".jpeg"}


class StorageBackend(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def path(self, key: str) -> Path: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("Invalid storage key")
        return p

    def put(self, key: str, data: bytes) -> None:
        p = self._p(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._p(key).read_bytes()

    def path(self, key: str) -> Path:
        return self._p(key)

    def delete(self, key: str) -> None:
        self._p(key).unlink(missing_ok=True)


_backend: StorageBackend | None = None


def backend() -> StorageBackend:
    global _backend
    if _backend is None:
        s = get_settings()
        if s.STORAGE_BACKEND != "local":
            raise SystemExit(f"Storage backend '{s.STORAGE_BACKEND}' is not implemented yet; use 'local'.")
        _backend = LocalStorage(s.storage_path)
    return _backend


def safe_name(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return name[:200] or "file"


def validate_upload(name: str, size: int, allowed: set[str] | None = None) -> None:
    ext = Path(name).suffix.lower()
    if ext not in (allowed or ALLOWED_EXTENSIONS):
        raise ValueError(f"File type {ext or '(none)'} is not supported")
    if size > get_settings().MAX_UPLOAD_MB * 1024 * 1024:
        raise ValueError(f"File is larger than {get_settings().MAX_UPLOAD_MB} MB")
    if size == 0:
        raise ValueError("File is empty")


def save_file(db: Session, data: bytes, original_name: str, area: str, user_id: int | None,
              content_type: str = "application/octet-stream", allowed: set[str] | None = None) -> StoredFile:
    validate_upload(original_name, len(data), allowed)
    name = safe_name(original_name)
    key = f"{area}/{datetime.now():%Y/%m}/{uuid.uuid4().hex}_{name}"
    backend().put(key, data)
    f = StoredFile(storage_key=key, original_name=name, content_type=content_type, size=len(data),
                   sha256=hashlib.sha256(data).hexdigest(), area=area, uploaded_by=user_id)
    db.add(f)
    db.flush()
    return f


def read_file(f: StoredFile) -> bytes:
    return backend().get(f.storage_key)


def file_path(f: StoredFile) -> Path:
    return backend().path(f.storage_key)
