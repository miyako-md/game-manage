import json
from types import SimpleNamespace

import pytest

from game_assistant.accounts.query import AccountQuery
from game_assistant.accounts.store import AccountNotFoundError
from game_assistant.identity.models import Principal
from game_assistant.models import Capability, FetchResult
from game_assistant.registry import GameRegistry
from game_assistant.snapshots import SnapshotStore
from tests.test_account_auth import setup, authorize


async def query_fixture(tmp_path):
    db, credentials, accounts, login = setup(tmp_path)
    row = await authorize(login)
    scope = accounts.require_scope(Principal('a', False), row['account_id'], row['role_id'])
    class Adapter:
        game_id = 'nte'
        display_name = '异环'
        capabilities = [Capability.ACCOUNT, Capability.STAMINA, Capability.EVENTS]
        async def fetch(self, capability):
            return FetchResult(ok=True, payload={'level': None})
        def prepare_refresh(self):
            pass
    registry = GameRegistry()
    registry.register(Adapter())
    runtime = SimpleNamespace(for_scope=lambda scope: registry)
    store = SnapshotStore(str(tmp_path / 'snapshots.db'))
    query = AccountQuery(accounts, runtime, store)
    return accounts, scope, store, query


async def test_cached_reads_preserve_missing_and_failure_state(tmp_path):
    accounts, scope, store, query = await query_fixture(tmp_path)
    assert query.read(scope, 'account').payload is None
    store.save_scoped(scope, 'account', json.dumps({'level': None, 'complete': False}), 1)
    store.record_poll_scoped(scope, 'account', FetchResult(ok=False, error_kind='source_error'), 1)
    result = query.read(scope, 'account')
    assert result.payload == {'level': None, 'complete': False}
    assert result.state == 'error' and result.complete is False
    assert result.fetched_at is not None
    accounts.revoke(Principal('a', False), scope.account_id)
    with pytest.raises(AccountNotFoundError):
        query.read(scope, 'account')


async def test_capabilities_use_registry_and_reject_public_or_unknown(tmp_path):
    accounts, scope, store, query = await query_fixture(tmp_path)
    assert query.capabilities(scope) == ['account', 'stamina']
    for cap in ('events', 'fake'):
        with pytest.raises(AccountNotFoundError):
            query.read(scope, cap)
    listing = query.list_accounts(Principal('a', False))
    assert listing[0]['capabilities'] == ['account', 'stamina']
    assert listing[0]['display_name'] == '异环'
    with pytest.raises(AccountNotFoundError):
        accounts.require_scope(Principal('b', True), scope.account_id, scope.role_id)


async def test_version_mismatch_cannot_read_old_cache(tmp_path):
    accounts, scope, store, query = await query_fixture(tmp_path)
    store.save_scoped(scope, 'account', '{"secret":"old"}', 1)
    info = accounts.describe(scope)
    credentials = accounts.credentials.load_grant(scope.user_id, info['grant_id'])
    sealed = accounts.credentials.seal_grant(scope.user_id, info['grant_id'], credentials, 2)
    accounts.connection.execute('UPDATE grants SET version=2,encrypted_payload=?', (sealed,))
    accounts.connection.commit()
    assert query.read(scope, 'account').payload is None


async def corrupt_fixture(tmp_path):
    from game_assistant.accounts.runtime import AccountRuntime
    from game_assistant.config import Settings
    db,credentials,accounts,login = setup(tmp_path)
    first = await authorize(login)
    second = await authorize(login,mobile='13900000000')
    db.execute("UPDATE grants SET encrypted_payload=? WHERE grant_id=?",(b'broken',first['grant_id']))
    db.commit()
    runtime = AccountRuntime(accounts,Settings(),tmp_path/'runtime',login=login)
    store = SnapshotStore(str(tmp_path/'snapshots.db'))
    return accounts,AccountQuery(accounts,runtime,store),first,second


