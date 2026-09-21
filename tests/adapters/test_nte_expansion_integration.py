import respx
from game_assistant.adapters.neverness.adapter import NteAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult
from game_assistant.snapshots import SnapshotStore

@respx.mock
async def test_teams_are_available_without_credentials_and_send_no_authorization():
    route = respx.get('https://bbs-api.tajiduo.com/apihub/awapi/yh/team').respond(200, json={'code': 0, 'data': [
        {'id': '1', 'name': '官方队伍', 'desc': '阵容说明', 'imgs': []},
    ]})
    result = await NteAdapter(Settings()).fetch(Capability.TEAMS)
    assert result.ok and result.payload.entries[0].name == '官方队伍'
    assert 'authorization' not in route.calls.last.request.headers

@respx.mock
async def test_private_assets_use_selected_role_and_keep_independent_payloads():
    a = NteAdapter(Settings(nte_access_token='test', nte_role_id='selected'))
    for cap in [Capability.REALESTATE, Capability.VEHICLES]:
        route = respx.get('https://bbs-api.tajiduo.com/apihub/awapi/yh/' + cap.value).respond(200,
            json={'code': 0, 'data': {'detail': [{'id': 'asset', 'name': '资产', 'own': True}], 'ownCnt': 1, 'total': 1}})
        result = await a.fetch(cap)
        assert result.ok and result.payload.entries[0].owned is True
        assert route.calls.last.request.url.params['roleId'] == 'selected'

def test_account_switch_clears_private_assets_but_keeps_public_teams():
    store = SnapshotStore(':memory:')
    for cap in ['realestate', 'vehicles', 'teams']:
        store.save('nte', cap, '{}')
        store.record_poll('nte', cap, FetchResult(ok=True, payload={}))
    store.clear_private('nte')
    assert store.get('nte', 'teams') and store.get_poll_status('nte', 'teams')
    for cap in ['realestate', 'vehicles']:
        assert store.get('nte', cap) is None and store.get_poll_status('nte', cap) is None
