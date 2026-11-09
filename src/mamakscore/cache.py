"""SQLite-backed deterministic replay cache for LLM assessments."""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional


class SQLiteReplayCache:
    """Stores and retrieves LLM completion responses by hash digest."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = Path(".cache")
            base_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(base_dir / "replay_cache.sqlite")
        else:
            self.db_path = db_path
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prompt_cache (
                    prompt_digest TEXT PRIMARY KEY,
                    response_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def get(self, prompt_digest: str) -> Optional[Dict[str, Any]]:
        """Retrieves cached JSON dict if present, else None."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT response_json FROM prompt_cache WHERE prompt_digest = ?",
                (prompt_digest,),
            )
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row[0])
                except Exception:
                    return None
        return None

    def set(self, prompt_digest: str, response_payload: Dict[str, Any]) -> None:
        """Saves response dict into the cache keyed by prompt digest."""
        payload_str = json.dumps(response_payload)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO prompt_cache (prompt_digest, response_json)
                VALUES (?, ?)
                ON CONFLICT(prompt_digest) DO UPDATE SET response_json = excluded.response_json
                """,
                (prompt_digest, payload_str),
            )
            conn.commit()


# Aliases for backward compatibility
ReplayCache = SQLiteReplayCache
AssessmentCache = SQLiteReplayCache

__all__ = ["SQLiteReplayCache", "ReplayCache", "AssessmentCache"]