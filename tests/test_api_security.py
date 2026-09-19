import pytest
from fastapi.testclient import TestClient

from game_assistant.api import create_app
from game_assistant.config import Settings
from game_assistant.snapshots import SnapshotStore
from tests.test_api import FakeRegistry
from tests.test_registry import DummyAdapter


@pytest.fixture
def local_client(tmp_path):
    settings = Settings(db_path=str(tmp_path / 'db'))
    store = SnapshotStore(settings.db_path)
    store.save('dummy', 'stamina', '{"current":19}')
    app = create_app(registry=FakeRegistry(DummyAdapter()), store=store,
                     settings=settings, start_scheduler=False)
    return TestClient(app, base_url='http://127.0.0.1:8010')


@pytest.mark.parametrize('headers', [
    {}, {'Origin': 'https://evil.example'},
    {'Origin': 'http://127.0.0.1:8010'},
    {'Origin': 'null', 'X-Game-Assistant': '1'},
    {'Origin': '', 'X-Game-Assistant': '1'},
    {'Origin': 'https://evil.example', 'X-Game-Assistant': '1'},
    {'Origin': 'http://localhost:5173.evil.example', 'X-Game-Assistant': '1'},
])
def test_refresh_rejects_cross_site_forms_and_missing_header(local_client, headers):
    response = local_client.post('/api/games/dummy/refresh', data={'refresh': '1'}, headers=headers)
    assert response.status_code == 403


@pytest.mark.parametrize('host', [
    'evil.example', 'localhost.evil.example', '127.0.0.1.evil.example',
    'testserver', 'localhost@evil.example', 'evil.example@localhost',
    'localhost:bad', 'localhost:99999', 'localhost/path', '[::1',
])
@pytest.mark.parametrize('path', ['/api/health', '/api/games/dummy/snapshot/stamina', '/api/wuwa/gacha'])
def test_api_reads_reject_untrusted_or_malformed_host(local_client, host, path):
    response = local_client.get(path, headers={'Host': host})
    assert response.status_code == 403


@pytest.mark.parametrize('host', ['localhost:8010', '127.0.0.1:8010', '[::1]:8010'])
def test_local_reads_need_no_custom_header_and_are_not_cached(local_client, host):
    response = local_client.get('/api/games/dummy/snapshot/stamina', headers={'Host': host})
    assert response.status_code == 200
    assert response.json()['payload']['current'] == 19
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('origin', [None, 'http://127.0.0.1:8010', 'http://localhost:5173'])
def test_cli_and_configured_ui_refresh_work(local_client, origin):
    headers = {'X-Game-Assistant': '1'}
    if origin is not None:
        headers['Origin'] = origin
    response = local_client.post('/api/games/dummy/refresh', headers=headers)
    assert response.status_code == 200
    assert 'stamina' in response.json()['results']


def test_duplicate_host_or_origin_cannot_hide_hostile_value(local_client):
    for headers in [
        [('Host', 'localhost'), ('Host', 'evil.example')],
        [('Origin', 'http://localhost:8010'), ('Origin', 'https://evil.example')],
    ]:
        assert local_client.get('/api/games', headers=headers).status_code == 403


def test_explicit_custom_origin_allows_only_its_exact_host(tmp_path):
    settings = Settings(db_path=str(tmp_path / 'db'), auth_allowed_origins=['https://assistant.example'])
    app = create_app(registry=FakeRegistry(DummyAdapter()), settings=settings, start_scheduler=False)
    client = TestClient(app, base_url='https://assistant.example')
    assert client.get('/api/health').status_code == 200
    assert client.post('/api/games/dummy/refresh', headers={
        'Origin': 'https://assistant.example', 'X-Game-Assistant': '1'}).status_code == 200
    assert client.post('/api/games/dummy/refresh', headers={
        'Origin': 'https://assistant.example:0', 'X-Game-Assistant': '1'}).status_code == 403
    assert client.get('/api/health', headers={'Host': 'assistant.example.evil.example'}).status_code == 403
