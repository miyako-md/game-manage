import sqlite3
import threading
from datetime import datetime, timezone


class SnapshotStore:
    def __init__(self, db_path: str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS snapshots ("
                " game_id TEXT NOT NULL, capability TEXT NOT NULL,"
                " payload TEXT NOT NULL, fetched_at TEXT NOT NULL,"
                " PRIMARY KEY (game_id, capability))"
            )
            self._conn.commit()

    def save(self, game_id: str, capability: str, payload_json: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO snapshots (game_id, capability, payload, fetched_at)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(game_id, capability) DO UPDATE SET"
                " payload = excluded.payload, fetched_at = excluded.fetched_at",
                (game_id, capability, payload_json,
                 datetime.now(timezone.utc).isoformat()),
            )
            self._conn.commit()

    def get(self, game_id: str, capability: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload, fetched_at FROM snapshots"
                " WHERE game_id = ? AND capability = ?",
                (game_id, capability),
            ).fetchone()
        return {"payload": row[0], "fetched_at": row[1]} if row else None

    def clear_private(self, game_id: str) -> None:
        """Account switching must never display the previous account's data."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM snapshots WHERE game_id = ? AND capability NOT IN ('announcement','events','news')",
                (game_id,))
            self._conn.commit()
