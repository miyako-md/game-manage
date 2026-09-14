import httpx
import respx

from game_assistant.auth.service import LoginService
from game_assistant.auth.store import CredentialStore
from game_assistant.config import Settings
from game_assistant.registry import build_default_registry
from game_assistant.models import Capability
from game_assistant.snapshots import SnapshotStore


def integrated(tmp_path, credentials=None, **config):
    settings = Settings(**config)
    store = CredentialStore(tmp_path / 'credentials')
    if credentials:
        store.save(credentials)
    auth = LoginService(settings, store)
    registry = build_default_registry(settings)
    auth.attach(registry, SnapshotStore(':memory:'))
    return auth, registry, settings


@respx.mock
async def test_saved_wuwa_identity_used_by_existing_account_client(tmp_path):
    auth, registry, settings = integrated(tmp_path, {'wuthering_waves': {
        'token': 'token', 'user_id': 'user', 'did': 'same-login-device',
        'dev_code': '1.1.1.1, UA', 'role_id': 'r1', 'server_id': 's1', 'b_at': 'ticket',
    }})
    role = respx.post('https://api.kurobbs.com/gamer/role/list').mock(return_value=httpx.Response(
        200, json={'code': 200, 'data': [{'roleId': 'r1', 'serverId': 's1', 'roleName': 'test'}]}))
    result = await registry.get('wuthering_waves').fetch(Capability.ACCOUNT)
    assert result.ok
    assert role.calls.last.request.headers['devcode'] == 'same-login-device'


@respx.mock
async def test_legacy_nte_refresh_only_acquires_stable_device_and_persists(tmp_path):
    auth, registry, settings = integrated(tmp_path, nte_refresh_token='legacy-refresh')
    refresh = respx.post('https://bbs-api.tajiduo.com/usercenter/api/refreshToken').mock(
        return_value=httpx.Response(200, json={'code': 0, 'data': {'accessToken': 'new-a', 'refreshToken': 'new-r'}}))
    roles = respx.get('https://bbs-api.tajiduo.com/usercenter/api/v2/getGameRoles').mock(
        return_value=httpx.Response(200, json={'code': 0, 'data': {'roles': [{'roleId': '77'}]}}))
    characters = respx.get('https://bbs-api.tajiduo.com/apihub/awapi/yh/characters').mock(
        return_value=httpx.Response(200, json={'code': 0, 'data': {'list': []}}))
    result = await registry.get('nte').fetch(Capability.ROLES)
    assert result.ok
    assert settings.nte_device_id
    assert refresh.calls.last.request.headers['deviceid'] == settings.nte_device_id
    assert characters.calls.last.request.headers['deviceid'] == settings.nte_device_id
    assert auth.store.load()['nte']['refresh_token'] == 'new-r'


@respx.mock
async def test_wuwa_expired_ticket_rotates_then_retries_existing_rolebox(tmp_path):
    auth, registry, settings = integrated(tmp_path, {'wuthering_waves': {
        'token': 'token', 'user_id': 'user', 'did': 'device',
        'dev_code': '1.1.1.1, UA', 'role_id': 'r1', 'server_id': 's1', 'b_at': 'old-ticket',
    }})
    rolebox = respx.post('https://api.kurobbs.com/aki/roleBox/akiBox/roleData').mock(side_effect=[
        httpx.Response(200, json={'code': 10903, 'msg': 'expired'}),
        httpx.Response(200, json={'code': 200, 'data': {'roleList': []}}),
    ])
    respx.post('https://api.kurobbs.com/aki/roleBox/requestToken').mock(return_value=httpx.Response(
        200, json={'code': 200, 'data': {'accessToken': 'new-ticket'}}))
    result = await registry.get('wuthering_waves').fetch(Capability.ROLES)
    assert result.ok
    assert rolebox.call_count == 2
    assert rolebox.calls.last.request.headers['b-at'] == 'new-ticket'
    assert auth.store.load()['wuthering_waves']['b_at'] == 'new-ticket'
