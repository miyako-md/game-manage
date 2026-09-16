from datetime import datetime, timezone

import pytest

from game_assistant.adapters.wuthering_waves import detail_parse
from game_assistant.adapters.wuthering_waves.adapter import WutheringWavesAdapter
from game_assistant.adapters.wuthering_waves.rolebox_client import RoleBoxError
from game_assistant.config import Settings
from unittest.mock import AsyncMock
import httpx
import respx
from game_assistant.adapters.wuthering_waves.rolebox_client import RoleBoxClient


def test_account_collections_and_missing_zero_are_preserved():
    data = detail_parse.normalize({'boxList': [{'num': 0}], 'treasureBoxList': None,
                                   'roleIconUrl': 'javascript:alert(1)'})
    assert data == {'box_list': [{'num': 0}], 'treasure_box_list': None, 'role_icon_url': None}


def test_url_schemes_and_acronym_fields():
    assert detail_parse.normalize({'homePageBG': 'https://host/bg', 'iconUrl': '/relative',
        'sourceUrl': 'file:///secret', 'picUrl': 'data:text/html,hello'}) == {
        'home_page_bg': 'https://host/bg', 'icon_url': None, 'source_url': None, 'pic_url': None}


def test_tower_retains_all_areas_floors_and_team_ids():
    raw = {'seasonEndTime': 60000, 'difficultyList': [{'difficulty': 3,
        'towerAreaList': [{'star': 0, 'maxStar': 12, 'floorList': [
            {'star': None, 'roleList': [{'roleId': 1501}]}]}]}]}
    data = detail_parse.parse_tower(raw, datetime(2026, 9, 16, tzinfo=timezone.utc))
    assert data['difficulty_list'][0]['tower_area_list'][0]['floor_list'][0] == {
        'star': None, 'role_list': [{'role_id': 1501}]}
    assert data['season_end_at'] == '2026-09-16T00:01:00+00:00'


def test_expired_tower_is_rejected():
    with pytest.raises(ValueError, match='过期'):
        detail_parse.parse_tower({'seasonEndTime': -1}, datetime.now(timezone.utc))


def test_resources_use_returned_quantities_and_periods():
    assert detail_parse.parse_periods({'months': [{'title': '九月', 'index': 9}]}) == {
        'month': [{'title': '九月', 'period': '9'}], 'week': [], 'version': []}
    assert detail_parse.normalize({'totalCoin': 0, 'totalStar': None, 'starList': [{'type': '活动', 'num': 25}]}) == {
        'total_coin': 0, 'total_star': None, 'star_list': [{'type': '活动', 'num': 25}]}


def adapter_with_client(monkeypatch):
    adapter = WutheringWavesAdapter(Settings(wuwa_token='t', wuwa_user_id='u',
        wuwa_role_id='account', wuwa_server_id='server', wuwa_b_at='b', wuwa_did='d', wuwa_dev_code='c'))
    client = AsyncMock()
    client.__aenter__.return_value = client
    monkeypatch.setattr(adapter, '_get_rolebox', lambda: client)
    return adapter, client


@pytest.mark.asyncio
async def test_combat_failure_keeps_successful_siblings_and_previous_source(monkeypatch):
    adapter, client = adapter_with_client(monkeypatch)
    client.tower_detail.return_value = {'seasonEndTime': 60000, 'difficultyList': []}
    client.challenge_details.return_value = {'challengeList': [{'star': 0}]}
    client.slash_detail.return_value = {'isUnlock': False}
    first = await adapter.fetch_combat()
    assert first.ok
    client.challenge_details.side_effect = RoleBoxError('offline')
    second = await adapter.fetch_combat()
    assert second.ok
    assert second.payload.hologram.state == 'stale'
    assert second.payload.hologram.data == {'challenge_list': [{'star': 0}]}
    assert second.payload.tower.state == 'ok'
    adapter._settings.wuwa_role_id = 'another'
    third = await adapter.fetch_combat()
    assert third.payload.hologram.data is None


