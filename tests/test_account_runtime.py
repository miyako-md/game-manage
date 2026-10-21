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


class ChallengeClient:
    """Synthetic Skland responses; ``failures`` maps a kind to the error it raises."""
    calls = []
    failures = {}
    data = {
        'war': {'seasons': [{'id': 's1', 'name': '合成赛季', 'stars': 0, 'weeks': []}],
                'achieves': [{'name': '合成荣誉', 'star': 0, 'token': 'RAW-TOKEN'}]},
        'monument': {'indieHardGroups': [{'id': 'm1', 'name': '合成丰碑', 'dungeonGroups': [],
                                          'achieve': {'cred': 'RAW-CRED'}}]},
        'crisis': {'status': {'highest': 0, 'weeklyMission': {'secret': 'RAW-MISSION'}},
                   'history': {'records': [{'id': 'r1', 'score': 0, 'isPass': False,
                                            'chars': [{'name': 'RAW-CHARS'}]}],
                               'bestRecord': {'chars': [{'name': 'RAW-BEST'}]}}},
    }

    async def refresh(self, cred):
        type(self).calls.append(('refresh', cred))
        return 'short-token'

    async def challenge(self, kind, cred, token, role, server, user, device='', **kwargs):
        type(self).calls.append((kind, cred, token, role, server, user, kwargs))
        if kind in self.failures:
            raise self.failures[kind]
        return self.data[kind]


async def combat_runtime(tmp_path, monkeypatch, **failures):
    from game_assistant.adapters.endfield import skland_client
    db, store, accounts, login = setup(tmp_path)
    p = Principal('a', False)
    result = accounts.save_verified(p, 'skland', {'user_id': 'sk-user', 'role_id': 'sk-role', 'server_id': '1', 'cred': 'sk-secret'})
    scope = accounts.require_scope(p, result['account_id'], result['role_id'])
    ChallengeClient.calls, ChallengeClient.failures = [], failures
    monkeypatch.setattr(skland_client, 'SklandClient', ChallengeClient)
    runtime = AccountRuntime(accounts, Settings(), tmp_path / 'runtime', login=login)
    return runtime, runtime.for_scope(scope).get('endfield')


async def test_skland_combat_reads_three_kinds_and_returns_only_the_projection(tmp_path, monkeypatch):
    import json
    from game_assistant.models import Capability
    runtime, adapter = await combat_runtime(tmp_path, monkeypatch)
    assert adapter.capabilities == [Capability.ACCOUNT, Capability.COMBAT]
    fetched = await adapter.fetch(Capability.COMBAT)
    assert fetched.ok and fetched.error_code is None
    # One signing refresh, then one default (unfiltered) request per kind.
    assert ChallengeClient.calls == [('refresh', 'sk-secret')] + [
        (kind, 'sk-secret', 'short-token', 'sk-role', '1', 'sk-user', {}) for kind in ('war', 'monument', 'crisis')]
    payload = fetched.payload
    assert set(payload) == {'schema_version', 'reports'} and payload['schema_version'] == 1
    assert [r['kind'] for r in payload['reports']] == ['war', 'monument', 'crisis']
    assert all(r['available'] and not r['stale'] and r['fetched_at'] for r in payload['reports'])
    crisis = payload['reports'][2]
    assert crisis['summary']['highest'] == 0 and crisis['summary']['challenge_count'] is None
    assert crisis['records'][0]['result'] == 0 and crisis['records'][0]['passed'] is False
    text = json.dumps(payload, ensure_ascii=False)
    for secret in ('sk-secret', 'short-token', 'RAW-', 'chars', 'bestRecord', 'cred', 'token'):
        assert secret not in text
    await runtime.aclose()


async def test_skland_combat_partial_and_total_failure(tmp_path, monkeypatch):
    from game_assistant.adapters.endfield.skland_client import SklandError
    from game_assistant.models import Capability
    runtime, adapter = await combat_runtime(tmp_path, monkeypatch,
        monument=SklandError('RAW-ERROR', status=429), crisis=SklandError('RAW-ERROR', status=503))
    fetched = await adapter.fetch(Capability.COMBAT)
    assert fetched.ok and fetched.error_code == 429 and 'RAW-ERROR' not in str(fetched.payload)
    war, monument, crisis = fetched.payload['reports']
    assert war['available'] and not war['stale']
    for report in (monument, crisis):
        assert (report['available'], report['stale'], report['fetched_at']) == (False, True, None)
        assert report['records'] == [] and report['summary']['listed_count'] is None
    ChallengeClient.failures['war'] = SklandError('RAW-ERROR', status=503)
    fetched = await adapter.fetch(Capability.COMBAT)
    assert not fetched.ok and fetched.payload is None
    assert (fetched.error_kind, fetched.error_code) == ('source_error', 429)
    assert 'RAW-ERROR' not in str(fetched.error)
    await runtime.aclose()


