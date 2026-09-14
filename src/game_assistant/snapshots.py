import sqlite3
import threading
from datetime import datetime, timezone

from game_assistant.models import FetchResult


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
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS poll_status ("
                " game_id TEXT NOT NULL, capability TEXT NOT NULL, state TEXT NOT NULL,"
                " last_attempt_at TEXT NOT NULL, last_success_at TEXT,"
                " consecutive_failures INTEGER NOT NULL, error TEXT, error_kind TEXT,"
                " PRIMARY KEY (game_id, capability))"
            )
            self._conn.commit()

    def record_poll(self, game_id: str, capability: str, result: FetchResult,
                    now: datetime | None = None) -> dict:
        """Record an attempt independently of the last usable snapshot."""
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        attempted = instant.astimezone(timezone.utc).isoformat()
        kind = None if result.ok else result.error_kind
        state = 'ok' if result.ok else kind if kind in (
            'offline', 'unconfigured', 'auth_expired') else 'error'
        with self._lock:
            previous = self._conn.execute(
                "SELECT last_success_at, consecutive_failures FROM poll_status"
                " WHERE game_id = ? AND capability = ?", (game_id, capability)).fetchone()
            last_success = previous[0] if previous else None
            if last_success is None:
                snapshot = self._conn.execute(
                    "SELECT fetched_at FROM snapshots WHERE game_id = ? AND capability = ?",
                    (game_id, capability)).fetchone()
                last_success = snapshot[0] if snapshot else None
            failures = 0 if state in ('ok', 'offline', 'unconfigured') else (
                (previous[1] if previous else 0) + 1)
            status = dict(game_id=game_id, capability=capability, state=state,
                last_attempt_at=attempted, last_success_at=attempted if result.ok else last_success,
                consecutive_failures=failures, error=None if result.ok else result.error,
                error_kind=kind)
            self._conn.execute(
                "INSERT INTO poll_status VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(game_id, capability) DO UPDATE SET"
                " state=excluded.state, last_attempt_at=excluded.last_attempt_at,"
                " last_success_at=excluded.last_success_at, consecutive_failures=excluded.consecutive_failures,"
                " error=excluded.error, error_kind=excluded.error_kind", tuple(status.values()))
            self._conn.commit()
        return status

    def get_poll_status(self, game_id: str, capability: str) -> dict | None:
        return next((s for s in self.list_poll_status(game_id)
                     if s['capability'] == capability), None)

    def list_poll_status(self, game_id: str | None = None) -> list[dict]:
        columns = ('game_id', 'capability', 'state', 'last_attempt_at',
                   'last_success_at', 'consecutive_failures', 'error', 'error_kind')
        query = 'SELECT ' + ', '.join(columns) + ' FROM poll_status'
        args = ()
        if game_id is not None:
            query += ' WHERE game_id = ?'
            args = (game_id,)
        query += ' ORDER BY game_id, capability'
        with self._lock:
            rows = self._conn.execute(query, args).fetchall()
        return [dict(zip(columns, row)) for row in rows]

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
            self._conn.execute(
                "DELETE FROM poll_status WHERE game_id = ? AND capability NOT IN ('announcement','events','news')",
                (game_id,))
            self._conn.commit()
