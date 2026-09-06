"""In-memory хранилище задач и загруженных файлов (MVP без БД, A10)."""
from __future__ import annotations

import threading
import uuid


class JobStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._files: dict[str, bytes] = {}
        self._jobs: dict[str, dict] = {}

    def add_file(self, content: bytes) -> str:
        fid = uuid.uuid4().hex
        with self._lock:
            self._files[fid] = content
        return fid

    def get_file(self, fid: str) -> bytes | None:
        with self._lock:
            return self._files.get(fid)

    def create_job(self) -> str:
        jid = uuid.uuid4().hex
        with self._lock:
            self._jobs[jid] = {"status": "PENDING"}
        return jid

    def update(self, jid: str, **kwargs) -> None:
        with self._lock:
            self._jobs[jid].update(kwargs)

    def get(self, jid: str) -> dict | None:
        with self._lock:
            return self._jobs.get(jid)
