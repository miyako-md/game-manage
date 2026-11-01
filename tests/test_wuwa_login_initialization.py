"""Regression for a cloud host unable to connect to the default IP resolver."""
import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from game_assistant.auth.providers import AuthError, WuwaLoginProvider
from game_assistant.auth.service import LoginError, LoginService
from game_assistant.auth.store import CredentialStore
from game_assistant.cloud_app import create_cloud_app
from game_assistant.config import Settings


@respx.mock
async def test_configured_resolver_initializes_same_kuro_device_context():
    respx.get('https://api64.ipify.org').respond(200, text='8.8.4.4\n')
    context = await WuwaLoginProvider(public_ip_url='https://api64.ipify.org').start_context()
    assert context['dev_code'].startswith('8.8.4.4, ')
    assert context['did']


@pytest.mark.parametrize('address', ['not-an-ip', '127.0.0.1', '192.168.1.1', '::1', '8.8.4.4\r\nx-secret: leak'])
@respx.mock
async def test_configured_resolver_rejects_invalid_or_nonpublic_address(address):
    respx.get('https://api64.ipify.org').respond(200, text=address)
    with pytest.raises(AuthError) as failed:
        await WuwaLoginProvider(public_ip_url='https://api64.ipify.org').start_context()
    assert failed.value.message == '无法获取有效公网地址，请检查网络后重试'
    assert 'leak' not in str(failed.value)


@pytest.mark.parametrize('url', ['http://api64.ipify.org', 'https://user:password@api64.ipify.org',
    'https://api64.ipify.org?ticket=secret', 'https://api64.ipify.org#secret',
    'https://127.0.0.1', 'https://unreviewed.example'])
def test_operator_resolver_rejects_unreviewed_or_unsafe_url(url):
    with pytest.raises(ValidationError):
        Settings(wuwa_login_public_ip_url=url)


@respx.mock
async def test_local_login_uses_configured_resolver_without_sending_sms(tmp_path):
    respx.get('https://api64.ipify.org').respond(200, text='8.8.4.4')
    settings = Settings(wuwa_login_public_ip_url='https://api64.ipify.org')
    service = LoginService(settings, CredentialStore(tmp_path / 'unused'))
    session = await service.start('wuthering_waves')
    assert session['session_id'] and session['expires_in'] == 600
    assert service._sessions[session['session_id']]['context']['dev_code'].startswith('8.8.4.4, ')


@respx.mock
async def test_resolver_connection_failure_is_fixed_error_and_has_no_fallback(tmp_path):
    respx.get('https://api.ipify.org').mock(side_effect=httpx.ConnectError('sensitive upstream original'))
    service = LoginService(Settings(), CredentialStore(tmp_path / 'unused'))
    with pytest.raises(LoginError) as failed:
        await service.start('wuthering_waves')
    assert failed.value.status == 502
    assert failed.value.message == '无法获取有效公网地址，请检查网络后重试'
    assert failed.value.__cause__ is None
    assert 'sensitive' not in str(failed.value)
    assert not service._sessions
    assert len(respx.calls) == 1


async def test_untrusted_provider_error_is_not_exposed(tmp_path):
    class Provider:
        async def start_context(self):
            raise AuthError('secret upstream original')
    service = LoginService(Settings(), CredentialStore(tmp_path / 'unused'),
                           providers={'wuthering_waves': Provider()})
    with pytest.raises(LoginError) as failed:
        await service.start('wuthering_waves')
    assert failed.value.message == '无法初始化登录，请检查网络后重试'
    assert 'secret' not in str(failed.value)


@respx.mock
def test_cloud_operator_resolver_propagates_and_request_cannot_select_url(tmp_path):
    respx.get('https://api64.ipify.org').respond(200, text='8.8.4.4')
    key = tmp_path / 'grant.key'
    key.write_bytes(b'x' * 32)
    key.chmod(0o600)
    settings = Settings(cloud_accounts_enabled=True,
        cloud_db_path=str(tmp_path / 'identity.db'), cloud_data_root=str(tmp_path / 'data'),
        cloud_credentials_key_path=str(key), cloud_allowed_origins=['https://cloud.example'],
        wuwa_login_public_ip_url='https://api64.ipify.org')
    app = create_cloud_app(settings, start_scheduler=False)
    app.state.identity.bootstrap_admin('synthetic-admin', 'Synthetic-test-password-01')
    with TestClient(app, base_url='https://cloud.example') as client:
        csrf = client.get('/api/identity/csrf').json()['csrf_token']
        response = client.post('/api/identity/login',
            json={'username':'synthetic-admin','password':'Synthetic-test-password-01'},
            headers={'X-CSRF-Token':csrf})
        assert response.status_code == 200
        csrf = client.get('/api/identity/csrf').json()['csrf_token']
        response = client.post('/api/accounts/auth/kuro/sessions',
            json={'public_ip_url':'https://evil.example'}, headers={'X-CSRF-Token':csrf})
        assert response.status_code == 422
        assert not respx.calls
        response = client.post('/api/accounts/auth/kuro/sessions',
            json={}, headers={'X-CSRF-Token':csrf})
        assert response.status_code == 200
        assert response.json()['session_id']
