"""Cloud public tools use synthetic persisted sources and the real HTTP boundary."""
import json
import sqlite3
import httpx
from datetime import datetime, timezone

import pytest
import respx
from fastapi.testclient import TestClient

from game_assistant.cloud_app import create_cloud_app
from game_assistant.nte_guides_catalog import SOURCES
from game_assistant.wuwa_guide_updates import Search
from tests.test_account_queries import cloud_settings
from tests.test_identity import write


@pytest.fixture
def cloud(tmp_path):
    app = create_cloud_app(cloud_settings(tmp_path), start_scheduler=False)
    admin = app.state.identity.bootstrap_admin('admin', 'Admin-password-123')
    with respx.mock(assert_all_called=False) as upstream, TestClient(app, base_url='https://cloud.example') as client:
        yield app, client, admin, upstream


def login(client, username='admin'):
    assert write(client, '/api/identity/login', {'username': username,
        'password': 'Admin-password-123' if username == 'admin' else 'Password-alice-123'}).status_code == 200


def seed(app):
    def save():
        post_id = next(iter(SOURCES))
        app.state.nte_guides.save(post_id, {'id': post_id, 'fingerprint': SOURCES[post_id]['fingerprint'],
            'title': '合成攻略', 'images': [], 'paragraphs': ['合成内容'],
            'fetched_at': datetime.now(timezone.utc).isoformat()})
        app.state.wuwa_guide_updates.save(Search(character_id='1', name='测试'), {
            'character_id': '1', 'name': '测试', 'attribute': '', 'candidates': [],
            'checked_at': None, 'attempted_at': None, 'error': None, 'limited': False})
        ef = app.state.endfield_public
        ef._put('news', [{'id': '1', 'title': '合成公告'}])
        ef._put('calendar', {'version': '1.0', 'events': []})
        ef._put('tree', [{'id': 'map1', 'name': '合成区域', 'levels': []}])
        ef._put('catalog', [{'id': 'main', 'name': '资源分类', 'subTypes': [{'id': 'sub', 'name': '资源'}]}])
        ef._put('mark-info:map1:mark1', {'id': 'mark1', 'desc': '合成点位'})
        return post_id
    return save


def test_public_tools_require_login_and_preserve_local_response(cloud):
    app, client, admin, _ = cloud
    post_id = client.portal.call(seed(app))
    paths = ['/api/public/nte/guides', f'/api/public/nte/guides/sources/{post_id}',
        '/api/public/wuwa/guides/updates?character_id=1&name=测试',
        '/api/public/endfield/public', '/api/public/endfield/map',
        '/api/public/endfield/map/marks/mark1?map_id=map1']
    for path in paths:
        assert client.get(path).status_code == 401
    invite = app.state.identity.create_invite(admin)
    assert write(client, '/api/identity/register', {'username': 'alice',
        'password': 'Password-alice-123', 'invite': invite}).status_code == 200
    for path in paths:
        assert client.get(path).status_code == 200
    assert client.get(paths[1]).json()['paragraphs'] == ['合成内容']
    assert 'active_guide' in client.get(paths[2]).json()
    assert client.get(paths[3]).json()['news']['items'][0]['title'] == '合成公告'
    assert client.get(paths[4]).json()['maps'][0]['name'] == '合成区域'
    assert client.get(paths[5]).json()['info']['desc'] == '合成点位'
    assert client.get('/api/public/nte/guides/sources/999999999').status_code == 404
    assert client.get('/api/public/endfield/map?offset=-1').status_code == 400
    assert client.get('/api/public/endfield/map/marks/a?map_id=../bad').status_code == 400


@pytest.mark.parametrize('path,payload', [
    ('/api/admin/nte/guides/sources/1/refresh', {}),
    ('/api/admin/wuwa/guides/updates', {'character_id': '1', 'name': '测试'}),
    ('/api/admin/wuwa/guides/updates/extract', {'character_id': '1', 'name': '测试', 'post_id': '1'}),
    ('/api/admin/wuwa/guides/tower/check', {}),
    ('/api/admin/endfield/public/refresh', {}),
])
def test_maintenance_requires_admin_and_csrf(cloud, path, payload):
    app, client, admin, _ = cloud
    invite = app.state.identity.create_invite(admin)
    assert write(client, '/api/identity/register', {'username': 'alice',
        'password': 'Password-alice-123', 'invite': invite}).status_code == 200
    assert write(client, path, payload).status_code == 403
    login(client)
    assert client.post(path, json=payload).status_code == 403
    assert client.put(path, json=payload).status_code == 404


