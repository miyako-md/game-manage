import pytest

from game_assistant.accounts.runtime import AccountRuntime
from game_assistant.config import Settings
from game_assistant.identity.models import Principal
from tests.test_account_auth import authorize, setup


async def test_two_accounts_do_not_share_settings(tmp_path):
    db, store, accounts, login = setup(tmp_path)
    await authorize(login)
    await authorize(login, 'b', '13900000000')
    template = Settings(nte_access_token='legacy', wuwa_token='legacy-kuro', endfield_hg_token='legacy-hg')
    runtime = AccountRuntime(accounts, template, tmp_path / 'runtime', login=login)
    registries = []
    for user in ('a', 'b'):
        row = accounts.list_accounts(Principal(user, False))[0]
        scope = accounts.require_scope(Principal(user, False), row['account_id'], row['roles'][0]['role_id'])
        registries.append(runtime.for_scope(scope))
    sa, sb = [r.get('nte')._settings for r in registries]
    assert sa.nte_access_token == 'token-13800000000'
    assert sb.nte_access_token == 'token-13900000000'
    assert sa is not sb and sa.db_path != sb.db_path
    assert sa.wuwa_token == sa.endfield_hg_token == ''
    assert template.nte_access_token == 'legacy'
    assert [a.game_id for a in registries[0].all()] == ['nte']
    await runtime.aclose()


async def test_skland_runtime_reads_verified_role_with_distinct_cred(tmp_path, monkeypatch):
    from game_assistant.models import Capability
    from game_assistant.adapters.endfield import skland_client
    db,store,accounts,login = setup(tmp_path)
    p = Principal('a',False)
    result = accounts.save_verified(p,'skland',{'user_id':'sk-user','role_id':'sk-role','server_id':'1','cred':'sk-secret'})
    scope = accounts.require_scope(p,result['account_id'],result['role_id'])
    class Client:
        async def refresh(self,cred):
            assert cred == 'sk-secret'
            return 'short-token'
        async def card(self,cred,token,role,server,user,device):
            assert (role,server,user) == ('sk-role','1','sk-user')
            return {'base':{'roleId':'sk-role','name':'Skland player'}}
    monkeypatch.setattr(skland_client,'SklandClient',Client)
    runtime = AccountRuntime(accounts,Settings(endfield_hg_token='legacy'),tmp_path/'runtime',login=login)
    fetched = await runtime.for_scope(scope).get('endfield').fetch(Capability.ACCOUNT)
    assert fetched.ok and fetched.payload['base']['role_id'] == 'sk-role'
    assert fetched.payload['stamina']['current'] is None
    assert 'sk-secret' not in str(fetched.payload)
    await runtime.aclose()


async def test_revoked_runtime_cannot_fetch_with_old_token(tmp_path):
    db, store, accounts, login = setup(tmp_path)
    await authorize(login)
    row = accounts.list_accounts(Principal('a', False))[0]
    scope = accounts.require_scope(Principal('a', False), row['account_id'], row['roles'][0]['role_id'])
    runtime = AccountRuntime(accounts, Settings(), tmp_path / 'runtime', login=login)
    registry = runtime.for_scope(scope)
    accounts.revoke(Principal('a', False), row['account_id'])
    from game_assistant.models import Capability
    result = await registry.get('nte').fetch(Capability.ACCOUNT)
    assert not result.ok and result.error_kind == 'auth_expired'
    with pytest.raises(Exception):
        runtime.for_scope(scope)
    await runtime.aclose()


async def test_endfield_runtime_ledger_checks_scope_manifest(tmp_path):
    import sqlite3
    db,store,accounts,login = setup(tmp_path)
    p = Principal('a',False)
    result = accounts.save_verified(p,'hypergryph',{'uid':'hg-uid','role_id':'hg-role','server_id':'1','hg_token':'hg-secret'})
    scope = accounts.require_scope(p,result['account_id'],result['role_id'])
    runtime = AccountRuntime(accounts,Settings(),tmp_path/'runtime',login=login)
    ledger = runtime.for_scope(scope).get('endfield').gacha_store()
    with pytest.raises(PermissionError):
        ledger.summary('another-role')
    path = next((tmp_path/'runtime').glob('*/endfield_gacha/*.sqlite3'))
    with sqlite3.connect(path) as other:
        other.execute("UPDATE private_scope SET user_id='b'")
    with pytest.raises(PermissionError):
        ledger.summary('hg-role')
    await runtime.aclose()

