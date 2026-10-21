import json
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from game_assistant.api import create_app
from game_assistant.cloud_app import create_cloud_app, allow_cloud_route
from game_assistant.config import Settings
from game_assistant.system_update import GITHUB_ROOT, MAX_UPSTREAM_BYTES, SystemUpdateService, UpstreamError
from game_assistant.system_update_protocol import write_json_atomic
from game_assistant.system_update_version import capture_version
from tests.test_api import FakeRegistry
from tests.test_registry import DummyAdapter
from tests.test_identity import write
from tests.test_system_update_version import marker, SHA, OTHER
from tests.test_system_update_service import upstream


@pytest.fixture
def cloud(tmp_path):
    root = marker(tmp_path / 'install')
    state = tmp_path / 'updates'
    state.mkdir()
    settings = Settings(cloud_db_path=str(tmp_path / 'identity.db'), cloud_allowed_origins=['https://cloud.example'],
        system_update_enabled=True, system_update_install_root=str(root), system_update_state_dir=str(state))
    app = create_cloud_app(settings, start_scheduler=False)
    admin = app.state.identity.bootstrap_admin('admin', 'Admin-password-123')
    updater = app.state.system_update
    updater.version = capture_version(root)
    app.state.running_version = updater.version
    updater.platform = 'linux'
    updater.clock = lambda: 2000
    updater.fetch = upstream()
    write_json_atomic(state / 'worker.json', {'schema':1,'pid':123,'platform':'linux','updated_at':2000})
    with TestClient(app, base_url='https://cloud.example') as client:
        yield app, client, admin, state


def login(client):
    response = write(client, '/api/identity/login', {'username':'admin','password':'Admin-password-123'})
    assert response.status_code == 200


def test_all_three_cloud_update_endpoints_require_admin_and_existing_csrf(cloud):
    app, client, admin, _ = cloud
    assert client.get('/api/system/update').status_code == 401
    assert client.post('/api/system/update/check', json={}).status_code == 401
    assert client.post('/api/system/update/apply', json={'expected_sha':SHA,'target_sha':OTHER}).status_code == 401
    invite = app.state.identity.create_invite(admin)
    assert write(client, '/api/identity/register', {'username':'alice','password':'Password-alice-123','invite':invite}).status_code == 200
    assert client.get('/api/system/update').status_code == 403
    for path, body in [('/check',{}),('/apply',{'expected_sha':SHA,'target_sha':OTHER})]:
        assert write(client, '/api/system/update'+path, body).json()['detail'] == 'admin_required'
    login(client)
    assert client.post('/api/system/update/check', json={}).status_code == 403
    assert client.post('/api/system/update/apply', json={'expected_sha':SHA,'target_sha':OTHER}).status_code == 403
    checked = write(client, '/api/system/update/check', {})
    assert checked.status_code == 200 and checked.json()['can_apply']
    queued = write(client, '/api/system/update/apply', {'expected_sha':SHA,'target_sha':OTHER})
    assert queued.status_code == 200 and queued.json()['job']['phase'] == 'queued'
    assert queued.json()['repository'] == 'miyako-md/game-manage'
    for response in (checked, queued, client.get('/api/system/update')):
        payload = response.json()
        assert set(payload) == {'repository','branch','current','latest','relation','checked_at',
                                'check_error','stale','can_apply','unavailable_reason','job','worker_available'}
        assert payload['repository'] == 'miyako-md/game-manage' and payload['branch'] == 'main'
        assert set(payload['current']) == {'sha','frontend_sha','dirty'}
        assert set(payload['latest']) == {'sha','message','committed_at','url'}


def test_no_client_repository_ref_url_command_or_query_parameters_reach_network(cloud):
    app, client, _, _ = cloud
    login(client)
    calls = []
    app.state.system_update.fetch = lambda url: calls.append(url)
    for path in ['/api/system/update?repository=other/repo','/api/system/update?ref=feature']:
        response = client.get(path)
        assert response.status_code == 400 and response.json()['error_code'] == 'invalid_request'
    for body in [{'repository':'other/repo'},{'branch':'feature'},{'url':'https://evil.example'},{'command':'whoami'}]:
        assert write(client, '/api/system/update/check', body).status_code == 422
    for body in [{'expected_sha':SHA,'target_sha':'main'}, {'expected_sha':SHA,'target_sha':OTHER,'command':'whoami'}]:
        assert write(client, '/api/system/update/apply', body).status_code == 422
    assert calls == []


def test_get_is_cache_only_and_rejected_apply_returns_frontend_error_code(cloud):
    app, client, _, _ = cloud
    login(client)
    calls = []
    fetch = app.state.system_update.fetch
    app.state.system_update.fetch = lambda url: (calls.append(url), fetch(url))[1]
    write(client, '/api/system/update/check', {})
    assert len(calls) == 1
    for _ in range(3):
        assert client.get('/api/system/update').json()['can_apply']
    assert len(calls) == 1
    response = write(client, '/api/system/update/apply', {'expected_sha':OTHER,'target_sha':OTHER})
    assert response.status_code == 409
    assert response.json() == {'detail':'running_version_mismatch','error_code':'running_version_mismatch'}