def test_public_tools_close_and_reinstall_without_stale_routes(tmp_path):
    app = create_cloud_app(cloud_settings(tmp_path), start_scheduler=False)
    for _ in range(2):
        with TestClient(app, base_url='https://cloud.example') as client:
            service = app.state.endfield_public
            assert client.get('/api/public/nte/guides').status_code == 401
        with pytest.raises(sqlite3.ProgrammingError):
            service._get('news')
    assert not any(regex.fullmatch('/api/public/nte/guides') for regex, _, _ in app.state.cloud_route_policy)


def test_failed_nte_refresh_retains_success_for_both_users(cloud):
    from tests.test_nte_guides import URL
    app, client, admin, upstream = cloud
    post_id = client.portal.call(seed(app))
    login(client)
    upstream.get(URL).mock(return_value=httpx.Response(503))
    result = write(client, f'/api/admin/nte/guides/sources/{post_id}/refresh', {}).json()
    assert result['stale'] and result['error'] and result['paragraphs'] == ['合成内容']
    invite = app.state.identity.create_invite(admin)
    assert write(client, '/api/identity/register', {'username': 'alice',
        'password': 'Password-alice-123', 'invite': invite}).status_code == 200
    assert client.get(f'/api/public/nte/guides/sources/{post_id}').json()['paragraphs'] == ['合成内容']


def test_failed_map_upstream_is_cooled_down_and_retains_cached_rows(cloud):
    from game_assistant.endfield_public import MAP_API
    app, client, _, upstream = cloud
    def save():
        seed(app)()
        ef = app.state.endfield_public
        ef._put('marks:map1:', {'marks': [{'id': 'm', 'templateId': 't', 'pos': {'x': 1}}],
            'markTemplates': [{'id': 't', 'name': '旧资源'}]})
        ef.conn.execute("UPDATE cache SET fetched_at='2020-01-01T00:00:00+00:00'")
        ef.conn.commit()
    client.portal.call(save)
    login(client)
    calls = upstream.get(url__startswith=MAP_API).mock(return_value=httpx.Response(503))
    for _ in range(3):
        data = client.get('/api/public/endfield/map?map_id=map1').json()
        assert data['stale'] and data['error'] and data['marks'][0]['name'] == '旧资源'
    assert calls.call_count == 3  # tree, catalog, mark/list once each


def test_endfield_total_timeout_returns_last_good_news(cloud, monkeypatch):
    import asyncio
    from game_assistant.cloud_public_tools import CloudPublicTools
    from game_assistant.endfield_public import EndfieldPublicService
    app, client, _, upstream = cloud
    client.portal.call(seed(app))
    login(client)
    original = EndfieldPublicService._request
    started, finished = [], []
    async def slow(self, url, params=None):
        started.append(url)
        await asyncio.sleep(1)
        finished.append(url)
        return await original(self, url, params)
    monkeypatch.setattr(EndfieldPublicService, '_request', slow)
    monkeypatch.setattr(CloudPublicTools, 'TIMEOUT', .01, raising=False)
    upstream.get('https://endfield.hypergryph.com/news').mock(return_value=httpx.Response(503))
    response = write(client, '/api/admin/endfield/public/refresh', {})
    # The deadline cancels the slow request; a wall-clock bound measured runner load instead.
    assert started and not finished
    assert response.status_code == 200
    data = response.json()
    assert data['news']['items'][0]['title'] == '合成公告'
    assert data['news']['stale'] and data['news']['error']
    assert write(client, '/api/admin/endfield/public/refresh', {}).status_code == 429


