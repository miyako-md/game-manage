import asyncio

import pytest

from game_assistant.auth.service import LoginService, LoginError
from game_assistant.auth.store import CredentialStore
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult


class Provider:
    def __init__(self):
        self.sent = 0
        self.renewed = 0
        self.logins = 0

    async def start_context(self):
        return {'device_id': 'device-1'}

    async def send_sms(self, context, mobile, captcha=None):
        self.sent += 1

    async def login(self, context, mobile, code):
        self.logins += 1
        return {'access_token': 'secret-access', 'refresh_token': 'secret-refresh',
                'role_id': '77', 'nickname': '测试角色', 'device_id': 'device-1'}

    async def renew(self, credentials):
        self.renewed += 1
        await asyncio.sleep(0)
        return {**credentials, 'access_token': 'rotated', 'refresh_token': 'rotated-refresh'}


def make_service(tmp_path):
    now = [1000.0]
    provider = Provider()
    settings = Settings(nte_access_token='legacy-access', nte_refresh_token='legacy-refresh')
    service = LoginService(settings, CredentialStore(tmp_path / 'secrets.bin'),
                           providers={'nte': provider, 'wuthering_waves': provider},
                           clock=lambda: now[0])
    return service, provider, settings, now


async def logged_in(service):
    session = await service.start('nte')
    sid = session['session_id']
    await service.sms('nte', sid, '13800000000')
    await service.login('nte', sid, '13800000000', '123456')
    return sid


async def test_login_persists_reloads_and_never_exposes_secrets(tmp_path):
    service, provider, settings, now = make_service(tmp_path)
    await logged_in(service)
    assert settings.nte_access_token == 'secret-access'
    status = service.status()['accounts']['nte']
    assert status['configured'] and status['source'] == 'saved'
    assert 'secret' not in str(service.status())
    assert '13800000000' not in str(service.status())
    restarted, _, new_settings, _ = make_service(tmp_path)
    assert new_settings.nte_refresh_token == 'secret-refresh'
    assert restarted.status()['accounts']['nte']['nickname'] == '测试角色'


async def test_logout_masks_old_toml_after_restart_and_invalidates_session(tmp_path):
    service, _, settings, _ = make_service(tmp_path)
    sid = await logged_in(service)
    pending = await service.start('nte')
    await service.logout('nte')
    assert settings.nte_access_token == ''
    restarted, _, settings2, _ = make_service(tmp_path)
    assert settings2.nte_access_token == ''
    assert not restarted.status()['accounts']['nte']['configured']
    with pytest.raises(LoginError):
        await service.login('nte', pending['session_id'], '13800000000', '123456')


async def test_expiry_phone_binding_and_sms_cooldown(tmp_path):
    service, provider, _, now = make_service(tmp_path)
    sid = (await service.start('nte'))['session_id']
    await service.sms('nte', sid, '13800000000')
    with pytest.raises(LoginError) as failure:
        await service.sms('nte', sid, '13800000000')
    assert failure.value.status == 429
    with pytest.raises(LoginError):
        await service.login('nte', sid, '13900000000', '123456')
    assert provider.logins == 0
    now[0] += 601
    with pytest.raises(LoginError) as failure:
        await service.login('nte', sid, '13800000000', '123456')
    assert failure.value.status == 410


async def test_new_session_does_not_bypass_phone_cooldown(tmp_path):
    service, provider, _, _ = make_service(tmp_path)
    sid = (await service.start('nte'))['session_id']
    await service.sms('nte', sid, '13800000000')
    sid2 = (await service.start('nte'))['session_id']
    with pytest.raises(LoginError) as failure:
        await service.sms('nte', sid2, '13800000000')
    assert failure.value.status == 429
    assert provider.sent == 1


async def test_failed_save_keeps_live_account(tmp_path, monkeypatch):
    service, _, settings, _ = make_service(tmp_path)
    from game_assistant.auth.store import CredentialStoreError
    def fail(_):
        raise CredentialStoreError('本地凭据保存失败')
    monkeypatch.setattr(service.store, 'save', fail)
    with pytest.raises(LoginError):
        await logged_in(service)
    assert settings.nte_access_token == 'legacy-access'


