import sqlite3
import threading
from datetime import datetime, timezone


class ReminderDedup:
    """提醒去重表。dedup_key 语义见 reminder.py 各规则注释。"""

    def __init__(self, db_path: str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS notified ("
            " rule_key TEXT PRIMARY KEY, sent_at TEXT NOT NULL)")
        self._conn.commit()

    def already_sent(self, rule_key: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM notified WHERE rule_key = ?", (rule_key,)).fetchone()
        return row is not None

    def mark_sent(self, rule_key: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO notified (rule_key, sent_at) VALUES (?, ?)"
                " ON CONFLICT(rule_key) DO NOTHING",
                (rule_key, datetime.now(timezone.utc).isoformat()))
            self._conn.commit()