async def test_skland_combat_expired_login_is_an_authorization_failure(tmp_path, monkeypatch):
    from game_assistant.adapters.endfield.skland_client import SklandError
    from game_assistant.models import Capability
    runtime, adapter = await combat_runtime(tmp_path, monkeypatch, monument=SklandError('expired', expired=True, status=401))
    fetched = await adapter.fetch(Capability.COMBAT)
    assert not fetched.ok and fetched.error_kind == 'auth_expired' and fetched.payload is None
    assert [call[0] for call in ChallengeClient.calls] == ['refresh', 'war', 'monument']
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


async def test_switching_between_verified_roles_keeps_the_snapshot_generation(tmp_path):
    from datetime import datetime, timezone
    from game_assistant.accounts.query import AccountQuery
    from game_assistant.auth.service import LoginError
    from game_assistant.models import FetchResult
    from game_assistant.reminder_policy import ReminderRule
    from game_assistant.scoped_reminders import ReminderStore, ScopedReminderService
    from game_assistant.snapshots import SnapshotStore
    from tests.test_account_auth import Provider
    roles = [{'role_id':'77','server_id':'official'}, {'role_id':'88','server_id':'second'}]
    class TwoServers(Provider):
        returned_role = None
        async def login(self, *args):
            return {**await super().login(*args), 'server_id':'official', '_verified_roles':roles}
        async def renew(self, credentials):
            updated = await super().renew(credentials)
            return {**updated, 'role_id':self.returned_role} if self.returned_role else updated
    provider, clock = TwoServers(), [1000]
    db, credentials, accounts, login = setup(tmp_path, provider=provider, clock=lambda: clock[0])
    row = await authorize(login)
    principal = Principal('a', False)
    scopes = {}
    for account in accounts.list_accounts(principal):
        role = account['roles'][0]
        scope = accounts.require_scope(principal, account['account_id'], role['role_id'])
        scopes[accounts.describe(scope)['game_uid']] = scope
    assert sorted(scopes) == ['77', '88']
    snapshots = SnapshotStore(str(tmp_path / 'snapshots.db'))
    for uid, scope in scopes.items():
        snapshots.save_scoped(scope, 'account', f'{{"uid":"{uid}"}}', 1)
    query = AccountQuery(accounts, AccountRuntime(accounts, Settings(), tmp_path / 'runtime', login=login), snapshots)
    now = datetime(2026, 10, 14, 8, tzinfo=timezone.utc)
    reminders = ScopedReminderService(ReminderStore(tmp_path / 'inbox.db'), accounts, clock=lambda: now)
    reminders.set_rule(scopes['77'], ReminderRule(enabled=True, notify_full=True))
    reminders.handle_poll(scopes['77'], 'stamina', FetchResult(ok=True,
        payload={'current':100, 'maximum':100, 'updated_at':now.isoformat()}), 1)
    inbox = reminders.inbox(scopes['77'])
    assert len(inbox) == 1
    def visible():
        version = accounts.describe(scopes['77'])['version']
        # The equipped route reads the roles snapshot through the same generation bound.
        equipped = snapshots.get_scoped(scopes['88'], 'account', grant_version=version,
            minimum_version=accounts.snapshot_generation(scopes['88'], version))
        return ({uid: query.read(scope, 'account').payload for uid, scope in scopes.items()},
                reminders.inbox(scopes['77']), equipped and equipped['payload'])
    expected = ({'77':{'uid':'77'}, '88':{'uid':'88'}}, inbox, '{"uid":"88"}')
    # Fetches alternate between the two verified roles; every switch renews the grant.
    for uid, server in [('88','second'), ('77','official'), ('88','second'), ('77','official')]:
        await login.renew(principal, row['grant_id'], role_id=uid, server_id=server)
        assert visible() == expected
    assert accounts.describe(scopes['77'])['version'] == 5
    # A role outside the verified set is refused without touching the grant.
    with pytest.raises(LoginError):
        await login.renew(principal, row['grant_id'], role_id='99', server_id='official')
    assert accounts.describe(scopes['77'])['version'] == 5 and visible() == expected
    # A renewal that comes back with an unverified role is an identity change: older
    # snapshots, inbox entries and late results from the old revisions stay hidden.
    provider.returned_role = '99'
    await login.renew(principal, row['grant_id'], role_id='88', server_id='second')
    assert visible() == ({'77':None, '88':None}, [], None)
    snapshots.save_scoped(scopes['77'], 'account', '{"late":true}', 5)
    assert query.read(scopes['77'], 'account').payload is None
    # Re-authorization starts a new generation too.
    provider.returned_role = None
    for scope in scopes.values():
        snapshots.save_scoped(scope, 'account', '{"current":true}', 6)
    assert query.read(scopes['77'], 'account').payload == {'current':True}
    clock[0] += 61
    await authorize(login)
    assert query.read(scopes['77'], 'account').payload is None
    reminders.close()
    await query.runtime.aclose()


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