async def test_token_rotation_preserves_other_capabilities_and_original_time(tmp_path, monkeypatch):
    import asyncio
    from game_assistant.accounts.query import AccountQuery
    from game_assistant.snapshots import SnapshotStore
    from game_assistant.models import FetchResult
    from game_assistant.scheduler import AccountPollingScheduler
    from tests.test_account_auth import Provider
    class ProviderWithUntrustedMarker(Provider):
        async def login(self, *args):
            return {**await super().login(*args), '_snapshot_generation':1}
    now = [1000]
    db, credentials, accounts, login = setup(tmp_path, provider=ProviderWithUntrustedMarker(), clock=lambda: now[0])
    row = await authorize(login)
    scope = accounts.require_scope(Principal('a', False), row['account_id'], row['role_id'])
    snapshots = SnapshotStore(str(tmp_path / 'snapshots.db'))
    snapshots.save_scoped(scope, 'account', '{"level":40}', 1)
    snapshots.record_poll_scoped(scope, 'account', FetchResult(ok=True), 1)
    original = snapshots.get_scoped(scope, 'account')
    runtime = AccountRuntime(accounts, Settings(), tmp_path / 'runtime', login=login)
    query = AccountQuery(accounts, runtime, snapshots)
    adapter = runtime.for_scope(scope).get('nte')
    async def stamina():
        return FetchResult(ok=True, payload={'current':90, 'maximum':240})
    monkeypatch.setattr(adapter, 'fetch_stamina', stamina)
    polling = AccountPollingScheduler(accounts, query, Settings(), tmp_path)
    now[0] += 3601
    await polling.poll_once(scope, 'stamina')
    assert accounts.describe(scope)['version'] == 2
    assert query.read(scope, 'account').payload == {'level':40}
    assert query.read(scope, 'account').fetched_at == original['fetched_at']
    assert query.read(scope, 'account').state == 'ok'
    assert snapshots.get_scoped(scope, 'account') == original
    # Concurrent rotations serialize their credential revisions without changing identity.
    await asyncio.gather(*(login.renew(Principal('a', False), row['grant_id']) for _ in range(2)))
    assert accounts.describe(scope)['version'] == 4
    assert query.read(scope, 'account').payload == {'level':40}
    # A new authorization must not inherit the old encrypted generation marker.
    await authorize(login)
    assert query.read(scope, 'account').payload is None
    await runtime.aclose()


async def test_rotation_generation_cannot_cross_changed_identity_or_future_revision(tmp_path):
    from game_assistant.accounts.identities import renewed_snapshot_generation
    from game_assistant.snapshots import SnapshotStore
    previous = {'center_uid':'u','role_id':'r','_verified_roles':[{'role_id':'r','server_id':'s'}],
                '_snapshot_generation':1}
    for field, value in [('center_uid','other'), ('role_id','other'), ('server_id','other'), ('channel','bilibili'),
                         ('_verified_roles',[{'role_id':'other','server_id':'s'}])]:
        assert renewed_snapshot_generation(previous, {**previous, field:value}, 3) == 4
    # Upstream-supplied bookkeeping is ignored in favor of the authenticated prior value.
    assert renewed_snapshot_generation(previous, {**previous, '_snapshot_generation':0}, 3) == 1
    db, credentials, accounts, login = setup(tmp_path)
    row = await authorize(login)
    scope = accounts.require_scope(Principal('a',False),row['account_id'],row['role_id'])
    snapshots = SnapshotStore(str(tmp_path/'s.db'))
    snapshots.save_scoped(scope,'account','{}',5)
    assert snapshots.get_scoped(scope,'account',grant_version=3,minimum_version=1) is None

async def test_failed_rotation_and_late_result_keep_authorization_boundary(tmp_path):
    import asyncio
    from game_assistant.accounts.query import AccountQuery
    from game_assistant.auth.providers import AuthError
    from game_assistant.auth.service import LoginError
    from game_assistant.models import Capability, FetchResult
    from game_assistant.snapshots import SnapshotStore
    from tests.test_account_auth import Provider
    class Failing(Provider):
        async def renew(self, credentials):
            raise AuthError('unavailable')
    now = [1000]
    db, credentials, accounts, login = setup(tmp_path, provider=Failing(), clock=lambda: now[0])
    row = await authorize(login)
    scope = accounts.require_scope(Principal('a',False),row['account_id'],row['role_id'])
    runtime = AccountRuntime(accounts,Settings(),tmp_path/'runtime',login=login)
    store = SnapshotStore(str(tmp_path/'s.db'))
    store.save_scoped(scope,'account','{"level":40}',1)
    query = AccountQuery(accounts,runtime,store)
    with pytest.raises(LoginError):
        await login.renew(Principal('a',False),row['grant_id'])
    assert accounts.describe(scope)['version'] == 1
    assert query.read(scope,'account').payload == {'level':40}
    old_adapter = runtime.for_scope(scope).get('nte')
    started, release = asyncio.Event(), asyncio.Event()
    async def old_result():
        started.set()
        await release.wait()
        return FetchResult(ok=True,payload={'private':'old'})
    old_adapter.fetch_account = old_result
    job = asyncio.create_task(old_adapter.fetch(Capability.ACCOUNT))
    await started.wait()
    now[0] += 61
    await authorize(login)
    release.set()
    result = await job
    assert not result.ok and result.error_kind == 'auth_expired'
    assert query.read(scope,'account').payload is None
    await runtime.aclose()
