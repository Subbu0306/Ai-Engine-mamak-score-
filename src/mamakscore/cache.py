# Optional content-addressed SQLite replay cache.
from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from .contracts import AssessmentDraft


class ReplayCache:
    def __init__(self, path: Path, enabled: bool = False) -> None:
        self.path = Path(path)
        self.enabled = enabled
        if enabled:
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS replay (key TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)"
            )

    @staticmethod
    def make_key(*parts: str) -> str:
        digest = hashlib.sha256()
        for part in parts:
            encoded = part.encode()
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
        return digest.hexdigest()

    def get(self, key: str) -> AssessmentDraft | None:
        if not self.enabled:
            return None
        with self._connect() as db:
            row = db.execute("SELECT payload FROM replay WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        try:
            return AssessmentDraft.model_validate_json(row[0])
        except (ValidationError, ValueError):
            with self._connect() as db:
                db.execute("DELETE FROM replay WHERE key=?", (key,))
            return None

    def put(self, key: str, value: AssessmentDraft) -> None:
        if self.enabled:
            self._put_raw(key, value.model_dump_json())

    def _put_raw(self, key: str, payload: str) -> None:
        if not self.enabled:
            return
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO replay(key,payload,created_at) VALUES(?,?,?)",
                (key, payload, datetime.now(UTC).isoformat()),
            )
