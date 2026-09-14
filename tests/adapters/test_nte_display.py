import httpx
import respx
import pytest

from game_assistant.adapters.neverness.adapter import NteAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability, StaminaInfo
from game_assistant.registry import GameRegistry
from game_assistant.scheduler import PollingScheduler
from game_assistant.snapshots import SnapshotStore

BASE = 'https://bbs-api.tajiduo.com'
HOME = {'code': 0, 'data': {'roleid': '77', 'rolename': '测试玩家', 'lev': 40,
    'staminaValue': 160, 'staminaMaxValue': 240, 'citystaminaValue': 80,
    'citystaminaMaxValue': 120, 'dayvalue': 20, 'charidCnt': 1,
    'roleloginDays': 25, 'worldlevel': 3, 'tycoonLevel': 2}}
CHARACTERS = {'code': 0, 'data': [{'id': '1019', 'name': '测试角色', 'alev': 50,
    'quality': 'ITEM_QUALITY_ORANGE', 'elementType': 'CHARACTER_ELEMENT_TYPE_PSYCHE',
    'awakenLev': 2, 'slev': 0, 'fork': {'id': 'fork_test', 'name': '测试弧盘'}}]}
GACHA = {'code': 0, 'data': {'gachaDetails': [{'tab': '限定卡池', 'm': 90,
    'drawCount': 80, 'rareCount': 2, 'average': '40.0', 'playerOver': '50%',
    'details': [{'charid': '1019', 'rareCount': 30, 'timeStamp': 1789380000000}]}]}}


def adapter(**overrides):
    return NteAdapter(Settings(nte_access_token='test-token', nte_role_id='77',
                               nte_device_id='device', **overrides))


@respx.mock
async def test_account_and_stamina_share_home_but_cache_changes_with_identity():
    route = respx.get(BASE + '/apihub/awapi/yh/roleHome').respond(200, json=HOME)
    a = adapter()
    account = await a.fetch(Capability.ACCOUNT)
    stamina = await a.fetch(Capability.STAMINA)
    assert account.ok and stamina.ok
    assert account.payload.nickname == '测试玩家'
    assert isinstance(stamina.payload, StaminaInfo)
    assert stamina.payload.current == 160
    assert stamina.payload.weekly_remaining is None
    assert route.call_count == 1
    a._settings.nte_access_token = 'rotated-token'
    assert (await a.fetch(Capability.STAMINA)).ok
    assert route.call_count == 2


@respx.mock
async def test_home_cache_expiry_and_failed_fetch_keeps_last_snapshot(monkeypatch):
    import game_assistant.adapters.neverness.adapter as module
    clock = [10.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    route = respx.get(BASE + '/apihub/awapi/yh/roleHome').respond(200, json=HOME)
    a = adapter()
    registry = GameRegistry(); registry.register(a)
    store = SnapshotStore(':memory:')
    scheduler = PollingScheduler(registry, store, Settings(), None)
    assert (await scheduler.poll_once('nte', Capability.ACCOUNT)).ok
    old = store.get('nte', 'account')
    clock[0] += 31
    route.respond(200, json={'code': 0, 'data': {'unexpected': True}})
    assert not (await scheduler.poll_once('nte', Capability.ACCOUNT)).ok
    assert store.get('nte', 'account') == old


@respx.mock
async def test_home_rejects_other_role():
    respx.get(BASE + '/apihub/awapi/yh/roleHome').respond(200, json={
        **HOME, 'data': {**HOME['data'], 'roleid': 'different'}})
    assert not (await adapter().fetch(Capability.ACCOUNT)).ok


@respx.mock
async def test_exploration_normalizes_counts_and_null():
    respx.get(BASE + '/apihub/awapi/yh/areaProgress').respond(200, json={'code': 0, 'data': [
        {'id': 'area1', 'name': '测试区', 'progress': 1, 'total': 4,
         'detail': [{'id': 'chest', 'name': '宝箱', 'progress': None, 'total': 2}]}]})
    result = await adapter().fetch(Capability.EXPLORATION)
    assert result.ok
    assert result.payload.areas[0].current == 1
    assert result.payload.areas[0].details[0].current is None


@respx.mock
async def test_gacha_names_use_current_account_roles():
    respx.get(BASE + '/apihub/awapi/yh/characters').respond(200, json=CHARACTERS)
    respx.get(BASE + '/apihub/awapi/yh/gacha').respond(200, json=GACHA)
    result = await adapter().fetch(Capability.GACHA)
    assert result.ok
    assert result.payload.total_s == 2
    assert result.payload.pools[0].details[0].name == '测试角色'
    assert result.payload.pools[0].details[0].pity == 30


@respx.mock
async def test_record_uses_community_uid_and_filters_other_games():
    respx.get(BASE + '/usercenter/api/getUserFullInfo').respond(200, json={
        'code': 0, 'data': {'user': {'uid': 900001}}})
    record = respx.get(BASE + '/apihub/api/getGameRecordCard').respond(200, json={
        'code': 0, 'data': [
            {'gameId': 1256, 'gameName': '其他游戏', 'bindRoleInfo': {'roleId': '66'}},
            {'gameId': 1289, 'gameName': '异环', 'bindRoleInfo': {'roleId': '77', 'roleName': '测试玩家', 'lev': 40}},
        ]})
    result = await adapter().fetch(Capability.RECORD)
    assert result.ok and len(result.payload.cards) == 1
    assert result.payload.cards[0].role_id == '77'
    assert record.calls.last.request.url.params['uid'] == '900001'


def test_nte_registers_all_display_capabilities():
    assert adapter().capabilities == [Capability.ACCOUNT, Capability.STAMINA,
        Capability.ROLES, Capability.PROGRESS, Capability.EXPLORATION,
        Capability.GACHA, Capability.RECORD, Capability.EVENTS, Capability.ANNOUNCEMENT]


@respx.mock
async def test_business_success_200_is_accepted_by_account_parser():
    respx.get(BASE + '/apihub/awapi/yh/roleHome').respond(200, json={**HOME, 'code': 200})
    assert (await adapter().fetch(Capability.ACCOUNT)).ok


@pytest.mark.parametrize('status', [401, 402, 403])
@respx.mock
async def test_gacha_name_lookup_auth_failure_is_not_hidden(status):
    respx.get(BASE + '/apihub/awapi/yh/characters').respond(status)
    respx.get(BASE + '/apihub/awapi/yh/gacha').respond(200, json=GACHA)
    result = await adapter().fetch(Capability.GACHA)
    assert not result.ok
    assert result.error_code == status


@respx.mock
async def test_gacha_name_lookup_network_failure_can_use_ids():
    respx.get(BASE + '/apihub/awapi/yh/characters').mock(side_effect=httpx.ConnectError('offline'))
    respx.get(BASE + '/apihub/awapi/yh/gacha').respond(200, json=GACHA)
    result = await adapter().fetch(Capability.GACHA)
    assert result.ok
    assert '1019' in result.payload.pools[0].details[0].name
