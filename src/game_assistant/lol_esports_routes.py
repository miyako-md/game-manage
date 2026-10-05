"""Public esports cache; independent from personal collection and login."""
import math
from datetime import datetime, timezone
from time import monotonic

from fastapi import Body, HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError

from game_assistant.adapters.league_of_legends.esports_models import EsportsSnapshot
from game_assistant.adapters.league_of_legends.esports_service import snapshot_for_display
from game_assistant.models import Capability
from game_assistant.scheduler import PollingScheduler

GAME = 'league_of_legends'


def _cached(app):
    row = app.state.store.get(GAME, 'esports')
    if row:
        try:
            return EsportsSnapshot.model_validate_json(row['payload'])
        except ValidationError:
            pass
    return None


def read_esports_snapshot(app, now: datetime) -> dict:
    row = app.state.store.get(GAME, 'esports')
    status = app.state.store.get_poll_status(GAME, 'esports') or {'state': 'never'}
    return {'game_id': GAME, 'capability': 'esports',
            'fetched_at': row['fetched_at'] if row else None, 'poll_status': status,
            **snapshot_for_display(_cached(app), status, now)}


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')


def install_lol_esports_routes(app) -> None:
    app.state.lol_esports_poller = app.state.scheduler or PollingScheduler(
        app.state.registry, app.state.store, app.state.settings)
    try:
        adapter = app.state.registry.get(GAME)
    except KeyError:
        adapter = None
    if adapter is not None:
        adapter.esports_cached = lambda: _cached(app)
    next_manual = 0.0

    @app.post('/api/lol/esports/refresh')
    async def refresh_esports(body: RefreshRequest | None = Body(default=None)) -> dict:
        nonlocal next_manual
        if adapter is None:
            raise HTTPException(404, '未注册英雄联盟')
        remaining = max(math.ceil(next_manual - monotonic()), adapter.esports.source_cooldown_seconds())
        if remaining > 0:
            raise HTTPException(429, '赛事更新暂在冷却中，请稍后重试', headers={'Retry-After': str(remaining)})
        next_manual = monotonic() + 60
        result = await app.state.lol_esports_poller.poll_once(GAME, Capability.ESPORTS)
        return {'ok': result.ok, 'error_kind': result.error_kind,
                'snapshot': read_esports_snapshot(app, datetime.now(timezone.utc))}
