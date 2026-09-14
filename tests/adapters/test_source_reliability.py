from types import SimpleNamespace

import httpx
import pytest
import respx

from game_assistant.adapters.wuthering_waves.adapter import WutheringWavesAdapter
from game_assistant.adapters.neverness.adapter import NteAdapter
from game_assistant.adapters.league_of_legends.adapter import LeagueOfLegendsAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult
from tests.adapters import test_wuwa_adapter as wuwa
from tests.adapters import test_nte_adapter as nte
from tests.test_auth_service import make_service, logged_in


@pytest.mark.parametrize('adapter', [WutheringWavesAdapter, NteAdapter])
async def test_missing_credentials_have_explicit_unconfigured_kind(adapter):
    result = await adapter(Settings()).fetch(Capability.ACCOUNT)
    assert result.error_kind == 'unconfigured'


async def test_missing_rolebox_credentials_are_unconfigured():
    adapter = WutheringWavesAdapter(Settings(wuwa_token='tok', wuwa_user_id='uid',
                                            wuwa_role_id='r1', wuwa_server_id='s1'))
    result = await adapter.fetch(Capability.ROLES)
    assert result.error_kind == 'unconfigured'


async def test_lol_process_absence_is_offline(monkeypatch):
    monkeypatch.setattr('game_assistant.adapters.league_of_legends.adapter.discover_lcu_credentials', lambda: None)
    result = await LeagueOfLegendsAdapter(Settings()).fetch(Capability.ACCOUNT)
    assert result.error_kind == 'offline'


@respx.mock
async def test_lol_connection_failure_is_source_error_not_offline(monkeypatch):
    monkeypatch.setattr('game_assistant.adapters.league_of_legends.adapter.discover_lcu_credentials',
                        lambda: ('54321', 'fake-token'))
    respx.get('https://127.0.0.1:54321/lol-summoner/v1/current-summoner').mock(
        side_effect=httpx.ConnectError('failed'))
    result = await LeagueOfLegendsAdapter(Settings()).fetch(Capability.ACCOUNT)
    assert result.error_kind == 'source_error'


@pytest.mark.parametrize('body', ['', '<p>新版本已发布，没有可解析活动</p>'])
@respx.mock
async def test_wuwa_unparseable_calendar_fails(body):
    respx.post(wuwa.EVENT_URL).mock(return_value=httpx.Response(200, json=wuwa.EVENTS_LIST_RAW))
    respx.post(wuwa.DETAIL_URL).mock(return_value=httpx.Response(200, json={
        'code': 200, 'data': {'postDetail': {'postH5Content': body}}}))
    result = await WutheringWavesAdapter(Settings(wuwa_token='tok', wuwa_user_id='uid')).fetch(Capability.EVENTS)
    assert not result.ok and result.error_kind == 'invalid_data'


@pytest.mark.parametrize('body', ['', '<p>新版本已发布，没有可解析活动</p>'])
@respx.mock
async def test_nte_unparseable_calendar_fails(body):
    respx.get(f'{nte.BASE}/apihub/wapi/getAllCommunity').mock(
        return_value=httpx.Response(200, json=nte.COMMUNITY_RAW))
    respx.get(f'{nte.BASE}/bbs/wapi/getOfficialPostList').mock(
        return_value=httpx.Response(200, json=nte.EVENTS_POSTS_RAW))
    respx.get(f'{nte.BASE}/bbs/wapi/getPostFull').mock(
        return_value=httpx.Response(200, json={'code': 0, 'data': {'post': {'content': body}}}))
    result = await NteAdapter(Settings()).fetch(Capability.EVENTS)
    assert not result.ok and result.error_kind == 'invalid_data'


async def test_manual_calendar_all_invalid_is_not_successful_empty():
    result = await NteAdapter(Settings(nte_events=[{'name': '坏项', 'end': 'bad'}])).fetch(Capability.EVENTS)
    assert not result.ok and result.error_kind == 'invalid_data'


@pytest.mark.parametrize('code', [220, 401, 10901])
async def test_wuwa_auth_error_codes_are_classified(code):
    from game_assistant.adapters.wuthering_waves.kuro_client import KuroError
    async def broken():
        raise KuroError(code, '登录失效')
    adapter = WutheringWavesAdapter(Settings(wuwa_token='tok', wuwa_user_id='uid'))
    adapter._client = SimpleNamespace(role_list=broken)
    result = await adapter.fetch(Capability.ACCOUNT)
    assert result.error_kind == 'auth_expired'