def test_varied_map_detail_requests_have_aggregate_upstream_budget(cloud):
    from game_assistant.endfield_public import MAP_API
    app, client, _, upstream = cloud
    login(client)
    calls = upstream.get(url__startswith=MAP_API).mock(return_value=httpx.Response(503))
    for number in range(35):
        response = client.get(f'/api/public/endfield/map/marks/mark{number}?map_id=map1')
        assert response.status_code == 200
        assert response.json()['error'] and response.json()['info'] is None
    assert calls.call_count == 32


async def test_timeout_cache_fallback_does_not_wait_indefinitely_for_another_reader(tmp_path, monkeypatch):
    import asyncio
    from fastapi import HTTPException
    from game_assistant.cloud_public_tools import CloudPublicTools
    from game_assistant.config import Settings
    monkeypatch.setattr(CloudPublicTools, 'TIMEOUT', .01)
    monkeypatch.setattr(CloudPublicTools, 'FALLBACK_TIMEOUT', .01, raising=False)
    tools = CloudPublicTools(Settings(db_path=str(tmp_path / 'public.db')))
    try:
        async with tools.endfield.lock:
            with pytest.raises(HTTPException) as error:
                await asyncio.wait_for(tools.read_endfield(tools.endfield.public), .2)
            assert error.value.status_code == 503
    finally:
        tools.close()


def test_admin_wuwa_search_failure_preserves_cached_candidates(cloud):
    from game_assistant.wuwa_guide_updates import SEARCH_URL
    app, client, _, upstream = cloud
    query = {'character_id': '1', 'name': '测试', 'attribute': ''}
    def save():
        app.state.wuwa_guide_updates.save(Search(**query), {**query, 'candidates': [{'id': '1', 'kind': 'article'}],
            'checked_at': '2026-01-01T00:00:00+00:00', 'attempted_at': None, 'error': None, 'limited': False})
    client.portal.call(save)
    login(client)
    upstream.post(SEARCH_URL).mock(return_value=httpx.Response(503))
    response = write(client, '/api/admin/wuwa/guides/updates', query)
    assert response.status_code == 200
    assert response.json()['error'] and response.json()['candidates'][0]['id'] == '1'
    assert client.get('/api/public/wuwa/guides/updates', params=query).json()['candidates'][0]['id'] == '1'


def test_wuwa_tower_guides_need_login_and_admin_failure_keeps_cache(cloud):
    from datetime import timedelta
    from game_assistant.wuwa_guide_updates import SEARCH_URL
    app, client, _, upstream = cloud
    now = datetime.now(timezone.utc)
    guide = {'id': '1', 'periodStart': (now - timedelta(days=1)).isoformat(),
             'periodEnd': (now + timedelta(days=27)).isoformat()}
    client.portal.call(lambda: app.state.wuwa_tower_guides.save({'guides': [guide],
        'checked_at': (now - timedelta(hours=2)).isoformat(), 'attempted_at': (now - timedelta(hours=2)).isoformat(),
        'error': None}))
    route = upstream.post(SEARCH_URL).mock(return_value=httpx.Response(503))
    assert client.get('/api/public/wuwa/guides/tower').status_code == 401
    login(client)
    assert client.get('/api/public/wuwa/guides/tower').json()['guides'][0]['id'] == '1'
    assert route.call_count == 0
    response = write(client, '/api/admin/wuwa/guides/tower/check', {})
    assert response.status_code == 200 and route.call_count == 1
    assert response.json()['error'] and response.json()['guides'][0]['id'] == '1'
    assert write(client, '/api/admin/wuwa/guides/tower/check', {}).status_code == 429


