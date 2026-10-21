import asyncio

import pytest

from game_assistant.auth.service import LoginError
from game_assistant.auth.store import CredentialStoreError
from game_assistant.identity.models import Principal
from tests.test_account_auth import setup

P = Principal('a', False)


def parent(accounts, **changes):
    return accounts.save_verified(P, 'hypergryph', dict(uid='hg-user', role_id='role',
        server_id='1', hg_token='passport-secret', **changes))


class Client:
    roles = [('role', '1'), ('other', '2')]
    expired = False
    fail = False
    calls = 0
    entered = None
    release = None

    async def cred_by_code(self, code):
        type(self).calls += 1
        if self.entered:
            self.entered.set()
            await self.release.wait()
        if self.fail:
            raise RuntimeError('upstream secret')
        return 'new-cred'

    async def refresh(self, cred):
        from game_assistant.adapters.endfield.skland_client import SklandError
        if self.expired and cred != 'new-cred':
            raise SklandError('expired secret', expired=True)
        return 'sign-token'

    async def binding(self, *args):
        return {'list': [{'appCode': 'endfield', 'bindingList': [{'channelMasterId': 1, 'isOfficial': True, 'roles': [
            {'roleId': r, 'serverId': s} for r, s in self.roles]}]}]}

    async def user(self, *args):
        return {'user': {'id': 'sk-user'}}

    async def card(self, cred, token, role, server, user, *args):
        return {'base': {'roleId': role, 'name': 'Player'}}

    async def tool(self, kind, cred, token, device_id=''):
        return {'chars': [{'id': 'c1', 'name': '干员'}]}


class Passport:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def skland_code(self, token):
        assert token == 'passport-secret'
        return 'code-secret'


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    from game_assistant.adapters.endfield import hypergryph, skland_client
    from game_assistant import endfield_skland
    Client.roles = [('role', '1'), ('other', '2')]
    Client.expired = Client.fail = False
    Client.calls = 0
    Client.entered = Client.release = None
    monkeypatch.setattr(hypergryph, 'HypergryphClient', Passport)
    monkeypatch.setattr(skland_client, 'SklandClient', Client)
    monkeypatch.setattr(endfield_skland, 'SklandClient', Client)
    return setup(tmp_path)


async def connect(login, hg):
    return await login.connect_skland_passport(P, hg['account_id'], hg['role_id'])


async def test_passport_validated_identity_and_safe_list(cloud):
    db, store, accounts, login = cloud
    hg = parent(accounts)
    sk = await connect(login, hg)
    session = store.load_grant('a', sk['grant_id'])
    assert session['role_id'] == 'role' and session['server_id'] == '1'
    assert session['_parent']['grant_id'] == hg['grant_id']
    assert 'passport-secret' not in str(session)
    item = next(x for x in accounts.list_accounts(P) if x['account_id'] == sk['account_id'])
    assert item['authorization_source'] == 'passport'
    assert item['parent_account_id'] == hg['account_id']
    assert item['parent_role_id'] == hg['role_id']
    assert 'secret' not in str(item) and '_authorization_id' not in str(item)


@pytest.mark.parametrize('foreign,wrong_provider', [(True, False), (False, True)])
async def test_passport_refuses_foreign_and_wrong_provider(cloud, foreign, wrong_provider):
    db, store, accounts, login = cloud
    hg = parent(accounts) if not wrong_provider else accounts.save_verified(P, 'skland',
        {'user_id': 'sk-user', 'cred': 'manual', 'role_id': 'role', 'server_id': '1'})
    with pytest.raises(LookupError):
        await login.connect_skland_passport(Principal('b', False) if foreign else P,
            hg['account_id'], hg['role_id'])
    assert Client.calls == 0


@pytest.mark.parametrize('roles', [[('role', '2')], [('other', '1')]])
async def test_mismatch_preserves_manual_grant(cloud, roles):
    db, store, accounts, login = cloud
    hg = parent(accounts)
    manual = accounts.save_verified(P, 'skland', {'user_id': 'sk-user', 'cred': 'manual',
        'role_id': 'role', 'server_id': '1'})
    before = db.execute('SELECT version,encrypted_payload FROM grants WHERE grant_id=?', (manual['grant_id'],)).fetchone()
    Client.roles = roles
    with pytest.raises(LoginError) as error:
        await connect(login, hg)
    assert error.value.status == 409 and '手动' in error.value.message
    assert db.execute('SELECT version,encrypted_payload FROM grants WHERE grant_id=?', (manual['grant_id'],)).fetchone() == before