@pytest.mark.asyncio
async def test_restart_restores_combat_and_resource_source_data(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from game_assistant.snapshots import SnapshotStore
    store = SnapshotStore(str(tmp_path / 'snapshots.db'))
    adapter, client = adapter_with_client(monkeypatch)
    client.tower_detail.return_value = {'seasonEndTime': 60000, 'difficultyList': []}
    client.challenge_details.return_value = {'challengeInfo': {'1': [{'difficulty': 6}]}}
    client.slash_detail.return_value = {'isUnlock': False}
    client.period_list.return_value = {'months': [{'index': 9}]}
    client.resource_report.return_value = {'totalStar': 0, 'totalCoin': 12}
    combat = await adapter.fetch_combat()
    resources = await adapter.fetch_resources()
    assert combat.ok and resources.ok
    store.save(adapter.game_id, 'combat', combat.payload.model_dump_json())
    store.save(adapter.game_id, 'resources', resources.payload.model_dump_json())
    assert isinstance(store.get(adapter.game_id, 'combat')['payload'], str)

    restarted, source = adapter_with_client(monkeypatch)
    restarted._auth = SimpleNamespace(snapshots=store)
    source.tower_detail.return_value = client.tower_detail.return_value
    source.slash_detail.return_value = client.slash_detail.return_value
    source.challenge_details.side_effect = RoleBoxError('offline')
    source.period_list.return_value = {'months': [{'index': 10}]}
    source.resource_report.side_effect = RoleBoxError('offline')
    restored_combat = await restarted.fetch_combat()
    restored_resources = await restarted.fetch_resources()
    assert restored_combat.ok and restored_resources.ok
    assert restored_combat.payload.tower.state == 'ok'
    assert restored_combat.payload.hologram.model_dump() == {
        **combat.payload.hologram.model_dump(), 'state': 'stale',
        'error': '来源请求失败，请稍后重试'}
    assert restored_resources.payload.current == {**resources.payload.current, 'state': 'stale'}
    assert restored_resources.payload.current['period'] == '9'
    assert restored_resources.payload.periods['month'][0]['period'] == '10'


@pytest.mark.parametrize('persisted', [
    '{broken', 'null', '[]', '42',
    '{"role_id":"foreign","server_id":"server"}',
    '{"role_id":"account","server_id":"foreign"}',
    '{"role_id":"account"}',
])
def test_persisted_restore_rejects_malformed_or_foreign_identity(monkeypatch, tmp_path, persisted):
    import sqlite3
    from types import SimpleNamespace
    from game_assistant.snapshots import SnapshotStore
    store = SnapshotStore(str(tmp_path / 'snapshots.db'))
    adapter, _ = adapter_with_client(monkeypatch)
    adapter._auth = SimpleNamespace(snapshots=store)
    for capability in ('combat', 'resources'):
        store.save(adapter.game_id, capability, '{}')
        # Simulate an old/corrupt database without feeding invalid JSON into the
        # current save hook (which also archives successful combat snapshots).
        with sqlite3.connect(str(tmp_path / 'snapshots.db')) as connection:
            connection.execute('UPDATE snapshots SET payload=? WHERE capability=?',
                               (persisted, capability))
        assert adapter._previous_payload(capability, 'account', 'server') == {}


@pytest.mark.asyncio
async def test_empty_activity_and_resource_responses_are_not_success(monkeypatch):
    adapter, client = adapter_with_client(monkeypatch)
    client.more_activity.return_value = {}
    assert not (await adapter.fetch_activities()).ok
    client.period_list.return_value = {}
    assert not (await adapter.fetch_resources()).ok
    client.period_list.return_value = {'months': [{'index': 1}]}
    client.resource_report.return_value = {}
    assert not (await adapter.fetch_resource_detail('month', '1')).ok


@pytest.mark.asyncio
async def test_invalid_base_collections_do_not_publish_empty_profile(monkeypatch):
    adapter, client = adapter_with_client(monkeypatch)
    adapter._client.role_list = AsyncMock(return_value={'data': [{'roleId': 'account', 'roleName': '漂泊者'}]})
    client.base_data.return_value = {'boxList': 'broken'}
    assert not (await adapter.fetch_account()).ok


@pytest.mark.asyncio
async def test_owned_character_and_role_enhancement(monkeypatch):
    adapter, client = adapter_with_client(monkeypatch)
    client.role_data.return_value = {'roleList': [{'roleId': 1501, 'level': 0,
        'roleSkin': {'skinId': 0}, 'weaponData': {'weaponName': '真实武器'}}]}
    client.role_detail.return_value = {'roleAttributeList': [], 'skillList': [], 'weaponData': {'level': 0}}
    result = await adapter.fetch_roles()
    assert result.payload[0].extra['role_skin'] == {'skin_id': 0}
    invalid = await adapter.fetch_role_detail('1502')
    assert not invalid.ok and invalid.error_kind == 'not_found'
    client.role_detail.assert_not_called()
    valid = await adapter.fetch_role_detail('1501')
    assert valid.payload['character_id'] == '1501'
    assert valid.payload['data']['weapon_data']['level'] == 0


@pytest.mark.asyncio
async def test_resource_period_is_allowlisted_before_network(monkeypatch):
    adapter, client = adapter_with_client(monkeypatch)
    client.period_list.return_value = {'months': [{'index': 9, 'title': '九月'}]}
    invalid = await adapter.fetch_resource_detail('month', '8')
    assert not invalid.ok and invalid.error_kind == 'not_found'
    client.resource_report.assert_not_called()
    client.resource_report.return_value = {'totalStar': 0, 'totalCoin': None}
    result = await adapter.fetch_resources()
    assert result.payload.current['data'] == {'total_star': 0, 'total_coin': None}
    client.resource_report.side_effect = RoleBoxError('offline')
    failed = await adapter.fetch_resources()
    assert failed.payload.current['data']['total_star'] == 0
    assert failed.payload.current['state'] == 'stale'


@pytest.mark.asyncio
async def test_account_adds_base_collections_without_dropping_summary(monkeypatch):
    adapter, client = adapter_with_client(monkeypatch)
    adapter._client.role_list = AsyncMock(return_value={'data': [{'roleId': 'account', 'roleName': '漂泊者'}]})
    client.base_data.return_value = {'boxList': [{'num': 0}], 'worldLevel': 8}
    result = await adapter.fetch_account()
    assert result.payload.nickname == '漂泊者'
    assert result.payload.extra['profile']['box_list'] == [{'num': 0}]


@respx.mock
@pytest.mark.asyncio
async def test_clients_use_fixed_endpoints_rolebox_auth_and_resource_token():
    root = 'https://api.kurobbs.com'
    detail = respx.post(root + '/aki/roleBox/akiBox/getRoleDetail').mock(return_value=httpx.Response(200, json={'code': 200, 'data': '{}'}))
    periods = respx.get(root + '/aki/resource/period/list').mock(return_value=httpx.Response(200, json={'code': 200, 'data': {'months': []}}))
    month = respx.post(root + '/aki/resource/month').mock(return_value=httpx.Response(200, json={'code': 200, 'data': {'totalStar': 0}}))
    async with RoleBoxClient('b', 'c', 'd', token='t') as rb:
        await rb.role_detail('account', 'server', '1501')
        await rb.period_list()
        await rb.resource_report('account', 'server', 'month', '9')
    assert b'id=1501' in detail.calls[0].request.content
    assert detail.calls[0].request.headers['b-at'] == 'b'
    assert periods.calls[0].request.headers['token'] == 't'
    assert month.calls[0].request.headers['token'] == 't'
