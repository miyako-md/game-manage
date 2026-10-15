"""Frozen web inputs use scoped observations, never a logged-in browser."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json

import pytest

from game_assistant.accounts.models import AccountScope, QueryResult
from game_assistant.identity.models import Principal
from game_assistant.qq.query_routes import QqQueryService
from game_assistant.qq.web_payload import display_data
from tests.test_qq_unified_queries import CachedQuery, IDENTITY, no_external_network


NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


class CaptureQueue:
    def __init__(self):
        self.results = []
        self.renderer = SimpleNamespace(invalidate_account=lambda *args: None)

    async def render(self, scope, result, **kwargs):
        self.results.append(result)
        return b'image'


def service(query, queue=None, public=None):
    return QqQueryService(SimpleNamespace(resolve_qq_identity=lambda _: Principal('u', False)),
                          query, public, render_queue=queue, clock=lambda: NOW)


async def render_payload(query, command, game=None, role_name=None, public=None):
    queue = CaptureQueue()
    reply = await service(query, queue, public).query_reply(
        IDENTITY, command, game, role_name=role_name, image_requested=True, budget_seconds=5)
    assert 'image' in reply
    return queue.results[0].payload


async def test_web_overview_uses_website_first_accounts_and_does_not_merge_endfield():
    query = CachedQuery()
    query.add('nte', 'tajiduo', 'first', {'account': {'nickname': 'first'}}, default=False)
    query.add('nte', 'tajiduo', 'default', {'account': {'nickname': 'second'}}, default=True)
    query.add('endfield', 'hypergryph', 'passport', {'account': {'nickname': 'passport'}})
    query.add('endfield', 'skland', 'archive', {'account': {'base': {'name': 'archive'}}})
    payload = await render_payload(query, 'overview')
    web = payload['web']
    assert [entry['account']['account_id'] for entry in web['entries']] == ['first', 'archive']
    assert {scope['account_id'] for scope in payload['scopes']} == {'first', 'archive'}
    assert len(query.reads) == len(set(query.reads))
    assert web['now'] == int(NOW.timestamp() * 1000)
    assert all('grant_id' not in entry['account'] and 'user_id' not in entry['account'] for entry in web['entries'])


async def test_gacha_chooses_hypergryph_even_when_skland_is_present():
    query = CachedQuery()
    query.add('endfield', 'skland', 'archive', {'account': {'base': {'name': 'archive'}}})
    query.add('endfield', 'hypergryph', 'passport', {'gacha': {'schema_version': 1, 'pools': []}})
    payload = await render_payload(query, 'gacha', 'endfield')
    assert payload['web']['entries'][0]['account']['provider'] == 'hypergryph'
    assert payload['scopes'][0]['account_id'] == 'passport'


async def test_web_snapshot_envelope_is_frozen_and_removes_secrets_and_raw_errors():
    query = CachedQuery()
    query.add('nte', 'tajiduo', 'nte', {'account': {
        'nickname': '名字123456789', 'schema_version': 1, 'token': 'DO-NOT-SEND',
        'extra': {'uid': '99887766', 'cookie': 'DO-NOT-SEND', 'raw': {'nested': 'DO-NOT-SEND'}},
        'level': 70,
    }})
    query.status = lambda *args: {'state': 'ok', 'error': 'DO-NOT-SEND', 'observed_at': NOW.isoformat()}
    payload = await render_payload(query, 'summary', 'nte')
    snap = payload['web']['entries'][0]['snapshots']['account']
    assert {'payload', 'fetched_at', 'state', 'complete', 'stale', 'poll_status', 'game_id', 'capability', 'account_id', 'role_id'} <= snap.keys()
    assert snap['payload']['nickname'] == '名字***' and snap['payload']['level'] == 70
    assert 'DO-NOT-SEND' not in json.dumps(payload['web'])
    query.data[('nte', 'account')].payload['level'] = 1
    assert snap['payload']['level'] == 70
    assert not query.refreshes


async def test_nte_ledger_supplies_only_default_component_gets_without_upstream():
    query = CachedQuery()
    scope = query.add('nte', 'tajiduo', 'nte', {'gacha': {'schema_version': 1, 'pools': []}})
    calls = []
    ledger = SimpleNamespace(
        summary=lambda value: {'schema_version': 1, 'pools': [], 'token': 'HIDDEN'},
        rules=lambda value: {'rules': []},
        records=lambda *args: calls.append(args) or {'records': [], 'total': 0},
    )
    query.private = SimpleNamespace(ledger=lambda value, kind: ledger)
    payload = await render_payload(query, 'gacha', 'nte')
    prefix = '/api/accounts/nte/roles/default-role/nte/gacha/'
    assert set(payload['web']['responses']) == {
        prefix + 'summary', prefix + 'rules', prefix + 'records?pool_id=&offset=0&limit=100'}
    assert calls == [(scope, '', 100, 0)]
    assert 'HIDDEN' not in json.dumps(payload['web'])


async def test_missing_private_shards_are_not_initialized(tmp_path):
    query = CachedQuery()
    query.add('nte', 'tajiduo', 'nte', {'gacha': {'schema_version': 1, 'pools': []}})
    def forbidden(*args):
        raise AssertionError('screenshot initialized a private shard')
    query.private = SimpleNamespace(private_root=tmp_path, ledger=forbidden)
    payload = await render_payload(query, 'gacha', 'nte')
    assert payload['web']['responses'] == {}
    assert list(tmp_path.iterdir()) == []


async def test_skland_challenge_only_uses_cached_observations():
    query = CachedQuery()
    scope = query.add('endfield', 'skland', 'archive', {'account': {'base': {'name': 'archive'}}})
    calls = []
    query.private = SimpleNamespace(cached_skland=lambda value: calls.append(value) or {
        'challenge': {'supported': True, 'kind': 'war', 'records': [{'name': 'cached challenge'}]},
        'operators': {}, 'attendance': None,
    })
    payload = await render_payload(query, 'combat', 'endfield')
    assert calls == [scope]
    responses = payload['web']['responses']
    assert responses['/api/accounts/archive/roles/default-role/endfield/skland/challenges?kind=war']['body']['records'][0]['name'] == 'cached challenge'
    assert query.reads == [(scope, 'account')]


async def test_public_events_need_no_website_session_or_private_scope():
    query = CachedQuery()
    public = SimpleNamespace(read=lambda *args: QueryResult([], NOW.isoformat(), 'ok', None))
    payload = await render_payload(query, 'events', 'nte', public=public)
    assert payload['web']['entries'] == []
    assert payload['web']['publicSnapshots']['nte']['events']['payload'] == []
    assert payload['scopes'] == []


async def test_non_component_commands_stay_text_without_starting_a_browser():
    queue = CaptureQueue()
    reply = await service(CachedQuery(), queue).query_reply(IDENTITY, 'help', image_requested=True, budget_seconds=5)
    assert 'image' not in reply and not queue.results
    assert '图片暂不可用' not in reply['text']
    without_renderer = await service(CachedQuery()).query_reply(IDENTITY, 'help', image_requested=True)
    assert '图片暂不可用' not in without_renderer['text']


def test_cached_skland_accessor_does_not_instantiate_a_service_or_load_credentials():
    from game_assistant.private_routes import PrivateRoutes
    from game_assistant.endfield_skland import ScopedSkland
    scope = AccountScope('u', 'a', 'r')
    accounts = SimpleNamespace(describe=lambda value: {'version': 2}, _listeners=[])
    bundle = PrivateRoutes(accounts, None, None)
    assert bundle.cached_skland(scope) == {}
    stored = SimpleNamespace(_last_attendance={'calendar': []}, _operator_cache={'a': {'operator': {'name': 'A'}}},
                             _challenge_cache={('war', None, None, None): {'records': []}})
    bundle._skland[scope] = (2, 'grant', ScopedSkland(scope, stored))
    frozen = bundle.cached_skland(scope)
    frozen['operators']['a']['operator']['name'] = 'mutated'
    assert stored._operator_cache['a']['operator']['name'] == 'A'
    bundle._skland[scope] = (1, 'grant', ScopedSkland(scope, stored))
    assert bundle.cached_skland(scope) == {}


def test_display_data_keeps_transport_identity_but_never_credentials():
    value = display_data({'role_id': '123456789', 'nickname': '名字123456789', 'cred': 'secret',
                          'grant_token': 'secret', 'raw_data': 'secret', 'auth': 'secret'})
    assert value == {'role_id': '123456789', 'nickname': '名字***'}


def test_named_properties_and_links_cannot_smuggle_credentials_into_shared_components():
    value = display_data({'properties': [{'name': 'token', 'value': 'PRIVATE'}, {'name': '攻击', 'value': 5}],
                          'nickname': 'https://private.example/?token=PRIVATE',
                          'icon_url': 'https://web-static.kurobbs.com/icon.png', 'grant_id': 'PRIVATE'})
    assert value == {'properties': [{'name': '攻击', 'value': 5}], 'nickname': '[链接未启用]',
                     'icon_url': 'https://web-static.kurobbs.com/icon.png'}


async def test_wuwa_exact_role_freezes_observed_detail_and_reads_archive_once():
    query = CachedQuery()
    scope = query.add('wuthering_waves', 'kuro', 'wuwa', {
        'account': {'extra': {'role_id': '123456789', 'server_id': '1'}},
        'roles': [{'role_id': 42, 'name': '角色', 'level': 70}],
    })
    calls = []
    observed = {'character_id': 42, 'role_id': '123456789', 'server_id': '1', 'data': {'skill_list': []}}
    history = {'items': [{'subject': '42', 'payload': observed, 'observed_at': NOW.isoformat()}]}
    ledger = SimpleNamespace(read=lambda *args: calls.append(args) or history)
    query.private = SimpleNamespace(ledger=lambda value, kind: ledger)
    payload = await render_payload(query, 'roles', 'wuthering_waves', role_name='角色')
    path = '/api/accounts/wuwa/roles/default-role/wuwa/roles/42'
    assert payload['web']['responses'][path]['body']['payload']['character_id'] == 42
    assert payload['web']['responses'][path]['body']['payload']['data'] == {'skill_list': []}
    assert calls == [(scope, 'role_detail', 100, 0)]


async def test_ambiguous_named_role_keeps_the_existing_disambiguation_text():
    query = CachedQuery()
    query.add('nte', 'tajiduo', 'nte', {'roles': {'entries': [{'name': '同名'}, {'name': '同名'}]}})
    queue = CaptureQueue()
    reply = await service(query, queue).query_reply(
        IDENTITY, 'roles', 'nte', role_name='同名', image_requested=True, budget_seconds=5)
    assert '同名角色' in reply['text'] and 'image' not in reply and not queue.results


async def test_web_preserves_audited_weapon_and_skin_images_but_rejects_authorized_urls():
    query = CachedQuery()
    weapon = 'https://web-static.kurobbs.com/game/weapon.png'
    skin = 'https://prod-alicdn-community.kurobbs.com/game/skin.webp'
    token_image = weapon + '?token=DO-NOT-SEND'
    private = 'https://127.0.0.1/private.png?authorization=DO-NOT-SEND'
    query.add('wuthering_waves', 'kuro', 'wuwa', {
        'roles': [{'role_id': 42, 'name': '角色', 'weapon_icon': weapon, 'skin_icon': skin,
                   'icon_url': token_image, 'extra': {'link': private, 'id': private}}],
    })
    payload = await render_payload(query, 'roles', 'wuthering_waves')
    role = payload['web']['entries'][0]['snapshots']['roles']['payload'][0]
    assert role['weapon_icon'] == weapon and role['skin_icon'] == skin
    assert role['icon_url'] == '[链接未启用]'
    assert role['extra'] == {'link': '[链接未启用]', 'id': '[链接未启用]'}
    encoded = json.dumps(payload['web'])
    assert 'DO-NOT-SEND' not in encoded and token_image not in encoded and private not in encoded


async def test_query_reply_freezes_observation_clock_for_same_minute_cache_reuse():
    from game_assistant.accounts.query import PublicQueryResult
    from game_assistant.qq.rendering import SummaryRenderer
    query = CachedQuery()
    scope = query.add('nte', 'tajiduo', 'nte', {'account': {'nickname': '名字', 'level': 70}})
    clock = [NOW + timedelta(seconds=1, microseconds=123)]
    query.status = lambda *args: {'state': 'ok', 'observed_at': clock[0].isoformat()}
    def read_public(*args):
        return PublicQueryResult([], NOW.isoformat(), 'ok', None, False,
                                 {'state': 'ok', 'observed_at': clock[0].isoformat()},
                                 'community', None, None)
    queue = CaptureQueue()
    api = service(query, queue, SimpleNamespace(read=read_public))
    api.clock = lambda: clock[0]
    for elapsed in (1, 50, 61):
        clock[0] = NOW + timedelta(seconds=elapsed, microseconds=123)
        reply = await api.query_reply(IDENTITY, 'summary', 'nte', image_requested=True, budget_seconds=5)
        assert 'image' in reply
    first, second, third = queue.results
    assert first.payload['web'] == second.payload['web']
    assert first.payload['web'] != third.payload['web']
    assert first.payload['web']['entries'][0]['snapshots']['account']['poll_status']['observed_at'] == NOW.isoformat()
    assert first.payload['web']['publicSnapshots']['nte']['events']['poll_status']['observed_at'] == NOW.isoformat()
    renderer = SummaryRenderer()
    assert renderer.cache_key(scope, first) == renderer.cache_key(scope, second)
    assert renderer.cache_key(scope, first) != renderer.cache_key(scope, third)
    query.versions['nte'] += 1
    await api.query_reply(IDENTITY, 'summary', 'nte', image_requested=True, budget_seconds=5)
    assert renderer.cache_key(scope, third) != renderer.cache_key(scope, queue.results[-1])