async def test_one_bad_grant_does_not_hide_other_account(tmp_path):
    accounts,query,first,second = await corrupt_fixture(tmp_path)
    listing = query.list_accounts(Principal('a',False))
    broken = next(row for row in listing if row['account_id'] == first['account_id'])
    healthy = next(row for row in listing if row['account_id'] == second['account_id'])
    assert broken['capabilities'] == []
    assert broken['query_state'] == 'credential_unavailable'
    assert 'account' in healthy['capabilities']
    await query.runtime.aclose()


async def test_a_role_the_provider_stopped_listing_does_not_break_the_account_list(tmp_path):
    from game_assistant.accounts.runtime import AccountRuntime
    from game_assistant.config import Settings
    db, credentials, accounts, login = setup(tmp_path)
    principal = Principal('a', False)
    def kuro(roles):
        return {'user_id': 'kuro-user', 'role_id': 'R1', 'server_id': 'S1', 'token': 'tok', 'did': 'did', 'token_source': 'ios',
                'roles': [{'role_id': role, 'server_id': server, 'nickname': role} for role, server in roles]}
    accounts.save_verified(principal, 'kuro', kuro([('R1', 'S1'), ('R2', 'S2')]))
    # A later login of the same Kuro account no longer lists the S2 role.
    accounts.save_verified(principal, 'kuro', kuro([('R1', 'S1')]))
    runtime = AccountRuntime(accounts, Settings(), tmp_path / 'runtime', login=login)
    query = AccountQuery(accounts, runtime, SnapshotStore(str(tmp_path / 'snapshots.db')))
    listing = {row['server']: row for row in query.list_accounts(principal)}
    assert listing['S1']['state'] == 'active' and listing['S1']['capabilities']
    assert (listing['S2']['state'], listing['S2']['roles'], listing['S2']['capabilities']) == ('role_unavailable', [], [])
    await runtime.aclose()


def cloud_settings(tmp_path, **kwargs):
    from game_assistant.config import Settings
    key = tmp_path / 'account.key'
    key.write_bytes(b'k' * 32)
    key.chmod(0o600)
    return Settings(cloud_db_path=str(tmp_path / 'cloud.db'), db_path=str(tmp_path / 'local.db'),
                    cloud_data_root=str(tmp_path / 'cloud-data'), cloud_accounts_enabled=True,
                    cloud_credentials_key_path=str(key), cloud_allowed_origins=['https://cloud.example'], **kwargs)


def test_cloud_composes_owned_routes_and_closes_lifecycle(tmp_path):
    from fastapi.testclient import TestClient
    from game_assistant.cloud_app import create_cloud_app
    from tests.test_identity import write
    import sqlite3
    settings = cloud_settings(tmp_path)
    app = create_cloud_app(settings, start_scheduler=False)
    admin = app.state.identity.bootstrap_admin('admin', 'Admin-password-123')
    invite = app.state.identity.create_invite(admin)
    for attempt in range(2):
        with TestClient(app, base_url='https://cloud.example') as client:
            if attempt == 0:
                user = write(client, '/api/identity/register', {'username':'alice',
                    'password':'Password-alice-123', 'invite':invite}).json()['user_id']
            else:
                user = write(client, '/api/identity/login', {'username':'alice',
                    'password':'Password-alice-123'}).json()['user_id']
            async def seed():
                row = app.state.accounts.save_verified(Principal(user,False), 'tajiduo',
                    {'center_uid':'verified-user','role_id':'77','access_token':'private-token','device_id':'device'})
                scope = app.state.accounts.require_scope(Principal(user,False),row['account_id'],row['role_id'])
                app.state.store.save_scoped(scope,'account','{"level":null,"history_complete":false}',row['version'])
                return row
            row = client.portal.call(seed)
            connection = app.state.accounts.connection
            listing = client.get('/api/accounts')
            assert listing.status_code == 200
            item = listing.json()['accounts'][0]
            assert 'account' in item['capabilities'] and 'events' not in item['capabilities']
            assert 'private-token' not in str(item)
            prefix = f"/api/accounts/{row['account_id']}/roles/{row['role_id']}"
            snapshot = client.get(prefix+'/snapshot/account')
            assert snapshot.status_code == 200
            assert snapshot.json()['payload']['level'] is None
            assert snapshot.json()['complete'] is False
            assert snapshot.json()['poll_status']['refresh_state'] == 'idle'
            assert client.post(prefix+'/refresh/account').status_code == 403
            assert write(client,prefix+'/refresh/account').status_code == 503
            assert client.get(prefix+'/nte/gacha/summary').status_code == 200
            assert client.get('/api/public/games/nte/events').status_code == 200
            if attempt == 0:
                # Two website sessions share the same server loop/SQLite owner thread.
                saved_cookie = client.cookies.get('__Host-ga_session')
                client.cookies.clear()
                outsider_invite = app.state.identity.create_invite(admin)
                assert write(client, '/api/identity/register', {'username':'bob',
                    'password':'Password-bob-123', 'invite':outsider_invite}).status_code == 200
                assert client.get(prefix+'/snapshot/account').status_code == 404
                assert write(client,prefix+'/refresh/account').status_code == 404
                client.cookies.clear()
                client.cookies.set('__Host-ga_session', saved_cookie)
            for path in ('/api/nte/gacha/summary','/api/auth/status','/api/lol/analysis'):
                assert client.get(path).status_code == 404
            assert write(client, f"/api/accounts/{row['account_id']}/authorization", method='delete').status_code == 200
            assert client.get(prefix+'/snapshot/account').status_code == 404
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute('SELECT 1')


