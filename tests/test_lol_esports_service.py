import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from tests.adapters.test_lol_esports_parse import sample
from game_assistant.adapters.league_of_legends.esports_client import EsportsSourceError
from game_assistant.adapters.league_of_legends.esports_models import EsportsSnapshot, GroupMeta
from game_assistant.adapters.league_of_legends.esports_service import LolEsportsService, snapshot_for_display

NOW = datetime(2026, 10, 4, 13, tzinfo=timezone.utc)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.fail = set()
        self.lpl = sample('lpl')
        self.active = 0
        self.maximum = 0

    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass

    async def request(self, key, value):
        self.calls.append(key)
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        await asyncio.sleep(0)
        self.active -= 1
        if key in self.fail or '*' in self.fail:
            raise EsportsSourceError('http_429', 120)
        return deepcopy(value)

    async def fetch_catalog(self):
        raw = sample('catalog')
        raw['msg']['sGameList'] = {'5': raw['msg']['sGameList']['5']}
        return await self.request('catalog', raw)

    async def fetch_matches(self, sid): return await self.request('matches', self.lpl)

    async def fetch_team(self, sid):
        raw = sample('edg')
        raw['msg']['baseInfo']['TeamId'] = sid
        return await self.request('roster:' + sid, raw)


def service(client=None):
    client = client or FakeClient()
    clocks = [NOW, 100.0]
    svc = LolEsportsService(lambda: client, clock=lambda: clocks[0], monotonic_clock=lambda: clocks[1],
                           settings=SimpleNamespace(esports_seconds=900, esports_profiles_seconds=86400))
    return svc, client, clocks


async def test_partial_match_group_preserves_missing_records():
    svc, client, clock = service()
    first = (await svc.refresh(None)).payload
    assert len(first.matches) == 2
    client.lpl['msg'] = [client.lpl['msg'][0], {'bad': True}]
    clock[0] += timedelta(minutes=16); clock[1] += 960
    result = await svc.refresh(first)
    assert result.ok and len(result.payload.matches) == 2
    assert result.payload.coverage['matches:tencent:tournament:237'].coverage == 'partial'


async def test_roster_failure_keeps_old_times():
    svc, client, clock = service()
    first = (await svc.refresh(None)).payload
    key = next(k for k in first.coverage if k.startswith('roster:'))
    client.fail.add('roster:' + key.rsplit(':', 1)[1])
    clock[0] += timedelta(days=2); clock[1] += 172800
    result = await svc.refresh(first)
    assert result.ok and result.payload.refresh_state == 'partial'
    assert result.payload.coverage[key].last_success_at == first.coverage[key].last_success_at
    assert result.payload.coverage[key].source_updated_at == first.coverage[key].source_updated_at
    assert len(result.payload.players) == len(first.players)


async def test_all_fail_returns_error_and_no_replacement():
    svc, client, _ = service()
    client.fail.add('*')
    result = await svc.refresh(None)
    assert result.ok is False and result.payload is None


async def test_noop_during_failed_group_backoff_is_not_recovery():
    svc, client, clocks = service()
    first = (await svc.refresh(None)).payload
    clocks[0] += timedelta(minutes=16); clocks[1] += 960
    async def fail(_):
        client.calls.append('failed-match')
        raise EsportsSourceError('network_error')
    client.fetch_matches = fail
    assert not (await svc.refresh(first)).ok
    count = len(client.calls)
    clocks[0] += timedelta(seconds=60); clocks[1] += 60
    retry = await svc.refresh(first)
    assert not retry.ok and retry.payload is None
    assert len(client.calls) == count


async def test_rollover_does_not_relabel_old_payload():
    old = EsportsSnapshot(season_year=2026)
    displayed = snapshot_for_display(old, None, datetime(2026, 12, 31, 16, tzinfo=timezone.utc))
    assert displayed['payload']['season_year'] == 2027
    assert displayed['payload']['matches'] == []
    assert displayed['source_status']['reason'] == 'current_season_missing'
    assert old.season_year == 2026


async def test_rollover_during_attempt_cooldown_preserves_previous_snapshot():
    svc, client, clocks = service()
    clocks[0] = datetime(2026, 12, 31, 15, 59, tzinfo=timezone.utc)
    first = (await svc.refresh(None)).payload
    count = len(client.calls)
    clocks[0] += timedelta(minutes=2)
    clocks[1] += 120
    result = await svc.refresh(first)
    assert not result.ok and result.payload is None
    assert len(client.calls) == count
    assert first.season_year == 2026 and first.matches


async def test_refresh_coalesces_and_cools_down():
    svc, client, _ = service()
    client.fail.add('catalog')
    assert not (await svc.refresh(None)).ok
    assert svc.source_cooldown_seconds() == 120
    count = len(client.calls)
    assert not (await svc.refresh(None)).ok
    assert len(client.calls) == count
    assert client.maximum <= 3


async def test_refresh_intervals():
    svc, client, clock = service()
    first = (await svc.refresh(None)).payload
    count = len(client.calls)
    second = (await svc.refresh(first)).payload
    assert len(client.calls) == count
    assert second.catalog.last_success_at == first.catalog.last_success_at
    clock[0] += timedelta(seconds=900); clock[1] += 900
    await svc.refresh(first)
    assert client.calls[count:] == ['matches']


def test_stale_thresholds():
    group = GroupMeta(group_key='roster:tencent:team:1', last_success_at=NOW,
                      source_updated_at=NOW - timedelta(days=8), attempt_state='ok')
    snapshot = EsportsSnapshot(season_year=2026, coverage={group.group_key: group})
    view = snapshot_for_display(snapshot, None, NOW)
    assert view['payload']['coverage'][group.group_key]['source_lagging']
    assert not view['payload']['coverage'][group.group_key]['stale']
    view = snapshot_for_display(snapshot, None, NOW + timedelta(seconds=172801))
    assert view['payload']['coverage'][group.group_key]['stale']
    snapshot.coverage[group.group_key].source_updated_at = NOW + timedelta(days=1)
    view = snapshot_for_display(snapshot, None, NOW)
    assert view['payload']['coverage'][group.group_key]['source_time_invalid']


async def test_roster_source_time_is_not_fetch_time():
    svc, _, _ = service()
    snap = (await svc.refresh(None)).payload
    row = next(v for k, v in snap.coverage.items() if k.startswith('roster:'))
    assert row.last_success_at == NOW
    assert row.source_updated_at != NOW
