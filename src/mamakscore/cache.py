"""SQLite-backed deterministic replay cache for evaluation requests."""

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Optional
from mamakscore.contracts import AssessmentDraft


class ReplayCache:
    """Caches AssessmentDraft objects keyed by SHA-256 of input parameters."""

    def __init__(self, db_path: Path, enabled: bool = True):
        self.db_path = db_path
        self.enabled = enabled
        if self.enabled:
            self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assessment_cache (
                    cache_key TEXT PRIMARY KEY,
                    draft_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    @staticmethod
    def compute_cache_key(
        input_digest: str,
        model_id: str,
        rubric_digest: str,
        prompt_digest: str,
    ) -> str:
        """Computes deterministic key across all input dimensions."""
        composite = f"{input_digest}:{model_id}:{rubric_digest}:{prompt_digest}"
        return hashlib.sha256(composite.encode("utf-8")).hexdigest()
    
    @staticmethod
    def make_key(*args: Any) -> str:
        """Computes a deterministic hash across arbitrary input parameters."""
        composite = ":".join(str(a) for a in args)
        return hashlib.sha256(composite.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> Optional[AssessmentDraft]:
        if not self.enabled or not self.db_path.exists():
            return None
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT draft_json FROM assessment_cache WHERE cache_key = ?",
                    (cache_key,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                data = json.loads(row[0])
                return AssessmentDraft.model_validate(data)
        except Exception:
            # Evict on malformed payload or read failure
            self.evict(cache_key)
            return None

    def put(self, cache_key: str, draft: AssessmentDraft) -> None:
        if not self.enabled:
            return
        self._init_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO assessment_cache (cache_key, draft_json) VALUES (?, ?)",
                (cache_key, draft.model_dump_json()),
            )
            conn.commit()
    def _put_raw(self, cache_key: str, raw_text: str) -> None:
        """Stores a raw string directly to test cache eviction and corruption handling."""
        if not self.enabled:
            return
        self._init_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO assessment_cache (cache_key, draft_json) VALUES (?, ?)",
                (cache_key, raw_text),
            )
            conn.commit()

    def evict(self, cache_key: str) -> None:
        if not self.enabled or not self.db_path.exists():
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM assessment_cache WHERE cache_key = ?", (cache_key,))
            conn.commit()