async def test_exchange_failure_preserves_previous_authorization(cloud):
    db, store, accounts, login = cloud
    hg = parent(accounts)
    sk = await connect(login, hg)
    Client.fail = True
    with pytest.raises(LoginError) as error:
        await connect(login, hg)
    assert error.value.status == 502 and 'secret' not in error.value.message
    assert store.load_grant('a', sk['grant_id'])['cred'] == 'new-cred'


@pytest.mark.parametrize('change', ['revoke', 'replace'])
async def test_parent_change_revokes_derived_and_preserves_independent_manual(cloud, change):
    db, store, accounts, login = cloud
    hg = parent(accounts)
    sk = await connect(login, hg)
    manual = accounts.save_verified(P, 'skland', {'user_id': 'other-user', 'cred': 'manual',
        'role_id': 'role', 'server_id': '1'})
    if change == 'revoke':
        accounts.revoke(P, hg['account_id'])
    else:
        parent(accounts)
    with pytest.raises(CredentialStoreError):
        store.load_grant('a', sk['grant_id'])
    assert db.execute('SELECT state FROM grants WHERE grant_id=?', (sk['grant_id'],)).fetchone()[0].startswith('revoked')
    assert store.load_grant('a', manual['grant_id'])['cred'] == 'manual'


@pytest.mark.parametrize('change', ['revoke', 'replace'])
async def test_inflight_exchange_cannot_restore_changed_parent(cloud, change):
    db, store, accounts, login = cloud
    hg = parent(accounts)
    Client.entered, Client.release = asyncio.Event(), asyncio.Event()
    job = asyncio.create_task(connect(login, hg))
    await Client.entered.wait()
    if change == 'revoke':
        accounts.revoke(P, hg['account_id'])
    else:
        parent(accounts)
    Client.release.set()
    with pytest.raises(LoginError) as error:
        await job
    assert error.value.status == 409
    assert not any(x['provider'] == 'skland' for x in accounts.list_accounts(P))


async def test_runtime_expired_derived_cred_renews_once_with_cloud_cas(cloud, tmp_path):
    from game_assistant.accounts.runtime import AccountRuntime
    from game_assistant.config import Settings
    from game_assistant.models import Capability
    db, store, accounts, login = cloud
    sk = await connect(login, parent(accounts))
    session = store.load_grant('a', sk['grant_id'])
    store.save_grant('a', sk['grant_id'], {**session, 'cred': 'old'}, sk['version'])
    Client.expired = True
    runtime = AccountRuntime(accounts, Settings(), tmp_path/'runtime', login=login)
    scope = accounts.require_scope(P, sk['account_id'], sk['role_id'])
    result = await runtime.for_scope(scope).get('endfield').fetch(Capability.ACCOUNT)
    assert result.ok and result.credential_version == sk['version'] + 1
    assert Client.calls == 2
    assert store.load_grant('a', sk['grant_id'])['cred'] == 'new-cred'
    await runtime.aclose()


async def test_scoped_private_service_expired_cred_renews_and_cache_does_not_leak(cloud, tmp_path):
    from game_assistant.private_routes import PrivateRoutes
    from types import SimpleNamespace
    db, store, accounts, login = cloud
    hg = parent(accounts)
    sk = await connect(login, hg)
    session = store.load_grant('a', sk['grant_id'])
    store.save_grant('a', sk['grant_id'], {**session, 'cred': 'old'}, sk['version'])
    Client.expired = True
    private = PrivateRoutes(accounts, SimpleNamespace(login=login), tmp_path)
    scope = accounts.require_scope(P, sk['account_id'], sk['role_id'])
    service = private.skland(scope)
    result = await service.read_card(scope)
    assert result['payload']['base']['role_id'] == 'role'
    assert Client.calls == 2
    accounts.revoke(P, hg['account_id'])
    with pytest.raises((LookupError, CredentialStoreError)):
        await service.read_card(scope)
    private.close()

async def test_old_manual_role_scope_is_unavailable_after_passport_narrows_grant(cloud, tmp_path):
    from game_assistant.private_routes import PrivateRoutes
    from types import SimpleNamespace
    db, store, accounts, login = cloud
    hg = parent(accounts)
    manual = accounts.save_verified(P, 'skland', {'user_id': 'sk-user', 'cred': 'manual',
        'role_id': 'other', 'server_id': '2', 'roles': [
            {'role_id': 'role', 'server_id': '1'}, {'role_id': 'other', 'server_id': '2'}]})
    old_scope = accounts.require_scope(P, manual['account_id'], manual['role_id'])
    await connect(login, hg)
    with pytest.raises(LookupError):
        accounts.describe(old_scope)
    private = PrivateRoutes(accounts, SimpleNamespace(login=login), tmp_path)
    with pytest.raises(LookupError):
        private.skland(old_scope)
    private.close()