async def test_failed_save_restores_private_snapshots(tmp_path, monkeypatch):
    from game_assistant.auth.store import CredentialStoreError
    from game_assistant.snapshots import SnapshotStore
    service, _, settings, _ = make_service(tmp_path)
    snapshots = SnapshotStore(str(tmp_path / 'assistant.db'))
    snapshots.save('nte', 'account', '{"nickname":"old"}')
    snapshots.record_poll('nte', 'account', FetchResult(ok=False, error='旧错误', error_kind='source_error'))
    service.snapshots = snapshots
    def fail(_):
        raise CredentialStoreError('本地凭据保存失败')
    monkeypatch.setattr(service.store, 'save', fail)
    with pytest.raises(LoginError):
        await logged_in(service)
    assert snapshots.get('nte', 'account')['payload'] == '{"nickname":"old"}'
    assert snapshots.get_poll_status('nte', 'account')['error'] == '旧错误'
    assert settings.nte_access_token == 'legacy-access'


def test_saved_account_keeps_a_generated_device_id(tmp_path):
    path = tmp_path / 'secrets.bin'
    CredentialStore(path).save({'nte': {'access_token': 'kept', 'refresh_token': 'kept-r'}})
    providers = {'nte': Provider(), 'wuthering_waves': Provider()}
    LoginService(Settings(), CredentialStore(path), providers=providers)
    device = CredentialStore(path).load()['nte']['device_id']
    assert device.startswith('HT') and len(device) == 16
    restarted = LoginService(Settings(), CredentialStore(path), providers=providers)
    assert restarted.settings.nte_device_id == device
    toml_only = tmp_path / 'toml.bin'
    bare = LoginService(Settings(nte_access_token='toml', nte_refresh_token='toml-r'),
                        CredentialStore(toml_only), providers=providers)
    assert bare.settings.nte_device_id.startswith('HT')
    assert CredentialStore(toml_only).load() == {}


async def test_login_attempt_limit(tmp_path):
    service, provider, _, _ = make_service(tmp_path)
    from game_assistant.auth.providers import AuthError
    async def wrong(*args):
        raise AuthError('验证码错误')
    provider.login = wrong
    sid = (await service.start('nte'))['session_id']
    await service.sms('nte', sid, '13800000000')
    for _ in range(5):
        with pytest.raises(LoginError):
            await service.login('nte', sid, '13800000000', '123456')
    with pytest.raises(LoginError) as failure:
        await service.login('nte', sid, '13800000000', '123456')
    assert failure.value.status == 410


async def test_concurrent_stale_fetches_rotate_only_once(tmp_path):
    service, provider, settings, now = make_service(tmp_path)
    await logged_in(service)
    now[0] += 3601
    async def action():
        assert settings.nte_access_token == 'rotated'
        return FetchResult(ok=True, payload=[])
    result = await asyncio.gather(*[service.fetch('nte', Capability.ROLES, action) for _ in range(4)])
    assert all(r.ok for r in result)
    assert provider.renewed == 1
    reloaded, _, settings2, _ = make_service(tmp_path)
    assert settings2.nte_refresh_token == 'rotated-refresh'


async def test_server_reject_rotates_and_retries_once(tmp_path):
    service, provider, settings, now = make_service(tmp_path)
    await logged_in(service)
    attempts = []
    async def action():
        attempts.append(settings.nte_access_token)
        if len(attempts) == 1:
            return FetchResult(ok=False, error='expired', error_code=401)
        return FetchResult(ok=True, payload=[])
    assert (await service.fetch('nte', Capability.ROLES, action)).ok
    assert attempts == ['secret-access', 'rotated']
    assert provider.renewed == 1


async def test_public_nte_capability_never_requires_login(tmp_path):
    service, provider, _, _ = make_service(tmp_path)
    await service.logout('nte')
    async def action():
        return FetchResult(ok=True, payload=[])
    assert (await service.fetch('nte', Capability.ANNOUNCEMENT, action)).ok
    assert provider.renewed == 0


async def test_auth_status_recovers_after_successful_private_request(tmp_path):
    service, provider, settings, _ = make_service(tmp_path)
    service._accounts['nte']['refresh_token'] = ''
    async def rejected():
        return FetchResult(ok=False, error='expired', error_code=401)
    await service.fetch('nte', Capability.ROLES, rejected)
    assert service.status()['accounts']['nte']['state'] == 'expired'
    async def recovered():
        return FetchResult(ok=True, payload=[])
    await service.fetch('nte', Capability.ROLES, recovered)
    assert service.status()['accounts']['nte']['state'] == 'configured'
