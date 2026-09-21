import json

import httpx
import pytest

from game_assistant import wuwa_gacha
from game_assistant.snapshots import SnapshotStore


def module():
    return wuwa_gacha


def record(**kw):
    return dict(cardPoolType='1', resourceId=1501, qualityLevel=5,
                resourceType='角色', name='角色名', count=1, time='2026-01-01 12:00:00', **kw)


def test_multiplicity_idempotency_unknowns_and_isolation(tmp_path):
    g = module()
    snapshots = SnapshotStore(str(tmp_path / 'db'))
    store = g.GachaStore(snapshots._conn, snapshots._lock)
    rows = [record(), record(), {**record(), 'cardPoolType': '99', 'qualityLevel': None}]
    exported = {'info': {'uid': '100', 'export_app': 'WWUID'}, 'list': rows}
    assert store.import_records(exported, '100', 'S')['inserted'] == 3
    assert store.import_records(exported, '100', 'S')['inserted'] == 0
    result = store.read('100', 'S')
    assert result['total'] == 3
    assert result['pools'][0]['rarity_distribution'] == {'5': 2}
    assert len(result['gold']) == 2
    assert result['pools'][1]['rarity_distribution'] == {'unknown': 1}
    assert result['coverage']['complete'] is False
    assert store.read('100', 'OTHER')['state'] == 'need_import'
    assert store.read('101', 'S')['total'] == 0
    with pytest.raises(ValueError):
        store.import_records(exported, '101', 'S')
    with pytest.raises(ValueError):
        store.import_records(rows, '100', 'S')
    assert store.import_records([], '100', 'S')['inserted'] == 0


def test_null_and_literal_unknown_rarity_counts_reconcile_without_losing_raw_values(tmp_path):
    g = module()
    snapshots = SnapshotStore(str(tmp_path / 'db'))
    store = g.GachaStore(snapshots._conn, snapshots._lock)
    rows = [{**record(), 'qualityLevel': rarity} for rarity in (None, 'unknown', 5)]
    store.import_records({'info': {'uid': '100'}, 'list': rows}, '100', 'S')
    result = store.read('100', 'S')
    pool = result['pools'][0]
    assert pool['rarity_distribution'] == {'unknown': 2, '5': 1}
    assert sum(pool['rarity_distribution'].values()) == pool['total'] == 3
    assert {row['rarity'] for row in result['items']} == {None, 'unknown', '5'}


def test_url_validation_fragment_aliases_and_secret_sanitization(tmp_path):
    g = module()
    for url in [
        'https://gmserver-api.aki-game2.com/gacha/record/query?record_id=SECRET&player_id=100&svr_id=S',
        'https://aki-gm-resources.aki-game.com/aki/gacha/index.html#/record?recordId=SECRET&playerId=100&serverId=S',
    ]:
        assert g.parse_link(url, '100', 'S')['recordId'] == 'SECRET'
    for url in [
        'http://gmserver-api.aki-game2.com/?record_id=x&player_id=100',
        'https://gmserver-api.aki-game2.com.evil.com/?record_id=x&player_id=100',
        'https://user@gmserver-api.aki-game2.com/?record_id=x&player_id=100',
        'https://gmserver-api.aki-game2.com/?record_id=x&player_id=101',
        'https://gmserver-api.aki-game2.com/?record_id=x&player_id=100&server_id=OTHER',
        'https://gmserver-api.aki-game2.com/?record_id=x&player_id=100&playerId=101',
    ]:
        with pytest.raises(ValueError) as error:
            g.parse_link(url, '100', 'S')
        assert url not in str(error.value)
    db = tmp_path / 'db'
    snapshots = SnapshotStore(str(db))
    store = g.GachaStore(snapshots._conn, snapshots._lock)
    store.import_records({'info': {'uid': '100', 'recordId': 'SECRET'},
                          'list': [record(recordId='SECRET', url='SECRET')]}, '100', 'S')
    assert b'SECRET' not in db.read_bytes()
    assert 'SECRET' not in json.dumps(store.read('100', 'S'))


@pytest.mark.asyncio
async def test_official_client_no_redirect_partial_and_fixed_destination():
    g = module()
    seen = []
    def handler(request):
        seen.append(str(request.url))
        body = json.loads(request.content)
        if body['cardPoolType'] == '2':
            return httpx.Response(302, headers={'Location': 'https://evil.test/SECRET'})
        return httpx.Response(200, json={'code': 0, 'data': [record()] if body['cardPoolType'] == '1' else []})
    result = await g.fetch_official('https://gmserver-api.aki-game2.com/?record_id=SECRET&player_id=100',
        '100', 'S', transport=httpx.MockTransport(handler))
    assert len(seen) == 9
    assert set(seen) == {'https://gmserver-api.aki-game2.com/gacha/record/query'}
    assert result['failed_pools'] == ['2']
    assert len(result['records']['list']) == 1
    assert 'SECRET' not in json.dumps(result)


def test_explicit_draw_identity_and_conflicting_row_account(tmp_path):
    g = module()
    snapshots = SnapshotStore(str(tmp_path / 'db'))
    store = g.GachaStore(snapshots._conn, snapshots._lock)
    def wrapped(rows):
        return {'info': {'uid': '100'}, 'list': rows}
    assert store.import_records(wrapped([record(id='first')]), '100', 'S')['inserted'] == 1
    assert store.import_records(wrapped([record(id='second')]), '100', 'S')['inserted'] == 1
    assert store.import_records(wrapped([record(id='second')]), '100', 'S')['inserted'] == 0
    with pytest.raises(ValueError):
        store.import_records(wrapped([record(playerId='101')]), '100', 'S')
    with pytest.raises(ValueError):
        store.import_records(wrapped([record(serverId='OTHER')]), '100', 'S')