async def test_legacy_parent_and_normal_parent_renewal_keep_relationship(cloud):
    db, store, accounts, login = cloud
    hg = parent(accounts)
    saved = store.load_grant('a', hg['grant_id'])
    saved.pop('_authorization_id')
    store.save_grant('a', hg['grant_id'], saved, hg['version'])
    sk = await connect(login, hg)
    class Renewal:
        async def renew(self, credentials):
            return {**credentials, 'hg_token': 'passport-secret'}
    login.providers['hypergryph'] = Renewal()
    await login.renew(P, hg['grant_id'])
    assert store.load_grant('a', sk['grant_id'])['cred'] == 'new-cred'
    parent(accounts)
    with pytest.raises(CredentialStoreError):
        store.load_grant('a', sk['grant_id'])


@pytest.mark.parametrize('change', ['revoke_parent', 'replace_parent', 'revoke_child', 'manual_relink'])
async def test_inflight_renewal_cannot_restore_changed_relationship(cloud, change):
    db, store, accounts, login = cloud
    hg = parent(accounts)
    sk = await connect(login, hg)
    Client.entered, Client.release = asyncio.Event(), asyncio.Event()
    job = asyncio.create_task(login.renew_skland(P, sk['grant_id'], expected_version=sk['version'],
        role_id='role', server_id='1'))
    await Client.entered.wait()
    if change == 'revoke_parent':
        accounts.revoke(P, hg['account_id'])
    elif change == 'replace_parent':
        parent(accounts)
    elif change == 'revoke_child':
        accounts.revoke(P, sk['account_id'])
    else:
        accounts.save_verified(P, 'skland', {'user_id': 'sk-user', 'cred': 'manual-new',
            'role_id': 'role', 'server_id': '1'})
    before = db.execute('SELECT version,state,encrypted_payload FROM grants WHERE grant_id=?', (sk['grant_id'],)).fetchone()
    Client.release.set()
    with pytest.raises(LoginError):
        await job
    assert db.execute('SELECT version,state,encrypted_payload FROM grants WHERE grant_id=?', (sk['grant_id'],)).fetchone() == before


async def test_inflight_connect_preserves_concurrent_manual_relink(cloud):
    db, store, accounts, login = cloud
    hg = parent(accounts)
    Client.entered, Client.release = asyncio.Event(), asyncio.Event()
    job = asyncio.create_task(connect(login, hg))
    await Client.entered.wait()
    manual = accounts.save_verified(P, 'skland', {'user_id': 'sk-user', 'cred': 'manual-new',
        'role_id': 'role', 'server_id': '1'})
    Client.release.set()
    with pytest.raises(LoginError) as error:
        await job
    assert error.value.status == 409
    assert store.load_grant('a', manual['grant_id'])['cred'] == 'manual-new'


async def test_link_survives_database_backup_and_cannot_read_after_parent_revoked(cloud, tmp_path):
    import sqlite3
    from game_assistant.accounts.service import AccountService
    from game_assistant.auth.store import CredentialStore
    db, store, accounts, login = cloud
    hg = parent(accounts)
    sk = await connect(login, hg)
    backup = tmp_path/'backup.db'
    with sqlite3.connect(backup) as restored:
        db.backup(restored)
        restored_store = CredentialStore(tmp_path/'unused', connection=restored, key_path=store.key_path)
        restored_accounts = AccountService(restored, restored_store)
        assert restored_store.load_grant('a', sk['grant_id'])['_parent']['grant_id'] == hg['grant_id']
        restored_accounts.revoke(P, hg['account_id'])
        with pytest.raises(CredentialStoreError):
            restored_store.load_grant('a', sk['grant_id'])
    assert store.load_grant('a', sk['grant_id'])['cred'] == 'new-cred'


async def test_manual_expired_cred_is_never_automatically_exchanged(cloud, tmp_path):
    from game_assistant.accounts.runtime import AccountRuntime
    from game_assistant.config import Settings
    from game_assistant.models import Capability
    db, store, accounts, login = cloud
    parent(accounts)
    manual = accounts.save_verified(P, 'skland', {'user_id': 'sk-user', 'cred': 'old',
        'role_id': 'role', 'server_id': '1'})
    Client.expired = True
    runtime = AccountRuntime(accounts, Settings(), tmp_path/'runtime', login=login)
    scope = accounts.require_scope(P, manual['account_id'], manual['role_id'])
    result = await runtime.for_scope(scope).get('endfield').fetch(Capability.ACCOUNT)
    assert not result.ok and result.error_kind == 'auth_expired' and Client.calls == 0
    await runtime.aclose()

