import httpx
import pytest

from game_assistant.cloud_app import allow_cloud_route, create_cloud_app, source_ip
from game_assistant.config import Settings
from tests.test_identity import identity, register


def test_cloud_routes_fail_closed(identity):
    settings, _, _, client = identity
    @client.app.get('/api/private/new')
    def unclassified():
        return {'secret': 'leaked'}
    for path in ['/api/private/new', '/api/wuwa/gacha', '/api/lol/collect', '/docs', '/openapi.json', '/api/identity/bootstrap']:
        assert client.get(path).status_code == 404
    health = client.get('/api/health')
    assert health.status_code == 200 and health.json()['status'] == 'ok'
    assert set(health.json()['version']) == {'commit', 'frontend_commit'}
    assert isinstance(health.json()['ready'], bool)
    assert client.get('/api/identity/me').status_code == 401
    register(identity)
    assert client.get('/api/private/new').status_code == 404


def test_internal_service_cannot_use_cookie(identity):
    client = identity[3]
    @client.app.get('/internal/test')
    def internal():
        return {'secret': 'leaked'}
    allow_cloud_route(client.app, '/internal/test', ['GET'], access='service')
    register(identity)
    assert client.get('/internal/test').status_code == 401
    client.app.state.service_authenticator = lambda request: (
        'trusted-service' if request.headers.get('authorization') == 'Bearer test-service-only' else None)
    assert client.get('/internal/test').status_code == 401
    assert client.get('/internal/test', headers={'Authorization': 'Bearer invalid'}).status_code == 401
    assert client.get('/internal/test', headers={'Authorization': 'Bearer test-service-only'}).status_code == 200


def test_explicit_user_route_still_requires_csrf(identity):
    client = identity[3]
    @client.app.post('/api/extra')
    def extra():
        return {'ok': True}
    allow_cloud_route(client.app, '/api/extra', ['POST'])
    assert client.post('/api/extra').status_code == 401
    register(identity)
    assert client.post('/api/extra').status_code == 403


@pytest.mark.parametrize('headers', [
    {'Host': 'evil.example'}, {'Host': 'cloud.example:0'}, {'Origin': 'https://evil.example'},
    {'Origin': 'null'}, {'Sec-Fetch-Site': 'cross-site'},
    [('Origin', 'https://cloud.example'), ('Origin', 'https://evil.example')],
])
def test_host_origin_and_csrf_issuance_are_restricted(identity, headers):
    assert identity[3].get('/api/identity/csrf', headers=headers).status_code == 403


@pytest.mark.asyncio
async def test_streaming_body_limit_without_content_length(identity):
    app = identity[3].app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='https://cloud.example') as client:
        token = (await client.get('/api/identity/csrf')).json()['csrf_token']
        async def chunks():
            for _ in range(20):
                yield b'x' * 8192
        response = await client.post('/api/identity/login', content=chunks(),
                                     headers={'X-CSRF-Token': token, 'Content-Length': '1'})
        assert response.status_code == 413


def test_cloud_database_does_not_touch_local_database(tmp_path):
    local = tmp_path / 'local.db'
    local.write_bytes(b'local data')
    create_cloud_app(Settings(db_path=str(local), cloud_db_path=str(tmp_path / 'cloud.db')),
                     start_scheduler=False)
    assert local.read_bytes() == b'local data'


def test_proxy_headers_only_trusted_from_loopback():
    from starlette.requests import Request
    def request(host):
        return Request({'type': 'http', 'client': (host, 1234),
                        'headers': [(b'x-forwarded-for', b'198.51.100.7')]})
    assert source_ip(request('192.0.2.1')) == '192.0.2.1'
    assert source_ip(request('127.0.0.1')) == '198.51.100.7'
