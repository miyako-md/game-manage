import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from game_assistant.adapters.wuthering_waves.adapter import WutheringWavesAdapter
from game_assistant.adapters.wuthering_waves import role, widget
from game_assistant.config import Settings
from game_assistant.models import Capability

BASE = 'https://api.kurobbs.com/aki/roleBox/akiBox'
NOW = datetime(2026, 9, 15, tzinfo=timezone.utc)
TOWER = {'seasonEndTime': 86400000, 'difficultyList': [
    {'difficulty': 4, 'difficultyName': '超载区', 'towerAreaList': [{'star': 18, 'maxStar': 18}]},
    {'difficulty': 3, 'difficultyName': '深境区', 'towerAreaList': [
        {'star': 6, 'maxStar': 12}, {'star': 12, 'maxStar': 12}, {'star': 0, 'maxStar': 12}]},
]}
BASE_PROGRESS = {'storeEnergy': 334, 'storeEnergyLimit': 480, 'liveness': 100,
    'livenessMaxCount': 100, 'weeklyInstCount': 3, 'weeklyInstCountLimit': 3,
    'weeklyInstTitle': '战歌重奏收取次数', 'rougeScore': 0, 'rougeScoreLimit': 6000,
    'rougeTitle': '千道门扉的异想'}

def adapter():
    return WutheringWavesAdapter(Settings(wuwa_token='test-token', wuwa_user_id='u',
        wuwa_role_id='r', wuwa_server_id='s', wuwa_b_at='test-ticket', wuwa_did='d', wuwa_dev_code='dev'))

def response(data):
    return httpx.Response(200, json={'code': 200, 'data': json.dumps(data)})

@respx.mock
async def test_stamina_refreshes_rolebox_before_reading_and_preserves_zero():
    refresh = respx.post(BASE + '/refreshData').respond(200, json={'code': 200, 'data': True})
    def base_data(request):
        assert refresh.call_count == 1
        return response({'energy': 0, 'maxEnergy': 240})
    respx.post(BASE + '/baseData').mock(side_effect=base_data)
    result = await adapter().fetch(Capability.STAMINA)
    assert result.ok and result.payload.current == 0 and result.payload.maximum == 240
    assert all('/widget/' not in str(call.request.url) for call in respx.calls)

@respx.mock
async def test_progress_selects_periodic_zone_and_refreshes_before_detail():
    refresh = respx.post(BASE + '/refreshData').respond(200, json={'code': 200, 'data': True})
    def detail(request):
        assert refresh.call_count == 1
        return response(TOWER)
    respx.post(BASE + '/towerDataDetail').mock(side_effect=detail)
    respx.post(BASE + '/baseData').mock(return_value=response(BASE_PROGRESS))
    respx.post('https://api.kurobbs.com/gamer/widget/game3/getData').mock(return_value=response({
        'towerData': {'name': '逆境深塔·超载区', 'cur': 18, 'total': 18},
        'weeklyData': {'name': '战歌重奏', 'cur': 0, 'total': 3},
        'storeEnergyData': {'name': '结晶单质', 'cur': 415, 'total': 480}}))
    result = await adapter().fetch(Capability.PROGRESS)
    assert result.ok
    rows = {x.name: (x.cur, x.total) for x in result.payload}
    assert rows == {'逆境深塔·深境区': (18, 36), '战歌重奏收取次数': (3, 3),
                    '结晶单质': (334, 480), '活跃度': (100, 100), '千道门扉的异想': (0, 6000)}

def test_base_progress_overrides_stale_widget_values_without_reinterpreting_claim_counts():
    items = widget.parse_base_progress(BASE_PROGRESS)
    assert items['weeklyData'].cur == 3
    assert items['weeklyData'].name == '战歌重奏收取次数'
    assert items['livenessData'].cur == 100
    assert items['weeklyRougeData'].cur == 0
    with pytest.raises(ValueError):
        widget.parse_base_progress({**BASE_PROGRESS, 'weeklyInstCount': None})

@respx.mock
async def test_refresh_ack_is_reused_briefly_but_not_across_accounts():
    a = adapter()
    refresh = respx.post(BASE + '/refreshData').respond(200, json={'code': 200, 'data': True})
    base = respx.post(BASE + '/baseData').mock(return_value=response({'energy': 1, 'maxEnergy': 240}))
    assert (await a.fetch(Capability.STAMINA)).ok
    assert (await a.fetch(Capability.STAMINA)).ok
    assert refresh.call_count == 1 and base.call_count == 2
    a._settings.wuwa_role_id = 'other-role'
    assert (await a.fetch(Capability.STAMINA)).ok
    assert refresh.call_count == 2

def test_store_energy_keeps_true_zero_and_does_not_invent_unknown_amount_or_reset():
    item = widget.parse_store_energy({'storeEnergy': 0, 'storeEnergyLimit': 480})
    assert item.cur == 0 and item.total == 480 and item.refresh_at is None
    with pytest.raises(ValueError):
        widget.parse_store_energy({'storeEnergyLimit': 480})

@respx.mock
@pytest.mark.parametrize('reply', [{'code': 200, 'data': False}, {'code': 10903, 'msg': 'expired'}])
async def test_failed_refresh_does_not_silently_publish_cached_widget_stamina(reply):
    respx.post(BASE + '/refreshData').respond(200, json=reply)
    result = await adapter().fetch(Capability.STAMINA)
    assert not result.ok
    assert len(respx.calls) == 1

def test_tower_season_end_is_remaining_milliseconds_and_rejects_old_cycle():
    item = widget.parse_periodic_tower(TOWER, NOW)
    assert item.refresh_at == NOW + timedelta(days=1)
    for remaining in [-1, 0, None, 'bad']:
        with pytest.raises(ValueError):
            widget.parse_periodic_tower({**TOWER, 'seasonEndTime': remaining}, NOW)
    with pytest.raises(ValueError):
        widget.parse_periodic_tower({**TOWER, 'difficultyList': TOWER['difficultyList'][:1]}, NOW)

@pytest.mark.parametrize('data', [{}, {'energy': None, 'maxEnergy': 240}, {'energy': 2, 'maxEnergy': 0}])
def test_invalid_base_energy_is_not_fabricated_zero(data):
    with pytest.raises(ValueError):
        role.parse_base_energy(data, NOW)