def test_local_routes_keep_global_loopback_origin_and_write_header_boundary(tmp_path):
    settings = Settings(db_path=str(tmp_path/'assistant.db'), auth_store_path=str(tmp_path/'credentials.json'),
                        wuwa_enabled=False, nte_enabled=False, endfield_enabled=False, lol_enabled=False)
    app = create_app(registry=FakeRegistry(DummyAdapter()), settings=settings, start_scheduler=False)
    app.state.system_update.fetch = upstream()
    app.state.system_update.version = capture_version(marker(tmp_path / 'local-release'))
    app.state.running_version = app.state.system_update.version
    with TestClient(app, base_url='http://127.0.0.1:8010') as client:
        assert client.get('/api/system/update').status_code == 200
        assert client.get('/api/system/update', headers={'Host':'evil.example'}).status_code == 403
        assert client.post('/api/system/update/check', json={}).status_code == 403
        assert client.post('/api/system/update/check', json={}, headers={'X-Game-Assistant':'1','Origin':'https://evil.example'}).status_code == 403
        assert client.post('/api/system/update/check', json={}, headers={'X-Game-Assistant':'1'}).status_code == 200
        response = client.get('/api/health')
        assert response.status_code == 200 and response.json()['status'] == 'ok'
        assert response.json()['service'] == 'game-assistant'
        assert set(response.json()['version']) == {'commit','frontend_commit'}
        assert response.json()['ready'] is True
        marker(tmp_path / 'local-release', OTHER)
        changed = client.get('/api/health').json()
        assert changed['status'] == 'ok' and changed['ready'] is False
        assert changed['version'] == {'commit':SHA,'frontend_commit':OTHER}
        marker(tmp_path / 'local-release', SHA)
        app.state.store._conn.close()
        degraded = client.get('/api/health')
        assert degraded.status_code == 200 and degraded.json()['status'] == 'ok'
        assert degraded.json()['ready'] is False


def worker_status(state, phase, **patch):
    write_json_atomic(state/'status.json', {'schema':1,'job_id':'d'*32,'target_sha':OTHER,
        'previous_sha':SHA,'phase':phase,'updated_at':2000,**patch})


def test_preparing_serves_normally_but_verifying_gates_business_writes_and_checks_until_terminal(cloud):
    app, client, _, state = cloud
    writes = []
    @app.post('/api/business-write')
    def business():
        writes.append('saved')
        return {'saved':True}
    allow_cloud_route(app, '/api/business-write', ['POST'])
    login(client)
    csrf = client.get('/api/identity/csrf').json()['csrf_token']
    headers = {'X-CSRF-Token':csrf}
    worker_status(state, 'preparing')
    assert client.post('/api/business-write', json={}, headers=headers).status_code == 200
    assert writes == ['saved']
    worker_status(state, 'verifying')
    for path in ['/api/business-write','/api/system/update/check']:
        response = client.post(path, json={}, headers=headers)
        assert response.status_code == 503 and response.json()['error_code'] == 'update_in_progress'
    assert writes == ['saved']
    health = client.get('/api/health')
    assert health.status_code == 200 and health.json()['ready'] is True
    assert health.json()['version'] == {'commit':SHA,'frontend_commit':SHA}
    assert client.get('/api/system/update').json()['job']['phase'] == 'verifying'
    for phase in ['completed','failed','rolled_back']:
        worker_status(state, phase)
        assert client.post('/api/business-write', json={}, headers=headers).status_code == 200
    assert len(writes) == 4


def test_maintenance_does_not_grant_ordinary_users_update_status_access(cloud):
    app, client, admin, state = cloud
    invite = app.state.identity.create_invite(admin)
    assert write(client, '/api/identity/register', {'username':'alice','password':'Password-alice-123','invite':invite}).status_code == 200
    worker_status(state, 'verifying')
    response = client.get('/api/system/update')
    assert response.status_code == 403 and response.json()['detail'] == 'admin_required'


def test_invalid_or_unknown_managed_status_blocks_business_until_recovered(cloud):
    app, client, _, state = cloud
    login(client)
    assert client.get('/api/identity/me').status_code == 200
    for patch in [{'schema':True},{'schema':2},{'job_id':'not-a-job'},{'phase':[]}]:
        worker_status(state, **{'phase':'verifying',**patch})
        assert client.get('/api/identity/me').status_code == 503
        assert not client.get('/api/system/update').json()['can_apply']
        assert client.get('/api/health').status_code == 200
    (state/'status.json').write_text('{broken')
    assert client.get('/api/identity/me').status_code == 503
    worker_status(state, 'rolled_back')
    assert client.get('/api/identity/me').status_code == 200


def test_unreadable_managed_status_never_opens_business_routes(cloud, monkeypatch):
    from game_assistant import system_update
    app, client, _, state = cloud
    login(client)
    worker_status(state, 'verifying')
    original = system_update.read_json
    def unreadable(path, *args, **kwargs):
        if Path(path) == state/'status.json':
            raise PermissionError('status temporarily unreadable')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(system_update, 'read_json', unreadable)
    response = client.get('/api/identity/me')
    assert response.status_code == 503 and response.json()['error_code'] == 'update_in_progress'
    assert response.headers['retry-after'] == '2'
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/system/update').json()['unavailable_reason'] == 'state_unavailable'


@respx.mock
def test_upstream_requests_are_https_fixed_bounded_and_never_follow_redirects():
    endpoint = GITHUB_ROOT+'/commits/main?per_page=1'
    route = respx.get(endpoint).mock(return_value=httpx.Response(200, json={'sha':SHA}))
    assert SystemUpdateService._fetch(endpoint) == {'sha':SHA}
    assert route.called
    for content in [b'[]', b'{' + b'a'*(MAX_UPSTREAM_BYTES+1)]:
        route.mock(return_value=httpx.Response(200, content=content))
        with pytest.raises(UpstreamError, match='github_invalid_response'):
            SystemUpdateService._fetch(endpoint)
    route.mock(return_value=httpx.Response(302, headers={'Location':'https://evil.example'}))
    with pytest.raises(UpstreamError):
        SystemUpdateService._fetch(endpoint)
    with pytest.raises(UpstreamError):
        SystemUpdateService._fetch('https://evil.example/commits/main')