def test_scoped_history_backfill_uses_only_owned_current_snapshots(tmp_path):
    from tests.test_private_data_isolation import cloud_fixture, A, B
    from game_assistant.snapshots import SnapshotStore
    client, app, bundle, db = cloud_fixture(tmp_path, 'wuthering_waves', 'kuro')
    credentials = bundle.accounts.credentials
    credentials.key_path.write_bytes(b'x' * 32)
    credentials.key_path.chmod(0o600)
    for scope in (A, B):
        info = bundle.accounts.describe(scope)
        credentials.save_grant(scope.user_id, info['grant_id'], {
            'user_id': 'synthetic-user', 'role_id': info['game_uid'],
            'server_id': info['server'], 'token': 'synthetic-token',
        }, info['version'])
    snapshots = SnapshotStore(str(tmp_path / 'snapshots.db'))
    bundle.snapshots = snapshots
    def roles(level):
        return json.dumps([{'role_id': '1', 'level': level, 'extra': {
            'account_role_id': '77', 'server_id': bundle.accounts.describe(A)['server']}}])
    version = bundle.accounts.describe(A)['version']
    snapshots.save_scoped(A, 'roles', roles(10), version)
    snapshots.save_scoped(B, 'roles', roles(99), version)
    snapshots.save('wuthering_waves', 'roles', roles(80))
    path = f'/api/accounts/{A.account_id}/roles/{A.role_id}/wuwa/history/backfill'
    assert client.post(path, json={'path': 'C:/private'}).status_code == 422
    response = client.post(path, json={})
    assert response.status_code == 200
    assert response.json()['inserted'] == 1 and response.json()['complete'] is False
    assert response.json()['sources'] == ['scoped_snapshot']
    assert bundle.ledger(A, 'wuwa_history').read(A, 'roles')['items'][0]['payload']['level'] == 10
    assert client.post(path.replace(A.account_id, B.account_id).replace(A.role_id, B.role_id), json={}).status_code == 404
    assert client.post(path, json={}).json()['inserted'] == 0
    snapshots.save_scoped(A, 'roles', roles(20), version + 1)
    assert client.post(path, json={}).json()['inserted'] == 0
    bundle.close()
    snapshots._conn.close()
    db.close()


def test_cloud_backfill_csrf_and_two_website_users(cloud):
    from game_assistant.identity.models import Principal
    app, client, admin, _ = cloud
    paths = []
    for username, level in (('alice', 10), ('bob', 90)):
        invite = app.state.identity.create_invite(admin)
        registered = write(client, '/api/identity/register', {'username': username,
            'password': 'Password-alice-123', 'invite': invite})
        assert registered.status_code == 200
        user = registered.json()['user_id']
        def save():
            row = app.state.accounts.save_verified(Principal(user, False), 'kuro', {
                'user_id': 'same-upstream-user', 'role_id': '77', 'server_id': '1', 'token': 'synthetic'})
            scope = app.state.accounts.require_scope(Principal(user, False), row['account_id'], row['role_id'])
            payload = [{'role_id': '1', 'level': level, 'extra': {'account_role_id': '77', 'server_id': '1'}}]
            app.state.store.save_scoped(scope, 'roles', json.dumps(payload), app.state.accounts.describe(scope)['version'])
            return f'/api/accounts/{scope.account_id}/roles/{scope.role_id}/wuwa/history'
        paths.append(client.portal.call(save))
        assert client.post(paths[-1] + '/backfill', json={}).status_code == 403
        assert write(client, paths[-1] + '/backfill', {}).json()['inserted'] == 1
        assert client.get(paths[-1], params={'kind': 'roles'}).json()['items'][0]['payload']['level'] == level
    assert write(client, paths[0] + '/backfill', {}).status_code == 404
    assert client.get(paths[0], params={'kind': 'roles'}).status_code == 404


def test_public_cache_files_roundtrip_backup(tmp_path):
    from scripts.cloud.backup import backup
    from scripts.cloud.restore import restore
    from tests.test_cloud_operations import fixture
    root, identity, key, _ = fixture(tmp_path)
    for name in ('public.nte-guides.sqlite3', 'public.wuwa-guides.sqlite3'):
        with sqlite3.connect(root / name) as db:
            db.execute('CREATE TABLE synthetic(value TEXT)')
            db.execute("INSERT INTO synthetic VALUES ('preserved')")
    backup(root, identity, tmp_path / 'backup', key)
    restore(tmp_path / 'backup', tmp_path / 'restored', key)
    for name in ('public.nte-guides.sqlite3', 'public.wuwa-guides.sqlite3'):
        with sqlite3.connect(tmp_path / 'restored/data' / name) as db:
            assert db.execute('SELECT value FROM synthetic').fetchone()[0] == 'preserved'