@pytest.mark.parametrize('code,kind', [(401,'auth_expired'), (500,'source_error')])
async def test_auth_renewal_failure_classified_without_using_stale_auth_state(tmp_path, monkeypatch, code, kind):
    from game_assistant.auth.providers import AuthError
    service, provider, _, now = make_service(tmp_path)
    await logged_in(service)
    now[0] += 4000
    service._errors['nte'] = '先前登录失效'
    async def renew(_):
        raise AuthError('请求失败', code=code)
    monkeypatch.setattr(provider, 'renew', renew)
    async def action():
        return FetchResult(ok=True)
    result = await service.fetch('nte', Capability.ROLES, action)
    assert result.error_kind == kind


async def test_auth_final_rejection_sets_kind(tmp_path):
    service, _, _, _ = make_service(tmp_path)
    async def action():
        return FetchResult(ok=False, error_code=401, error='失效')
    result = await service.fetch('nte', Capability.ROLES, action)
    assert result.error_kind == 'auth_expired'


@respx.mock
async def test_wuwa_network_exception_cannot_leak_request_secrets_to_status():
    from game_assistant.scheduler import PollingScheduler
    from game_assistant.snapshots import SnapshotStore
    adapter = WutheringWavesAdapter(Settings(wuwa_token='tok', wuwa_user_id='uid'))
    respx.post(wuwa.ROLE_LIST_URL).mock(side_effect=httpx.ConnectError(
        'https://example.test/?token=secret-token'))
    sched = PollingScheduler(SimpleNamespace(get=lambda _: adapter), SnapshotStore(':memory:'),
                            Settings(), None)
    result = await sched.poll_once(adapter.game_id, Capability.ACCOUNT)
    assert not result.ok and result.error_kind == 'source_error'
    assert 'secret-token' not in sched.store.get_poll_status(adapter.game_id, 'account')['error']


async def test_failed_manual_calendar_refresh_keeps_successful_snapshot():
    from game_assistant.scheduler import PollingScheduler
    from game_assistant.snapshots import SnapshotStore
    settings = Settings(nte_events=[{'name': '活动', 'end': '2026-09-18 04:00'}])
    adapter = NteAdapter(settings)
    sched = PollingScheduler(SimpleNamespace(get=lambda _: adapter), SnapshotStore(':memory:'),
                            settings, None)
    assert (await sched.poll_once('nte', Capability.EVENTS)).ok
    snapshot = sched.store.get('nte', 'events')
    settings.nte_events = [{'name': '坏项', 'end': 'invalid'}]
    assert not (await sched.poll_once('nte', Capability.EVENTS)).ok
    assert sched.store.get('nte', 'events') == snapshot
    assert sched.store.get_poll_status('nte', 'events')['state'] == 'error'


@respx.mock
async def test_rolebox_network_error_cannot_leak_into_poll_status_or_log(caplog):
    from game_assistant.scheduler import PollingScheduler
    from game_assistant.snapshots import SnapshotStore
    adapter = WutheringWavesAdapter(Settings(wuwa_token='tok', wuwa_user_id='uid',
        wuwa_role_id='r1', wuwa_server_id='s1', wuwa_b_at='ticket',
        wuwa_did='device', wuwa_dev_code='test-device'))
    respx.post(f'{wuwa.ROLEBOX_BASE_URL}/roleData').mock(side_effect=httpx.ConnectError(
        'https://example.test/?token=fake-secret-marker'))
    sched = PollingScheduler(SimpleNamespace(get=lambda _: adapter), SnapshotStore(':memory:'),
                            Settings(), None)
    result = await sched.poll_once(adapter.game_id, Capability.ROLES)
    status = sched.store.get_poll_status(adapter.game_id, 'roles')
    assert result.error_kind == status['error_kind'] == 'source_error'
    assert 'fake-secret-marker' not in str(status)
    assert 'fake-secret-marker' not in caplog.text


async def test_reversed_manual_calendar_preserves_last_success():
    from game_assistant.scheduler import PollingScheduler
    from game_assistant.snapshots import SnapshotStore
    settings = Settings(nte_events=[{'name': '活动', 'end': '2026-09-18 04:00'}])
    adapter = NteAdapter(settings)
    sched = PollingScheduler(SimpleNamespace(get=lambda _: adapter), SnapshotStore(':memory:'),
                            settings, None)
    assert (await sched.poll_once('nte', Capability.EVENTS)).ok
    snapshot = sched.store.get('nte', 'events')
    settings.nte_events = [{'name': '逆序活动', 'start': '2026-09-19 04:00', 'end': '2026-09-18 04:00'}]
    result = await sched.poll_once('nte', Capability.EVENTS)
    assert not result.ok and result.error_kind == 'invalid_data'
    assert sched.store.get('nte', 'events') == snapshot