async def test_passport_rate_budget_is_owned_bounded_and_redacted(cloud):
    db, store, accounts, login = cloud
    hg = parent(accounts)
    for _ in range(10):
        await connect(login, hg)
    with pytest.raises(LoginError) as error:
        await connect(login, hg)
    assert error.value.status == 429 and Client.calls == 10
    assert 'secret' not in error.value.message
    assert login._skland_attempts.keys() == {'a'}


async def test_cloud_routes_require_csrf_and_explicit_allowlist(cloud, tmp_path):
    import httpx
    from game_assistant.cloud_app import create_cloud_app, allow_cloud_route
    from game_assistant.accounts.routes import install_account_routes
    from game_assistant.config import Settings
    from game_assistant.identity.dependencies import require_user
    db, store, accounts, login = cloud
    app = create_cloud_app(Settings(cloud_db_path=str(tmp_path/'identity.db'),
        cloud_allowed_origins=['https://cloud.example']), start_scheduler=False)
    app.dependency_overrides[require_user] = lambda: P
    routes = install_account_routes(app, accounts, login)
    path = '/api/accounts/auth/skland/passport'
    hg = parent(accounts)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://cloud.example') as client:
        body = {'account_id': hg['account_id'], 'role_id': hg['role_id']}
        assert (await client.post(path, json=body)).status_code == 404
        for route in routes.routes:
            allow_cloud_route(app, route.path, route.methods)
        assert (await client.post(path, json=body)).status_code == 401
        admin = app.state.identity.bootstrap_admin('admin', 'Admin-password-123')
        csrf = (await client.get('/api/identity/csrf')).json()['csrf_token']
        response = await client.post('/api/identity/login',json={'username':'admin','password':'Admin-password-123'},
            headers={'X-CSRF-Token':csrf})
        assert response.status_code == 200
        assert (await client.post(path, json=body)).status_code == 403
        csrf = (await client.get('/api/identity/csrf')).json()['csrf_token']
        headers = {'X-CSRF-Token':csrf}
        response = await client.post(path,json={**body,'token':'injected-secret'},headers=headers)
        assert response.status_code == 422 and 'injected-secret' not in response.text
        assert (await client.post('/api/endfield/skland/passport',json=body,headers=headers)).status_code == 404
        response = await client.post(path,json=body,headers=headers)
        assert response.status_code == 200 and response.json()['ok']
        assert 'secret' not in response.text


async def test_private_http_read_accepts_own_renewal_and_rejects_revocation(cloud, tmp_path):
    import httpx
    from fastapi import FastAPI
    from types import SimpleNamespace
    from game_assistant.private_routes import PrivateRoutes, _install_skland
    from game_assistant.accounts.routes import install_account_routes
    from game_assistant.identity.dependencies import require_user
    db, store, accounts, login = cloud
    hg = parent(accounts)
    sk = await connect(login, hg)
    session = store.load_grant('a', sk['grant_id'])
    store.save_grant('a', sk['grant_id'], {**session,'cred':'old'}, sk['version'])
    Client.expired = True
    app = FastAPI()
    app.dependency_overrides[require_user] = lambda: P
    install_account_routes(app,accounts,login)
    private = PrivateRoutes(accounts, SimpleNamespace(login=login), tmp_path)
    _install_skland(private,app)
    path = f"/api/accounts/{sk['account_id']}/roles/{sk['role_id']}/endfield/skland/card"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://cloud.example') as client:
        response = await client.get(path)
        assert response.status_code == 200 and response.json()['payload']['base']['role_id']=='role'
        accounts.revoke(P,hg['account_id'])
        response = await client.get(path)
        assert response.status_code == 404 and 'Player' not in response.text
    private.close()


async def test_private_http_official_tools_route_reads_the_catalog(cloud, tmp_path):
    import httpx
    from fastapi import FastAPI
    from types import SimpleNamespace
    from game_assistant.private_routes import PrivateRoutes, _install_skland
    from game_assistant.identity.dependencies import require_user
    db, store, accounts, login = cloud
    sk = await connect(login, parent(accounts))
    app = FastAPI()
    app.dependency_overrides[require_user] = lambda: P
    private = PrivateRoutes(accounts, SimpleNamespace(login=login), tmp_path)
    _install_skland(private, app)
    path = f"/api/accounts/{sk['account_id']}/roles/{sk['role_id']}/endfield/skland/tools"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://cloud.example') as client:
        response = await client.get(path, params={'kind': 'characters'})
    private.close()
    assert response.status_code == 200 and response.json()['payload']['chars'][0]['name'] == '干员'


