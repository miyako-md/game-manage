import copy
import json
from types import SimpleNamespace

import pytest

from game_assistant.snapshots import SnapshotStore


def combat(account='A', end='2026-09-30T12:00:00.100+00:00', star=0, state='ok'):
    return {'role_id': account, 'server_id': 'S', 'tower': {
        'state': state, 'fetched_at': '2026-09-16T00:00:00+00:00',
        'source': 'towerDataDetail', 'data': {'season_end_at': end,
        'season_end_time': 10000, 'difficulty_list': [{'star': star}]}}}


def test_history_success_only_dedup_jitter_and_seasons(tmp_path):
    store = SnapshotStore(str(tmp_path / 'test.db'))
    for payload in [combat(), combat(end='2026-09-30T12:00:00.900+00:00'),
                    combat(star=9, state='stale'), combat(star=9, state='error')]:
        store.save('wuthering_waves', 'combat', json.dumps(payload))
    rows = store.wuwa_history.read('A', 'S', 'tower')['items']
    assert len(rows) == 1
    assert rows[0]['delta'] is None
    store.save('wuthering_waves', 'combat', json.dumps(combat(end='2026-10-30T12:00:00+00:00')))
    assert len(store.wuwa_history.read('A', 'S', 'tower')['items']) == 2


def test_roles_account_isolation_timestamp_dedup_and_null_delta(tmp_path):
    store = SnapshotStore(str(tmp_path / 'test.db'))
    row = {'role_id': '1501', 'level': None, 'extra': {'account_role_id': 'A',
           'server_id': 'S', 'provenance': {'fetched_at': 'first'}}}
    for account, level in [('A', None), ('B', 80), ('A', 0), ('A', 1)]:
        current = copy.deepcopy(row)
        current['level'] = level
        current['extra']['account_role_id'] = account
        store.save('wuthering_waves', 'roles', json.dumps([current]))
    current['extra']['provenance']['fetched_at'] = 'later'
    store.save('wuthering_waves', 'roles', json.dumps([current]))
    result = store.wuwa_history.read('A', 'S', 'roles')
    assert len(result['items']) == 3
    assert result['items'][0]['delta']['level'] == {'before': 0, 'after': 1, 'delta': 1}
    assert result['items'][1]['delta']['level'] == {'before': None, 'after': 0, 'delta': None}
    assert len(store.wuwa_history.read('B', 'S', 'roles')['items']) == 1
    assert store.wuwa_history.read('A', 'OTHER', 'roles')['items'] == []


def test_backfill_only_available_matching_snapshots(tmp_path):
    store = SnapshotStore(str(tmp_path / 'test.db'))
    assert store.wuwa_history.backfill(store, 'A', 'S')['inserted'] == 0
    store.save('wuthering_waves', 'combat', json.dumps(combat('B')))
    result = store.wuwa_history.backfill(store, 'A', 'S')
    assert result['inserted'] == 0
    assert result['complete'] is False
    assert store.wuwa_history.read('A', 'S', 'tower')['archive_started_at'] is None


def test_backfill_keeps_observation_time_distinct_from_archive_creation(tmp_path):
    store = SnapshotStore(str(tmp_path / 'db'))
    old = '2026-01-01T00:00:00+00:00'
    store._conn.execute('INSERT INTO snapshots VALUES (?,?,?,?)',
        ('wuthering_waves', 'combat', json.dumps(combat()), old))
    store._conn.commit()
    assert store.wuwa_history.backfill(store, 'A', 'S')['inserted'] == 1
    result = store.wuwa_history.read('A', 'S', 'tower')
    row = result['items'][0]
    assert row['observed_at'] == old
    assert row['archived_at'] != old
    assert result['archive_started_at'] == row['archived_at']


def test_tower_rejects_expired_at_source_but_allows_valid_old_season(tmp_path):
    store = SnapshotStore(str(tmp_path / 'db'))
    expired = combat(end='2026-01-01T00:00:00+00:00')
    assert store.wuwa_history.capture('combat', expired) == 0
    historical = combat(end='2026-01-01T00:00:00+00:00')
    historical['tower']['fetched_at'] = '2025-12-15T00:00:00+00:00'
    assert store.wuwa_history.capture('combat', historical) == 1


@pytest.mark.parametrize('kind,payload', [
    ('roles', [{'role_id': '1', 'extra': ['malformed']}]),
    ('combat', {'role_id': 'A', 'server_id': 'S', 'tower': ['malformed']}),
])
def test_malformed_legacy_snapshot_is_not_archived(tmp_path, kind, payload):
    store = SnapshotStore(str(tmp_path / 'db'))
    assert store.wuwa_history.capture(kind, payload) == 0


@pytest.mark.asyncio
async def test_scheduler_failed_and_switched_observations_never_archive(tmp_path):
    from game_assistant.config import Settings
    from game_assistant.models import Capability, FetchResult
    from game_assistant.scheduler import PollingScheduler
    store = SnapshotStore(str(tmp_path / 'db'))
    epoch = [0]
    auth = SimpleNamespace(account_generation=lambda _: epoch[0], version=lambda _: 1)
    response = [FetchResult(ok=False, error='failed')]
    async def fetch(_):
        if response[0].ok:
            epoch[0] += 1
        return response[0]
    adapter = SimpleNamespace(_auth=auth, fetch=fetch)
    scheduler = PollingScheduler(SimpleNamespace(get=lambda _: adapter), store, Settings(), None)
    await scheduler.poll_once('wuthering_waves', Capability.COMBAT)
    response[0] = FetchResult(ok=True, payload=combat(), credential_version=1)
    result = await scheduler.poll_once('wuthering_waves', Capability.COMBAT)
    assert result.error_kind == 'account_changed'
    assert store.wuwa_history.read('A', 'S', 'tower')['items'] == []
