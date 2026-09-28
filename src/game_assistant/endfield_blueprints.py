"""A local notebook for Endfield blueprint share codes supplied by the user."""
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BlueprintInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=2000)
    notes: str = Field(default='', max_length=2000)

    @field_validator('name', 'code', 'notes')
    @classmethod
    def clean_text(cls, value, info):
        value = value.strip()
        if info.field_name != 'notes' and not value:
            raise ValueError('名称和分享码不能为空')
        if any(ord(char) < 32 and char not in '\n\t' for char in value):
            raise ValueError('内容包含无法显示的字符')
        return value


class BlueprintStore:
    limit = 1000

    def __init__(self, db_path):
        self.path = Path(db_path).with_suffix('.endfield-blueprints.sqlite3')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS blueprints (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL,
                notes TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def items(self):
        with self._db() as db:
            return [dict(row) for row in db.execute('SELECT * FROM blueprints ORDER BY updated_at DESC, id')]

    def save(self, item: BlueprintInput, identity: str | None = None):
        now = datetime.now(timezone.utc).isoformat()
        with self._db() as db:
            # Keep the quota check and insert atomic across browser tabs/processes.
            db.execute('BEGIN IMMEDIATE')
            if identity is None:
                if db.execute('SELECT COUNT(*) FROM blueprints').fetchone()[0] >= self.limit:
                    raise ValueError('蓝图收藏已达 1000 条，请先整理已有收藏')
                identity = uuid.uuid4().hex
                db.execute('INSERT INTO blueprints VALUES (?,?,?,?,?,?)',
                           (identity, item.name, item.code, item.notes, now, now))
            else:
                result = db.execute('UPDATE blueprints SET name=?,code=?,notes=?,updated_at=? WHERE id=?',
                                    (item.name, item.code, item.notes, now, identity))
                if not result.rowcount:
                    raise KeyError(identity)
            return dict(db.execute('SELECT * FROM blueprints WHERE id=?', (identity,)).fetchone())

    def delete(self, identity):
        with self._db() as db:
            return bool(db.execute('DELETE FROM blueprints WHERE id=?', (identity,)).rowcount)