def test_enabled_cloud_missing_key_fails_without_generating(tmp_path):
    from fastapi.testclient import TestClient
    from game_assistant.cloud_app import create_cloud_app
    from game_assistant.auth.store import CredentialStoreError
    settings = cloud_settings(tmp_path)
    key = tmp_path / 'account.key'
    key.unlink()
    app = create_cloud_app(settings, start_scheduler=False)
    with pytest.raises(CredentialStoreError):
        with TestClient(app, base_url='https://cloud.example'):
            pass
    assert not key.exists()
    assert not (tmp_path / 'local.db').exists()


def test_cloud_refresh_enqueues_without_waiting(tmp_path):
    import asyncio
    from fastapi.testclient import TestClient
    from game_assistant.cloud_app import create_cloud_app
    from tests.test_identity import write
    settings = cloud_settings(tmp_path,wuwa_enabled=False,nte_enabled=False,endfield_enabled=False)
    app = create_cloud_app(settings)
    admin = app.state.identity.bootstrap_admin('admin','Admin-password-123')
    invite = app.state.identity.create_invite(admin)
    with TestClient(app,base_url='https://cloud.example') as client:
        user = write(client,'/api/identity/register',{'username':'alice','password':'Password-alice-123',
                                                    'invite':invite}).json()['user_id']
        async def seed():
            row = app.state.accounts.save_verified(Principal(user,False),'tajiduo',
                {'center_uid':'verified-user','role_id':'77','access_token':'private-token','device_id':'device'})
            scope = app.state.accounts.require_scope(Principal(user,False),row['account_id'],row['role_id'])
            gate = asyncio.Event()
            async def blocked(cap):
                await gate.wait()
                return FetchResult(ok=True,payload={'level':None})
            app.state.account_runtime.for_scope(scope).get('nte').fetch = blocked
            return row,gate
        row,gate = client.portal.call(seed)
        prefix = f"/api/accounts/{row['account_id']}/roles/{row['role_id']}"
        first = write(client,prefix+'/refresh/account')
        second = write(client,prefix+'/refresh/account')
        assert first.status_code == second.status_code == 202
        assert first.json()['state'] == 'queued' and second.json()['state'] == 'coalesced'
        assert first.json()['job_id'] == second.json()['job_id']
        assert client.get(prefix+'/snapshot/account').json()['payload'] is None
        async def finish():
            gate.set()
            await app.state.scheduler.drain()
        client.portal.call(finish)
        result = client.get(prefix+'/snapshot/account').json()
        assert result['state'] == 'ok' and result['payload']['level'] is None
        assert result['poll_status']['refresh_state'] == 'idle'
