from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from game_assistant.adapters.wuthering_waves.routes import install_wuwa_routes
from game_assistant.models import FetchResult


class Auth:
    generation = 0
    ticket_version = 0

    def version(self, game):
        return self.ticket_version

    def account_generation(self, game):
        return self.generation

    async def fetch(self, game, capability, action):
        result = await action()
        result.credential_version = self.ticket_version
        return result


def make_client():
    from types import SimpleNamespace
    app = FastAPI()
    adapter = SimpleNamespace(credentials_configured=True,
        fetch_role_detail=AsyncMock(return_value=FetchResult(ok=True, payload={'character_id': '1501'})),
        fetch_resource_detail=AsyncMock(return_value=FetchResult(ok=False, error='无此周期', error_kind='not_found')))
    app.state.registry = SimpleNamespace(get=lambda game: adapter)
    app.state.auth = Auth()
    install_wuwa_routes(app)
    return TestClient(app), adapter, app.state.auth


def test_private_routes_reject_bad_ids_and_missing_periods():
    client, adapter, auth = make_client()
    assert client.get('/api/wuwa/roles/1501').json()['payload']['character_id'] == '1501'
    assert client.get('/api/wuwa/roles/evil').status_code == 422
    assert client.get('/api/wuwa/resources/other/1').status_code == 422
    assert client.get('/api/wuwa/resources/month/1').status_code == 404
    adapter.credentials_configured = False
    assert client.get('/api/wuwa/roles/1501').status_code == 401


def test_session_switch_discards_inflight_details():
    client, adapter, auth = make_client()
    async def switched(role_id):
        auth.generation += 1
        return FetchResult(ok=True, payload={'private': 'old-account'})
    adapter.fetch_role_detail.side_effect = switched
    response = client.get('/api/wuwa/roles/1501')
    assert response.status_code == 409
    assert 'old-account' not in response.text


def test_same_account_ticket_renewal_returns_detail_without_retry():
    client, adapter, auth = make_client()
    async def renewed(role_id):
        auth.ticket_version += 1
        return FetchResult(ok=True, payload={'character_id': role_id})
    adapter.fetch_role_detail.side_effect = renewed
    assert client.get('/api/wuwa/roles/1501').status_code == 200
