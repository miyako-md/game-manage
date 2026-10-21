"""Operator-admin group policy. QQ membership never conveys permissions."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from pydantic import Field

from .reminder_policy import QuietPolicy

GAMES = ['wuthering_waves', 'nte', 'endfield']


class GroupSettings(QuietPolicy):
    allowed_games: list[Literal['wuthering_waves', 'nte', 'endfield']] = Field(default_factory=lambda: list(GAMES), max_length=3)
    public_topics: list[Literal['events', 'news']] = Field(default_factory=list, max_length=2)
    image_preference: bool = True
    requests_per_minute: int = Field(default=20, ge=1, le=60)


class GroupSettingsService:
    def __init__(self, store, *, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def read(self, app_id, group):
        with self.store.lock:
            row = self.store.db.execute('SELECT body FROM qq_group_settings WHERE app_id=? AND group_openid=?', (app_id, group)).fetchone()
        return GroupSettings.model_validate_json(row[0]) if row else GroupSettings()

    def save(self, app_id, group, settings):
        with self.store.transaction() as db:
            db.execute('INSERT INTO qq_group_settings VALUES(?,?,?) ON CONFLICT(app_id,group_openid) DO UPDATE SET body=excluded.body',
                       (app_id, group, settings.model_dump_json()))
        return settings

    def consume(self, identity, game, command, image_requested):
        if identity.scene != 'group':
            return image_requested
        settings = self.read(identity.app_id, identity.group_openid)
        now = self.clock()
        if command not in ('help', 'dashboard', 'retired'):
            if game is not None and game not in settings.allowed_games:
                raise HTTPException(403, 'group_game_disabled')
            # Global/private overview must not reveal a game disabled for this group.
            if game is None and set(settings.allowed_games) != set(GAMES):
                raise HTTPException(403, 'group_select_allowed_game')
            window = int(now.timestamp()) // 60
            with self.store.transaction() as db:
                row = db.execute('SELECT window,count FROM qq_group_limits WHERE app_id=? AND group_openid=?', (identity.app_id, identity.group_openid)).fetchone()
                count = row['count'] if row and row['window'] == window else 0
                if count >= settings.requests_per_minute:
                    raise HTTPException(429, 'group_rate_limited')
                db.execute('INSERT INTO qq_group_limits VALUES(?,?,?,?) ON CONFLICT(app_id,group_openid) DO UPDATE SET window=excluded.window,count=excluded.count',
                           (identity.app_id, identity.group_openid, window, count + 1))
        return bool(image_requested and settings.image_preference)
