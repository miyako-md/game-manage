import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from tests.test_lol_routes import client
from game_assistant.models import Capability, FetchResult
from game_assistant.adapters.league_of_legends.esports_models import EsportsSnapshot
from game_assistant.adapters.league_of_legends.adapter import LeagueOfLegendsAdapter

PATH = '/api/games/league_of_legends/snapshot/esports'
REFRESH = '/api/lol/esports/refresh'
HEADERS = {'X-Game-Assistant': '1'}


def test_esports_get_is_cache_only(tmp_path, monkeypatch):
    c, app = client(tmp_path)
    monkeypatch.setattr(LeagueOfLegendsAdapter, '_discover', lambda _: pytest.fail('LCU should not run'))
    monkeypatch.setattr(app.state.store, 'save', lambda *a: pytest.fail('GET writes'))
    r = c.get(PATH)
    assert r.status_code == 200
    assert r.json()['payload']['schema_version'] == 1
    assert r.json()['payload']['matches'] == []
    assert r.json()['source_status']['reason'] == 'never'


def test_no_scheduler_manual_refresh_persists(tmp_path, monkeypatch):
    c, app = client(tmp_path)
    year = datetime.now(timezone.utc).astimezone(__import__('datetime').timezone(__import__('datetime').timedelta(hours=8))).year
    fetch = AsyncMock(return_value=FetchResult(ok=True, payload=EsportsSnapshot(season_year=year)))
    adapter = app.state.registry.get('league_of_legends')
    monkeypatch.setattr(adapter, 'fetch_esports', fetch)
    monkeypatch.setattr(adapter, 'fetch_account', AsyncMock(side_effect=AssertionError('account collected')))
    r = c.post(REFRESH, headers=HEADERS)
    assert r.status_code == 200 and r.json()['ok']
    assert fetch.await_count == 1
    assert app.state.store.get('league_of_legends', 'esports')
    assert c.get(PATH).json()['fetched_at']


def test_refresh_only_polls_esports(tmp_path, monkeypatch):
    c, app = client(tmp_path)
    call = AsyncMock(return_value=FetchResult(ok=False, error='unavailable', error_kind='source_error'))
    monkeypatch.setattr(app.state.lol_esports_poller, 'poll_once', call)
    assert c.post(REFRESH, headers=HEADERS).status_code == 200
    call.assert_awaited_once_with('league_of_legends', Capability.ESPORTS)


def test_refresh_security_and_cooldown(tmp_path, monkeypatch):
    c, app = client(tmp_path)
    monkeypatch.setattr(app.state.lol_esports_poller, 'poll_once', AsyncMock(return_value=FetchResult(ok=False)))
    assert c.post(REFRESH).status_code == 403
    assert c.post(REFRESH, headers={**HEADERS, 'Origin': 'https://evil.example'}).status_code == 403
    assert c.post(REFRESH, headers=HEADERS, json={'url': 'https://evil.example'}).status_code == 422
    assert c.post(REFRESH, headers=HEADERS).status_code == 200
    r = c.post(REFRESH, headers=HEADERS)
    assert r.status_code == 429 and int(r.headers['retry-after']) > 0


@pytest.mark.parametrize('ok', [False, True])
async def test_esports_public_and_silent(tmp_path, monkeypatch, ok):
    _, app = client(tmp_path)
    store = app.state.store
    store.save('league_of_legends', 'esports', EsportsSnapshot(season_year=2026).model_dump_json())
    store.save('league_of_legends', 'account', '{}')
    store.clear_private('league_of_legends')
    assert store.get('league_of_legends', 'esports')
    assert not store.get('league_of_legends', 'account')
    poller = app.state.lol_esports_poller
    poller.reminder = type('Reminder', (), {'handle_poll': AsyncMock()})()
    result = FetchResult(ok=ok, payload=EsportsSnapshot(season_year=2026) if ok else None)
    monkeypatch.setattr(app.state.registry.get('league_of_legends'), 'fetch_esports', AsyncMock(return_value=result))
    await poller.poll_once('league_of_legends', Capability.ESPORTS)
    poller.reminder.handle_poll.assert_not_awaited()
    assert not store.get('league_of_legends', 'events')


async def test_manual_and_scheduled_share_lock(tmp_path, monkeypatch):
    _, app = client(tmp_path)
    active = maximum = 0
    async def fetch():
        nonlocal active, maximum
        active += 1; maximum = max(active, maximum)
        await asyncio.sleep(0.01)
        active -= 1
        return FetchResult(ok=False)
    monkeypatch.setattr(app.state.registry.get('league_of_legends'), 'fetch_esports', fetch)
    await asyncio.gather(*(app.state.lol_esports_poller.poll_once('league_of_legends', Capability.ESPORTS) for _ in range(2)))
    assert maximum == 1


def test_api_reports_partial_and_year_mismatch(tmp_path):
    c, app = client(tmp_path)
    app.state.store.save('league_of_legends', 'esports', EsportsSnapshot(season_year=2000).model_dump_json())
    r = c.get(PATH).json()
    assert r['source_status']['reason'] == 'current_season_missing'
    assert r['payload']['matches'] == []