async def test_scheduler_and_qq_use_same_verified_snapshot_and_revoke_blocks_it(cloud, tmp_path):
    from types import SimpleNamespace
    from game_assistant.accounts.runtime import AccountRuntime
    from game_assistant.accounts.query import AccountQuery
    from game_assistant.config import Settings
    from game_assistant.scheduler import AccountPollingScheduler
    from game_assistant.snapshots import SnapshotStore
    from game_assistant.qq.models import QqIdentity
    from game_assistant.qq.query_routes import QqQueryService
    db, store, accounts, login = cloud
    hg = parent(accounts)
    sk = await connect(login, hg)
    runtime = AccountRuntime(accounts, Settings(), tmp_path/'runtime', login=login)
    snapshots = SnapshotStore(str(tmp_path/'snapshots.db'))
    query = AccountQuery(accounts,runtime,snapshots)
    scheduler = AccountPollingScheduler(accounts,query,Settings(),tmp_path)
    scope = accounts.require_scope(P, sk['account_id'],sk['role_id'])
    result = await scheduler.poll_once(scope,'account')
    assert result.ok
    web = query.read(scope,'account')
    qq = QqQueryService(SimpleNamespace(resolve_qq_identity=lambda identity:P),query,None)
    identity = QqIdentity('app','group','group','sender')
    response = qq.query(identity,'roles','endfield')
    assert '终末地' in response['text'] and 'secret' not in response['text']
    assert web.fetched_at and Client.calls == 1  # QQ read starts no upstream exchange.
    accounts.revoke(P,hg['account_id'])
    with pytest.raises(LookupError):
        query.read(scope,'account')
    response = qq.query(identity,'roles','endfield')
    assert 'Player' not in response['text'] and Client.calls == 1
    await runtime.aclose()

async def test_concurrent_passport_click_does_not_exchange_twice(cloud):
    db, store, accounts, login = cloud
    hg = parent(accounts)
    Client.entered, Client.release = asyncio.Event(), asyncio.Event()
    job = asyncio.create_task(connect(login,hg))
    await Client.entered.wait()
    second = asyncio.create_task(connect(login,hg))
    await asyncio.sleep(0)
    Client.release.set()
    try:
        with pytest.raises(LoginError) as error:
            await second
        assert error.value.status == 429
        assert (await job)['ok'] and Client.calls == 1
    finally:
        await asyncio.gather(job,second,return_exceptions=True)


@pytest.mark.parametrize('path', ['runtime', 'private'])
async def test_inflight_role_data_discarded_after_parent_revoke(cloud, tmp_path, monkeypatch, path):
    from types import SimpleNamespace
    from game_assistant.accounts.runtime import AccountRuntime
    from game_assistant.accounts.query import AccountQuery
    from game_assistant.config import Settings
    from game_assistant.scheduler import AccountPollingScheduler
    from game_assistant.snapshots import SnapshotStore
    from game_assistant.private_routes import PrivateRoutes
    db, store, accounts, login = cloud
    hg = parent(accounts)
    sk = await connect(login,hg)
    scope = accounts.require_scope(P, sk['account_id'],sk['role_id'])
    entered,release = asyncio.Event(),asyncio.Event()
    async def slow_card(self,*args):
        entered.set()
        await release.wait()
        return {'base': {'roleId':'role','name':'Old secret player'}}
    monkeypatch.setattr(Client,'card',slow_card)
    if path == 'runtime':
        runtime = AccountRuntime(accounts, Settings(), tmp_path/'runtime', login=login)
        snapshots = SnapshotStore(str(tmp_path/'snapshots.db'))
        query = AccountQuery(accounts,runtime,snapshots)
        scheduler = AccountPollingScheduler(accounts,query,Settings(),tmp_path)
        job = asyncio.create_task(scheduler.poll_once(scope,'account'))
    else:
        private = PrivateRoutes(accounts, SimpleNamespace(login=login), tmp_path)
        service = private.skland(scope)
        job = asyncio.create_task(service.read_card(scope))
    await entered.wait()
    accounts.revoke(P,hg['account_id'])
    release.set()
    if path == 'runtime':
        result = await job
        assert not result.ok and result.payload is None
        assert snapshots.get_scoped(scope,'account') is None
        await runtime.aclose()
    else:
        with pytest.raises(LookupError):
            await job
        assert service._service._cache is None
        private.close()
