import importlib.util
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from game_assistant.snapshots import SnapshotStore
from tests.test_wuwa_routes import Auth
from tests.test_wuwa_gacha import record


def make_client(tmp_path):
    assert importlib.util.find_spec('game_assistant.wuwa_archive_routes'), 'archive routes missing'
    from game_assistant.wuwa_archive_routes import install_wuwa_archive_routes
    app = FastAPI()
    adapter = SimpleNamespace(credentials_configured=True, _settings=SimpleNamespace(
        wuwa_user_id='community', wuwa_role_id='100', wuwa_server_id='S'))
    app.state.registry = SimpleNamespace(get=lambda _: adapter)
    app.state.auth = Auth()
    app.state.store = SnapshotStore(str(tmp_path / 'db'))
    app.state.settings = SimpleNamespace(auth_allowed_origins=['http://testserver'])
    install_wuwa_archive_routes(app)
    return TestClient(app), app, adapter


def test_private_reads_empty_backfill_no_network_and_logout(tmp_path, monkeypatch):
    client, app, adapter = make_client(tmp_path)
    from game_assistant import wuwa_archive_routes as routes
    async def forbidden(*a, **kw):
        raise AssertionError('only explicit import may request gacha')
    monkeypatch.setattr(routes, 'fetch_official', forbidden)
    assert client.get('/api/wuwa/gacha').json()['state'] == 'need_import'
    assert client.get('/api/wuwa/history?kind=tower').json()['items'] == []
    result = client.post('/api/wuwa/history/backfill', json={}, headers={'X-Game-Assistant': '1'})
    assert result.json()['inserted'] == 0
    assert result.json()['complete'] is False
    assert client.get('/api/wuwa/history?kind=other').status_code == 422
    adapter.credentials_configured = False
    for path in ['/api/wuwa/gacha', '/api/wuwa/history?kind=roles']:
        assert client.get(path).status_code == 401


def test_write_guard_body_limit_identity_and_secret_errors(tmp_path):
    client, app, adapter = make_client(tmp_path)
    path = '/api/wuwa/gacha/import'
    body = {'records': {'info': {'uid': '100'}, 'list': [record()]}}
    assert client.post(path, json=body).status_code == 403
    headers = {'X-Game-Assistant': '1', 'Origin': 'https://evil.test'}
    assert client.post(path, json=body, headers=headers).status_code == 403
    headers['Origin'] = 'http://testserver'
    assert client.post(path, json=body, headers=headers).json()['inserted'] == 1
    assert client.get('/api/wuwa/gacha').json()['total'] == 1
    response = client.post(path, content=b'x' * (2 * 1024 * 1024 + 1), headers=headers)
    assert response.status_code == 413
    response = client.post(path, content=b'x' * (2 * 1024 * 1024 + 1),
                           headers={**headers, 'Content-Length': '1'})
    assert response.status_code == 413
    response = client.post(path, json={'url': 'https://evil.test/SECRET'}, headers=headers)
    assert response.status_code == 422 and 'SECRET' not in response.text
    response = client.post(path, json={'url': ['SECRET']}, headers=headers)
    assert response.status_code == 422 and 'SECRET' not in response.text
    body['records']['info']['uid'] = '101'
    assert client.post(path, json=body, headers=headers).status_code == 422
    adapter._settings.wuwa_role_id = '101'
    assert client.get('/api/wuwa/gacha').json()['total'] == 0
    assert client.get('/api/wuwa/gacha').headers['cache-control'] == 'no-store'
    assert client.get('/api/wuwa/gacha?limit=501').status_code == 422


def test_import_session_switch_discards_inflight_rows(tmp_path, monkeypatch):
    client, app, adapter = make_client(tmp_path)
    from game_assistant import wuwa_archive_routes as routes
    async def switched(*a):
        app.state.auth.generation += 1
        return {'records': {'info': {'uid': '100'}, 'list': [record()]}, 'failed_pools': []}
    monkeypatch.setattr(routes, 'fetch_official', switched)
    response = client.post('/api/wuwa/gacha/import', json={'url': 'transient'}, headers={'X-Game-Assistant': '1'})
    assert response.status_code == 409
    assert client.get('/api/wuwa/gacha').json()['total'] == 0


def test_actual_role_detail_read_archives_only_success(tmp_path):
    from game_assistant.adapters.wuthering_waves.routes import install_wuwa_routes
    from game_assistant.models import FetchResult
    client, app, adapter = make_client(tmp_path)
    async def detail(character):
        return FetchResult(ok=True, payload={'role_id': '100', 'server_id': 'S',
            'character_id': character, 'data': {'level': 0}, 'provenance': {'fetched_at': 'source-time'}})
    adapter.fetch_role_detail = detail
    install_wuwa_routes(app)
    assert client.get('/api/wuwa/roles/1501').status_code == 200
    rows = client.get('/api/wuwa/history?kind=role_detail').json()['items']
    assert len(rows) == 1 and rows[0]['source_at'] == 'source-time'
    async def failed(character):
        return FetchResult(ok=False, error='source failure')
    adapter.fetch_role_detail = failed
    assert client.get('/api/wuwa/roles/1501').status_code == 502
    assert len(client.get('/api/wuwa/history?kind=role_detail').json()['items']) == 1
