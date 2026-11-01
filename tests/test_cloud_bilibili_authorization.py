"""Synthetic QR transport; real identity boundary, encryption and backup."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from game_assistant.cloud_app import create_cloud_app
from game_assistant.config import Settings
from game_assistant.identity.store import IdentityStore
from game_assistant.identity.service import IdentityService
from game_assistant.auth.bilibili_provider import QrChallenge, QrResult, VerifiedBilibiliAccount
from tests.test_identity import write

ROOT = '/api/admin/bilibili-source/login'
FAKE = {'sessdata': 'SYNTHETIC_SECRET_ONLY', 'bili_jct': 'SYNTHETIC_JCT'}


class Provider:
    async def start_qr(self): return QrChallenge('SYNTHETIC_KEY', 'data:image/png;base64,FAKE')
    async def poll_qr(self, key): return QrResult('credential_ready', FAKE)
    async def validate_credentials(self, values): return VerifiedBilibiliAccount(values, '10001', 'Fixture', 1234)
    async def aclose(self): pass


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    import importlib.util
    if importlib.util.find_spec('game_assistant.auth.cloud_bilibili'):
        from game_assistant.auth import cloud_bilibili
        monkeypatch.setattr(cloud_bilibili, 'BilibiliLoginProvider', Provider)
    import httpx
    async def no_network(*args, **kwargs): raise AssertionError('real upstream forbidden')
    monkeypatch.setattr(httpx.AsyncClient, 'send', no_network)
    root = tmp_path / 'data'
    root.mkdir()
    key = tmp_path / 'external.key'
    key.write_bytes(b'k' * 32)
    key.chmod(0o600)
    settings = Settings(cloud_accounts_enabled=True, cloud_db_path=str(root/'identity.db'),
        cloud_data_root=str(root), cloud_credentials_key_path=str(key),
        cloud_allowed_origins=['https://cloud.example'], bilibili_sources={'wuthering_waves':'123'},
        wuwa_enabled=True, nte_enabled=False, endfield_enabled=False)
    identity = IdentityService(IdentityStore(settings.cloud_db_path), settings)
    admin = identity.bootstrap_admin('admin', 'Admin-password-123')
    with TestClient(create_cloud_app(settings, start_scheduler=False), base_url='https://cloud.example') as client:
        yield client, identity, admin, settings, key


def login(client):
    assert write(client, '/api/identity/login', {'username':'admin','password':'Admin-password-123'}).status_code == 200


def start(client, mode='qr'):
    response = write(client, ROOT+'/sessions', {'mode':mode})
    assert response.status_code == 200, response.text
    return response.json()['session_id']


def test_qr_admin_boundary_and_mode_allowlist(cloud):
    client, identity, admin, *_ = cloud
    assert client.get(ROOT+'/status').status_code == 401
    invite = identity.create_invite(admin)
    assert write(client, '/api/identity/register', {'username':'member','password':'Member-password-123','invite':invite}).status_code == 200
    assert client.get(ROOT+'/status').status_code == 403
    assert write(client, ROOT+'/sessions', {'mode':'qr'}).status_code == 403
    assert client.get('/api/public/games/wuthering_waves/news').status_code == 200
    login(client)
    assert client.post(ROOT+'/sessions', json={'mode':'qr'}).status_code == 403
    for mode in ('password','sms'):
        assert write(client, ROOT+'/sessions', {'mode':mode}).status_code == 422
    for path in ('/password','/sms/send','/captcha'):
        assert write(client, ROOT+'/sessions/unknown'+path).status_code == 404
    assert client.get(ROOT+'/status', headers={'Host':'evil.example'}).status_code == 403
    assert client.get(ROOT+'/status', headers={'Origin':'https://evil.example'}).status_code == 403
    assert client.get('/api/auth/bilibili-source/login/status').status_code == 404


def test_qr_saves_encrypted_owned_public_grant_without_game_scope(cloud):
    client, _, admin, settings, key = cloud
    login(client)
    sid = start(client)
    result = write(client, ROOT+f'/sessions/{sid}/qr/poll').json()
    assert result['state'] == 'complete'
    assert FAKE['sessdata'] not in str(result)
    assert 'SYNTHETIC_KEY' not in str(result)
    assert client.get(ROOT+'/status').json()['configured']
    assert client.get('/api/accounts').json() == {'accounts':[]}
    with sqlite3.connect(settings.cloud_db_path) as db:
        assert db.execute('SELECT COUNT(*) FROM roles').fetchone()[0] == 0
        owner, provider, sealed = db.execute('SELECT user_id,provider,encrypted_payload FROM grants').fetchone()
        assert owner == admin.user_id and provider == 'bilibili-public-source'
        assert sealed.startswith(b'GRANT1\n') and FAKE['sessdata'].encode() not in sealed
    root = key.parent/'data'
    assert not list(root.glob('*.credentials*')) and not list(root.glob('*.key'))
    from scripts.cloud.backup import backup
    from scripts.cloud.restore import restore
    manifest = backup(root, settings.cloud_db_path, key.parent/'backup', key)
    assert manifest['credential_readability'] == 'verified' and not manifest['key_included']
    restored = restore(key.parent/'backup', key.parent/'restored', key)
    assert restored['credential_readability'] == 'verified'


@pytest.mark.parametrize('change', ['session','disabled','demoted'])
def test_qr_owner_cannot_commit_after_identity_change(cloud, change):
    client, _, admin, settings, _ = cloud
    login(client)
    sid = start(client)
    if change == 'session':
        login(client)
        assert client.get(ROOT+f'/sessions/{sid}').status_code == 410
        assert write(client, ROOT+f'/sessions/{sid}/qr/poll').status_code == 410
    else:
        with sqlite3.connect(settings.cloud_db_path) as db:
            db.execute('UPDATE users SET '+("disabled_at='now'" if change == 'disabled' else 'is_admin=0')+' WHERE user_id=?', (admin.user_id,))
        assert write(client, ROOT+f'/sessions/{sid}/qr/poll').status_code in (401,403)
    with sqlite3.connect(settings.cloud_db_path) as db:
        assert db.execute('SELECT COUNT(*) FROM grants').fetchone()[0] == 0


def test_cancel_preserves_existing_authorization(cloud):
    client, *_ = cloud
    login(client)
    sid = start(client)
    assert write(client, ROOT+f'/sessions/{sid}/qr/poll').json()['state'] == 'complete'
    sid = start(client)
    assert write(client, ROOT+f'/sessions/{sid}', method='delete').json()['state'] == 'cancelled'
    assert write(client, ROOT+f'/sessions/{sid}/qr/poll').status_code == 410
    assert client.get(ROOT+'/status').json()['configured']


@pytest.mark.parametrize('change', ['revoke','disabled','demoted'])
def test_identity_change_during_upstream_validation_cannot_save(cloud, monkeypatch, change):
    client, _, admin, settings, _ = cloud
    login(client)
    sid = start(client)
    async def invalidate(values):
        with sqlite3.connect(settings.cloud_db_path) as db:
            if change == 'revoke': db.execute("UPDATE sessions SET revoked_at='now' WHERE user_id=?", (admin.user_id,))
            else: db.execute('UPDATE users SET '+("disabled_at='now'" if change == 'disabled' else 'is_admin=0')+' WHERE user_id=?', (admin.user_id,))
        return VerifiedBilibiliAccount(values, '10001', 'Fixture', 1234)
    monkeypatch.setattr(Provider, 'validate_credentials', staticmethod(invalidate))
    response = write(client, ROOT+f'/sessions/{sid}/qr/poll')
    assert response.status_code == 410
    assert FAKE['sessdata'] not in response.text
    with sqlite3.connect(settings.cloud_db_path) as db:
        assert db.execute('SELECT COUNT(*) FROM grants').fetchone()[0] == 0


def test_busy_candidate_can_commit_only_in_original_site_session(cloud):
    client, _, _, settings, _ = cloud
    login(client)
    async def hold():
        import asyncio
        await asyncio.sleep(60)
    def queue():
        client.app.state.bilibili.tasks['wuthering_waves'] = __import__('asyncio').create_task(hold())
    client.portal.call(queue)
    task = client.app.state.bilibili.tasks['wuthering_waves']
    sid = start(client)
    response = write(client, ROOT+f'/sessions/{sid}/qr/poll')
    assert response.status_code == 409 and response.json()['state'] == 'pending_save'
    client.portal.call(task.cancel)
    client.portal.call(__import__('asyncio').sleep, 0)
    response = write(client, ROOT+f'/sessions/{sid}/commit')
    assert response.status_code == 200 and response.json()['state'] == 'complete'
    with sqlite3.connect(settings.cloud_db_path) as db:
        grant = db.execute('SELECT grant_id FROM grants').fetchone()[0]
    assert write(client, f'/api/accounts/{grant}/authorization', method='delete').status_code == 404
    client.app.state.scheduler.public = None
    client.portal.call(client.app.state.scheduler.tick)
    assert client.app.state.scheduler._due == {}


def test_completed_grant_not_used_after_administrator_demotion(cloud):
    client, _, admin, settings, _ = cloud
    login(client)
    sid = start(client)
    assert write(client, ROOT+f'/sessions/{sid}/qr/poll').status_code == 200
    with sqlite3.connect(settings.cloud_db_path) as db:
        db.execute('UPDATE users SET is_admin=0 WHERE user_id=?',(admin.user_id,))
    assert client.portal.call(client.app.state.bilibili.credentials.load) == {}


def test_qr_expiry_rejects_poll_without_credentials(cloud):
    client, *_ = cloud
    login(client)
    sid = start(client)
    def expire(): client.app.state.bilibili_login._sessions[sid].qr_expires = 1
    client.portal.call(expire)
    assert client.get(ROOT+f'/sessions/{sid}').json()['state'] == 'expired'
    assert write(client, ROOT+f'/sessions/{sid}/qr/poll').status_code == 410


def test_other_administrator_cannot_read_cancel_or_poll_qr(cloud):
    client, identity, admin, settings, _ = cloud
    login(client)
    sid = start(client)
    invite = identity.create_invite(admin)
    response = write(client, '/api/identity/register', {'username':'otheradmin','password':'Other-admin-password-123','invite':invite})
    with sqlite3.connect(settings.cloud_db_path) as db:
        db.execute('UPDATE users SET is_admin=1 WHERE user_id=?',(response.json()['user_id'],))
    assert client.get(ROOT+f'/sessions/{sid}').status_code == 410
    assert write(client, ROOT+f'/sessions/{sid}', method='delete').status_code == 410
    assert write(client, ROOT+f'/sessions/{sid}/qr/poll').status_code == 410


def test_failed_replacement_preserves_old_grant_until_commit(cloud, monkeypatch):
    from game_assistant.auth.store import CredentialStoreError
    client, _, _, settings, _ = cloud
    login(client)
    sid = start(client)
    assert write(client, ROOT+f'/sessions/{sid}/qr/poll').status_code == 200
    with sqlite3.connect(settings.cloud_db_path) as db:
        old = db.execute("SELECT grant_id,encrypted_payload FROM grants WHERE state='active'").fetchone()
    sid = start(client)
    def fail_seal(*args): raise CredentialStoreError('synthetic storage failure')
    with monkeypatch.context() as patch:
        patch.setattr(client.app.state.bilibili.credentials.credentials, 'seal_grant', fail_seal)
        response = write(client, ROOT+f'/sessions/{sid}/qr/poll')
        assert response.status_code == 500 and response.json()['error_code'] == 'STORAGE_ERROR'
        assert 'synthetic storage failure' not in response.text
        with sqlite3.connect(settings.cloud_db_path) as db:
            assert db.execute("SELECT grant_id,encrypted_payload FROM grants WHERE state='active'").fetchone() == old
    assert write(client, ROOT+f'/sessions/{sid}/commit').status_code == 200
    with sqlite3.connect(settings.cloud_db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM grants WHERE state='active'").fetchone()[0] == 1
        assert db.execute("SELECT state FROM grants WHERE grant_id=?",(old[0],)).fetchone()[0] == 'revoked'


def test_sessdata_only_is_normalized_encrypted_and_never_returned(cloud, monkeypatch, caplog):
    client, *_ = cloud
    login(client)
    seen = []
    async def validate(values):
        seen.append(values)
        return VerifiedBilibiliAccount({**values,'dedeuserid':'10001'}, '10001', 'Fixture', 1234)
    monkeypatch.setattr(Provider, 'validate_credentials', staticmethod(validate))
    sid = start(client, 'cookie')
    response = write(client, ROOT+f'/sessions/{sid}/cookie', {'sessdata':'  SYNTHETIC%2CSESS  '})
    assert response.status_code == 200 and response.json()['state'] == 'complete'
    assert seen == [{'sessdata':'SYNTHETIC,SESS'}]
    for path in (ROOT+'/status', ROOT+f'/sessions/{sid}'):
        assert 'SYNTHETIC' not in client.get(path).text
    assert 'SYNTHETIC' not in response.text and 'SYNTHETIC' not in caplog.text
    assert client.portal.call(client.app.state.bilibili.credentials.load)['bilibili'] == {'sessdata':'SYNTHETIC,SESS','dedeuserid':'10001'}


@pytest.mark.parametrize('body', [ {'sessdata':'x'*4097}, {'sessdata':'SYNTHETIC_SECRET','bili_jct':'SYNTHETIC_EXTRA'}, {'sessdata':12345}, {'sessdata':''} ])
def test_cookie_validation_errors_never_echo_secret(cloud, body, caplog):
    client, *_ = cloud
    login(client)
    sid = start(client, 'cookie')
    response = write(client, ROOT+f'/sessions/{sid}/cookie', body)
    assert response.status_code == 422 and response.json() == {'detail':'invalid_request'}
    assert 'SYNTHETIC' not in response.text and 'SYNTHETIC' not in caplog.text
    assert 'x'*20 not in response.text


def test_cookie_submit_requires_csrf_origin_and_original_site_session(cloud):
    client, identity, admin, *_ = cloud
    login(client)
    sid = start(client, 'cookie')
    path = ROOT+f'/sessions/{sid}/cookie'
    assert client.post(path,json={'sessdata':'SYNTHETIC'}).status_code == 403
    csrf = client.get('/api/identity/csrf').json()['csrf_token']
    assert client.post(path,json={'sessdata':'SYNTHETIC'},headers={'X-CSRF-Token':csrf,'Origin':'https://evil.example'}).status_code == 403
    login(client)
    assert write(client,path,{'sessdata':'SYNTHETIC'}).status_code == 410
    invite = identity.create_invite(admin)
    assert write(client,'/api/identity/register',{'username':'membercookie','password':'Member-cookie-password-123','invite':invite}).status_code == 200
    assert write(client,path,{'sessdata':'SYNTHETIC'}).status_code == 403
    assert write(client,ROOT+'/sessions',{'mode':'cookie'}).status_code == 403
    assert write(client,'/api/identity/logout').status_code == 200
    assert client.post(path,json={'sessdata':'SYNTHETIC'}).status_code == 401


def test_cookie_failure_keeps_previous_public_grant(cloud, monkeypatch):
    from game_assistant.auth.bilibili_provider import BilibiliProtocolError
    client, _, _, settings, _ = cloud
    login(client)
    sid = start(client)
    assert write(client,ROOT+f'/sessions/{sid}/qr/poll').status_code == 200
    with sqlite3.connect(settings.cloud_db_path) as db:
        old = db.execute("SELECT grant_id,encrypted_payload FROM grants WHERE state='active'").fetchone()
    async def reject(values): raise BilibiliProtocolError('INVALID_CREDENTIALS',400)
    monkeypatch.setattr(Provider,'validate_credentials',staticmethod(reject))
    sid = start(client,'cookie')
    response = write(client,ROOT+f'/sessions/{sid}/cookie',{'sessdata':'SYNTHETIC_INVALID'})
    assert response.status_code == 400 and 'SYNTHETIC' not in response.text
    with sqlite3.connect(settings.cloud_db_path) as db:
        assert db.execute("SELECT grant_id,encrypted_payload FROM grants WHERE state='active'").fetchone() == old


@pytest.mark.parametrize('change', ['revoke','demoted'])
def test_identity_change_during_cookie_validation_cannot_commit(cloud, monkeypatch, change):
    client, _, admin, settings, _ = cloud
    login(client)
    sid = start(client,'cookie')
    async def invalidate(values):
        with sqlite3.connect(settings.cloud_db_path) as db:
            if change == 'revoke': db.execute("UPDATE sessions SET revoked_at='now' WHERE user_id=?", (admin.user_id,))
            else: db.execute('UPDATE users SET is_admin=0 WHERE user_id=?',(admin.user_id,))
        return VerifiedBilibiliAccount(values,'10001','Fixture',1234)
    monkeypatch.setattr(Provider,'validate_credentials',staticmethod(invalidate))
    assert write(client,ROOT+f'/sessions/{sid}/cookie',{'sessdata':'SYNTHETIC'}).status_code == 410
    with sqlite3.connect(settings.cloud_db_path) as db:
        assert db.execute('SELECT COUNT(*) FROM grants').fetchone()[0] == 0


@pytest.mark.parametrize('code,status', [('UPSTREAM_RESTRICTED',502), ('UNSUPPORTED_RESPONSE',502), ('UPSTREAM_UNAVAILABLE',502), ('INVALID_CREDENTIALS',400)])
def test_cookie_failure_category_is_returned_without_saving_new_grant(cloud, monkeypatch, code, status):
    from game_assistant.auth.bilibili_provider import BilibiliProtocolError
    client, _, _, settings, _ = cloud
    login(client)
    sid = start(client, 'cookie')
    async def reject(values):
        raise BilibiliProtocolError(code, status)
    monkeypatch.setattr(Provider, 'validate_credentials', staticmethod(reject))
    response = write(client, ROOT+f'/sessions/{sid}/cookie', {'sessdata':'SYNTHETIC_NOT_SAVED'})
    assert response.status_code == status
    assert response.json()['error_code'] == code
    assert 'SYNTHETIC_NOT_SAVED' not in response.text
    assert client.get(ROOT+'/status').json()['configured'] is False
    with sqlite3.connect(settings.cloud_db_path) as db:
        assert db.execute('SELECT COUNT(*) FROM grants').fetchone()[0] == 0


def test_public_grant_status_survives_service_restart(cloud):
    from game_assistant.auth.cloud_bilibili import CloudBilibiliLoginService
    client, *_ = cloud
    login(client)
    sid = start(client, 'cookie')
    assert write(client, ROOT+f'/sessions/{sid}/cookie', {'sessdata':'SYNTHETIC_RESTART'}).status_code == 200
    restarted = CloudBilibiliLoginService(client.app.state.bilibili, client.app.state.identity)
    status = client.portal.call(restarted.status)
    assert status['configured'] is True and status['state'] == 'configured'
    assert status['uid'] == '10001'
    assert 'SYNTHETIC_RESTART' not in str(status)


def test_unreadable_grant_status_is_storage_error_and_preserves_grant(cloud, monkeypatch):
    from game_assistant.auth.store import CredentialStoreError
    client, _, _, settings, _ = cloud
    login(client)
    sid = start(client, 'cookie')
    assert write(client, ROOT+f'/sessions/{sid}/cookie', {'sessdata':'SYNTHETIC_STORED'}).status_code == 200
    def unreadable(*args): raise CredentialStoreError('SYNTHETIC_PRIVATE_ERROR')
    monkeypatch.setattr(client.app.state.bilibili.credentials.credentials, 'load_grant', unreadable)
    response = client.get(ROOT+'/status')
    assert response.status_code == 200
    assert response.json()['state'] == 'storage_error'
    assert '读取失败' in response.json()['message']
    assert 'SYNTHETIC' not in response.text
    with sqlite3.connect(settings.cloud_db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM grants WHERE state='active'").fetchone()[0] == 1
