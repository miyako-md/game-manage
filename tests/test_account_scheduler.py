import asyncio

import pytest

from game_assistant.config import Settings
from game_assistant.identity.models import Principal
from game_assistant.models import FetchResult
from game_assistant.scheduler import AccountPollingScheduler, SchedulerAlreadyRunning
from tests.test_account_queries import query_fixture


def scheduler(tmp_path, accounts, query, **kwargs):
    result = AccountPollingScheduler(accounts, query, Settings(), tmp_path, **kwargs)
    query.scheduler = result
    return result


async def test_refresh_coalesces_same_scope(tmp_path):
    accounts, scope, store, query = await query_fixture(tmp_path)
    gate = asyncio.Event()
    async def blocked(cap):
        await gate.wait()
        return FetchResult(ok=True, payload={'level': None})
    query.runtime.for_scope(scope).get('nte').fetch = blocked
    polling = scheduler(tmp_path, accounts, query)
    polling.start(periodic=False)
    first = query.request_refresh(scope, 'account')
    second = query.request_refresh(scope, 'account')
    assert first.state == 'queued' and second.state == 'coalesced'
    assert first.job_id == second.job_id
    gate.set()
    await polling.drain()
    assert query.read(scope, 'account').state == 'ok'
    await polling.shutdown()


async def test_old_grant_result_discarded(tmp_path):
    accounts, scope, store, query = await query_fixture(tmp_path)
    async def changing(cap):
        accounts.revoke(Principal('a', False), scope.account_id)
        return FetchResult(ok=True, payload={'old': True}, credential_version=1)
    query.runtime.for_scope(scope).get('nte').fetch = changing
    polling = scheduler(tmp_path, accounts, query)
    result = await polling.poll_once(scope, 'account')
    assert result.error_kind == 'account_changed'
    assert store.get_scoped(scope, 'account') is None
    assert store.get_poll_status_scoped(scope, 'account') is None


async def test_failed_poll_keeps_snapshot_and_pauses_auth_expired(tmp_path):
    accounts, scope, store, query = await query_fixture(tmp_path)
    polling = scheduler(tmp_path, accounts, query)
    await polling.poll_once(scope, 'account')
    previous = store.get_scoped(scope, 'account')
    calls = 0
    async def failure(cap):
        nonlocal calls
        calls += 1
        return FetchResult(ok=False, error_kind='auth_expired')
    query.runtime.for_scope(scope).get('nte').fetch = failure
    await polling.poll_once(scope, 'account')
    assert store.get_scoped(scope, 'account') == previous
    assert query.read(scope, 'account').state == 'auth_expired'
    await polling.tick()
    await polling.drain()
    assert calls == 1  # account paused, but other never-polled capability may run


async def test_second_scheduler_cannot_start(tmp_path):
    accounts, scope, store, query = await query_fixture(tmp_path)
    first = scheduler(tmp_path, accounts, query)
    second = scheduler(tmp_path, accounts, query)
    first.start(periodic=False)
    with pytest.raises(SchedulerAlreadyRunning):
        second.start(periodic=False)
    import subprocess
    import sys
    code = "from game_assistant.scheduler import _SchedulerLease; import sys; _SchedulerLease(sys.argv[1]).acquire()"
    other_process = subprocess.run([sys.executable,'-c',code,str(tmp_path)],capture_output=True,text=True)
    assert other_process.returncode != 0
    assert 'SchedulerAlreadyRunning' in other_process.stderr
    await first.shutdown()
    second.start(periodic=False)
    await second.shutdown()


async def test_public_source_polled_once(tmp_path):
    accounts, scope, store, query = await query_fixture(tmp_path)
    calls = []
    class Public:
        sources = ['nte']
        async def poll(self, game):
            calls.append(game)
        def provider(self, game):
            return 'bilibili'
    polling = scheduler(tmp_path, accounts, query, public=Public())
    polling.start(periodic=False)
    await polling.tick()
    await polling.tick()
    await polling.drain()
    assert calls == ['nte']
    await polling.shutdown()


async def test_provider_concurrency_and_backoff(tmp_path):
    accounts, scope, store, query = await query_fixture(tmp_path)
    active = maximum = 0
    async def fetch(cap):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(.01)
        active -= 1
        return FetchResult(ok=False, error_kind='source_error')
    query.runtime.for_scope(scope).get('nte').fetch = fetch
    polling = scheduler(tmp_path, accounts, query)
    polling.start(periodic=False)
    query.request_refresh(scope, 'account')
    query.request_refresh(scope, 'stamina')
    await polling.drain()
    assert maximum == 1
    first = query.request_refresh(scope, 'account')
    second = query.request_refresh(scope, 'account')
    assert second.state == 'coalesced' and first.job_id == second.job_id
    await polling.shutdown()


async def test_restart_retains_backoff_and_auth_pause(tmp_path):
    accounts, scope, store, query = await query_fixture(tmp_path)
    from datetime import datetime, timezone
    store.record_poll_scoped(scope,'account',FetchResult(ok=False,error_kind='source_error'),1,
                             now=datetime.now(timezone.utc))
    polling = scheduler(tmp_path, accounts, query)
    polling.start(periodic=False)
    query.request_refresh(scope,'account')
    await asyncio.sleep(.02)
    assert query.read(scope,'account').state == 'error'
    await polling.shutdown()
    store.record_poll_scoped(scope,'account',FetchResult(ok=False,error_kind='auth_expired'),1)
    replacement = scheduler(tmp_path, accounts, query)
    replacement.start(periodic=False)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        query.request_refresh(scope,'stamina')
    assert error.value.status_code == 409
    await replacement.shutdown()


async def test_reauthorization_cancels_old_queued_work(tmp_path):
    accounts, scope, store, query = await query_fixture(tmp_path)
    gate = asyncio.Event()
    async def blocked(cap):
        await gate.wait()
        return FetchResult(ok=True,payload={'level':None})
    query.runtime.for_scope(scope).get('nte').fetch = blocked
    polling = scheduler(tmp_path,accounts,query)
    polling.start(periodic=False)
    first = query.request_refresh(scope,'account')
    info = accounts.describe(scope)
    saved = accounts.credentials.load_grant(scope.user_id, info['grant_id'])
    accounts.revoke(Principal('a',False),scope.account_id)
    accounts.save_verified(Principal('a',False), 'tajiduo', saved)
    second = query.request_refresh(scope,'account')
    assert second.state == 'queued' and second.job_id != first.job_id
    gate.set()
    await polling.drain()
    assert store.get_scoped(scope,'account')['grant_version'] == 3
    await polling.shutdown()


async def test_bad_grant_does_not_abort_public_tick(tmp_path):
    from tests.test_account_queries import corrupt_fixture
    accounts,query,first,second = await corrupt_fixture(tmp_path)
    calls = []
    class Public:
        sources = ['nte']
        def provider(self,game):
            return 'public_sources'
        async def poll(self,game):
            calls.append(game)
    polling = scheduler(tmp_path,accounts,query,public=Public())
    polling.start(periodic=False)
    await polling.tick()
    await polling.drain()
    assert calls == ['nte']
    await polling.shutdown()
    await query.runtime.aclose()


@pytest.mark.parametrize('method', ['save_scoped', 'record_poll_scoped', 'get_poll_status_scoped'])
async def test_storage_failure_logs_safe_code_and_keeps_queue_usable(tmp_path, monkeypatch, caplog, method):
    import sqlite3
    accounts, scope, store, query = await query_fixture(tmp_path)
    polling = scheduler(tmp_path, accounts, query)
    await polling.poll_once(scope, 'account')
    original = getattr(store, method)
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError('private credential and snapshot details')
    polling.start(periodic=False)
    try:
        query.request_refresh(scope, 'account')
        monkeypatch.setattr(store, method, fail)
        await polling.drain()
        assert polling.refresh_state(scope, 'account') == 'idle'
        assert polling._due[(scope, 'account')] > polling.clock()
        messages = [record.getMessage() for record in caplog.records
                    if record.name == 'game_assistant.scheduler']
        assert messages == ['scoped_refresh_failed']
        assert 'private credential' not in caplog.text
        monkeypatch.setattr(store, method, original)
        query.request_refresh(scope, 'account')
        await polling.drain()
        assert query.read(scope, 'account').state == 'ok'
    finally:
        await polling.shutdown()


async def test_queued_scope_removal_is_not_logged_as_storage_failure(tmp_path, monkeypatch, caplog):
    from game_assistant.accounts.store import AccountNotFoundError
    accounts, scope, store, query = await query_fixture(tmp_path)
    polling = scheduler(tmp_path, accounts, query)
    polling.start(periodic=False)
    try:
        query.request_refresh(scope, 'account')
        def removed(*args, **kwargs):
            raise AccountNotFoundError()
        monkeypatch.setattr(accounts, 'describe', removed)
        await polling.drain()
        assert not [record for record in caplog.records
                    if record.name == 'game_assistant.scheduler']
        assert polling.refresh_state(scope, 'account') == 'idle'
    finally:
        await polling.shutdown()


@pytest.mark.parametrize('manual',[True,False])
async def test_successful_rotation_unpauses_old_token_failure(tmp_path, manual):
    from game_assistant.accounts.runtime import AccountRuntime
    from game_assistant.accounts.query import AccountQuery
    from game_assistant.models import Capability
    from game_assistant.snapshots import SnapshotStore
    from tests.test_account_auth import setup,authorize
    db, credentials, accounts, login = setup(tmp_path)
    row = await authorize(login)
    principal = Principal('a',False)
    scope = accounts.require_scope(principal,row['account_id'],row['role_id'])
    runtime = AccountRuntime(accounts,Settings(),tmp_path/'runtime',login=login)
    store = SnapshotStore(str(tmp_path/'snapshots.db'))
    store.save_scoped(scope,'account','{"level":40}',1)
    store.record_poll_scoped(scope,'account',FetchResult(ok=False,error='old token',error_kind='auth_expired'),1)
    old = store.get_scoped(scope,'account')
    query = AccountQuery(accounts,runtime,store)
    polling = scheduler(tmp_path,accounts,query)
    assert polling._paused(scope)
    await login.renew(principal,row['grant_id'])
    adapter = runtime.for_scope(scope).get('nte')
    adapter.capabilities = [Capability.ACCOUNT]
    async def fresh():
        return FetchResult(ok=True,payload={'level':41})
    adapter.fetch_account = fresh
    assert not polling._paused(scope)
    assert query.read(scope,'account').payload == {'level':40}
    assert query.read(scope,'account').fetched_at == old['fetched_at']
    assert query.read(scope,'account').state == 'never'
    status = query.status(scope,'account')
    assert status['refresh_required'] and status['error'] is None and status['error_kind'] is None
    assert store.get_poll_status_scoped(scope,'account',grant_version=1)['state'] == 'auth_expired'
    clock = [1000]
    polling.clock = lambda:clock[0]
    assert polling._persisted_due(scope,'account') == clock[0]
    polling.start(periodic=False)
    try:
        if manual:
            assert query.request_refresh(scope,'account').state == 'queued'
        else:
            await polling.tick()
            clock[0] += 31
            await polling.tick()
        await polling.drain()
        assert query.read(scope,'account').payload == {'level':41}
        assert query.read(scope,'account').state == 'ok'
    finally:
        await polling.shutdown()
        await runtime.aclose()


def challenge_payload(fetched_at, *, failed=()):
    from game_assistant.endfield_challenges import CHALLENGE_KINDS, build_challenge_report
    return {'schema_version':1,'reports':[build_challenge_report(
        {'supported':True,'kind':kind,'fetched_at':None,'stale':True} if kind in failed else
        {'supported':True,'kind':kind,'fetched_at':fetched_at,'stale':False,
         'records':[{'id':kind+'-1','name':kind+' '+fetched_at}],'summary':{'highest':0}},kind=kind)
        for kind in CHALLENGE_KINDS]}


async def skland_fixture(tmp_path, **settings):
    from types import SimpleNamespace
    from game_assistant.accounts.query import AccountQuery
    from game_assistant.models import Capability
    from game_assistant.registry import GameRegistry
    from game_assistant.snapshots import SnapshotStore
    from tests.test_account_auth import setup
    db, credentials, accounts, login = setup(tmp_path)
    row = accounts.save_verified(Principal('a',False),'skland',
        {'user_id':'sk-user','role_id':'sk-role','server_id':'1','cred':'sk-secret'})
    scope = accounts.require_scope(Principal('a',False),row['account_id'],row['role_id'])
    class Adapter:
        game_id, display_name = 'endfield', '终末地'
        capabilities = [Capability.ACCOUNT, Capability.COMBAT]
        results = []
        async def fetch(self, capability):
            return self.results.pop(0) if capability == Capability.COMBAT else FetchResult(ok=True,payload={'base':{}})
        def prepare_refresh(self):
            pass
    adapter = Adapter()
    registry = GameRegistry()
    registry.register(adapter)
    store = SnapshotStore(str(tmp_path/'snapshots.db'))
    query = AccountQuery(accounts,SimpleNamespace(for_scope=lambda scope:registry),store)
    polling = AccountPollingScheduler(accounts,query,Settings(**settings),tmp_path)
    query.scheduler = polling
    polling.clock = lambda: 1000.0
    return accounts, scope, store, query, adapter, polling, login


async def test_endfield_challenges_use_their_own_interval_and_failure_backoff(tmp_path):
    accounts, scope, store, query, adapter, polling, _ = await skland_fixture(tmp_path,
        cloud_private_poll_seconds=600, cloud_endfield_challenge_poll_seconds=1800)
    assert query.capabilities(scope) == ['account', 'combat']
    adapter.results = [FetchResult(ok=True,payload=challenge_payload('2026-10-21T00:00:00+00:00')),
                       FetchResult(ok=False,error='raw upstream text',error_kind='source_error',error_code=429),
                       FetchResult(ok=False,error_kind='source_error',error_code=429)]
    await polling.poll_once(scope,'account')
    await polling.poll_once(scope,'combat')
    assert polling._due[(scope,'account')] == 1600 and polling._due[(scope,'combat')] == 2800
    assert 1000 + 1790 < polling._persisted_due(scope,'combat') <= 2800
    saved = store.get_scoped(scope,'combat')
    # 429 waits at least the challenge interval instead of the 60 s / 120 s backoff.
    for _ in range(2):
        await polling.poll_once(scope,'combat')
        assert polling._due[(scope,'combat')] == 1000 + 1800
        assert 1000 + 1790 < polling._persisted_due(scope,'combat') <= 2800
    status = query.status(scope,'combat')
    assert (status['state'], status['error_code'], status['consecutive_failures']) == ('error', 429, 2)
    assert 'raw upstream' not in str(status)
    assert store.get_scoped(scope,'combat') == saved and query.read(scope,'combat').state == 'error'
    assert query.status(scope,'account')['error_code'] is None


async def test_non_rate_limited_failures_keep_the_short_backoff(tmp_path):
    accounts, scope, store, query, adapter, polling, _ = await skland_fixture(tmp_path,
        cloud_endfield_challenge_poll_seconds=1800)
    adapter.results = [FetchResult(ok=False,error_kind='source_error',error_code=503),
                       FetchResult(ok=False,error_kind='source_error')]
    for delay in (60, 120):
        await polling.poll_once(scope,'combat')
        assert polling._due[(scope,'combat')] == 1000 + delay


async def test_partial_challenge_failure_keeps_last_success_of_that_kind(tmp_path, caplog):
    import json
    accounts, scope, store, query, adapter, polling, _ = await skland_fixture(tmp_path)
    first, second = '2026-10-21T00:00:00+00:00', '2026-10-21T00:15:00+00:00'
    adapter.results = [FetchResult(ok=True,payload=challenge_payload(first,failed=('crisis',))),
                       FetchResult(ok=True,payload=challenge_payload(second,failed=('monument',)),error_code=429,
                                   failure_codes='monument:http:429')]
    await polling.poll_once(scope,'combat')
    stored = {r['kind']:r for r in json.loads(store.get_scoped(scope,'combat')['payload'])['reports']}
    assert stored['crisis']['available'] is False and stored['crisis']['stale'] is True
    assert stored['crisis']['summary']['listed_count'] is None  # never observed is not zero
    await polling.poll_once(scope,'combat')
    payload = json.loads(store.get_scoped(scope,'combat')['payload'])
    assert set(payload) == {'schema_version','reports'}
    stored = {r['kind']:r for r in payload['reports']}
    assert (stored['war']['fetched_at'], stored['war']['stale']) == (second, False)
    assert (stored['monument']['fetched_at'], stored['monument']['stale']) == (first, True)
    assert stored['monument']['records'][0]['name'] == 'monument '+first
    assert (stored['crisis']['fetched_at'], stored['crisis']['stale']) == (second, False)
    status = query.status(scope,'combat')
    assert (status['state'], status['error_code'], status['consecutive_failures']) == ('ok', 429, 0)
    assert polling._due[(scope,'combat')] == 1900
    messages = [r.getMessage() for r in caplog.records if r.name == 'game_assistant.scheduler']
    assert messages[-1] == ('scoped_poll_failed game=endfield capability=combat state=ok error_code=429 '
                            'failed_kinds=monument failed_codes=monument:http:429')
    assert 'failed_codes' not in str(status) and 'http:429' not in str(status)
    assert scope.account_id not in caplog.text and scope.role_id not in caplog.text


async def test_challenge_merge_never_adopts_a_replaced_grant(tmp_path):
    import json
    accounts, scope, store, query, adapter, polling, _ = await skland_fixture(tmp_path)
    store.save_scoped(scope,'combat',json.dumps(challenge_payload('2026-10-20T00:00:00+00:00')),1)
    accounts.save_verified(Principal('a',False),'skland',
        {'user_id':'sk-user','role_id':'sk-role','server_id':'1','cred':'rotated'})
    assert accounts.describe(scope)['version'] > 1
    adapter.results = [FetchResult(ok=True,payload=challenge_payload('2026-10-21T00:00:00+00:00',failed=('war',)))]
    await polling.poll_once(scope,'combat')
    stored = {r['kind']:r for r in json.loads(store.get_scoped(scope,'combat')['payload'])['reports']}
    assert stored['war']['available'] is False and stored['monument']['fetched_at'] == '2026-10-21T00:00:00+00:00'


async def test_snapshot_staleness_follows_the_capability_interval(tmp_path):
    import json
    import httpx
    from fastapi import FastAPI
    from game_assistant.accounts.routes import install_account_routes
    from game_assistant.identity.dependencies import require_user
    accounts, scope, store, query, adapter, polling, login = await skland_fixture(tmp_path)
    app = FastAPI()
    app.state.settings = Settings(cloud_private_poll_seconds=60, cloud_endfield_challenge_poll_seconds=3600)
    app.dependency_overrides[require_user] = lambda: Principal('a',False)
    install_account_routes(app,accounts,login,query=query)
    for cap in ('account','combat'):
        store.save_scoped(scope,cap,json.dumps(challenge_payload('2026-10-21T00:00:00+00:00')),1)
        store.record_poll_scoped(scope,cap,FetchResult(ok=True),1)
    from datetime import datetime, timedelta, timezone
    store._conn.execute('UPDATE scoped_snapshots SET fetched_at=?',
                        ((datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),))
    store._conn.commit()
    prefix = f'/api/accounts/{scope.account_id}/roles/{scope.role_id}/snapshot/'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://cloud.example') as client:
        account, combat = [(await client.get(prefix+cap)).json() for cap in ('account','combat')]
    assert account['stale'] is True and combat['stale'] is False
    assert combat['poll_status']['error_code'] is None


async def test_failed_poll_logs_short_codes_but_never_messages(tmp_path, caplog):
    accounts, scope, store, query, adapter, polling, _ = await skland_fixture(tmp_path)
    adapter.results = [FetchResult(ok=False,error='RAW upstream message',error_kind='source_error',
                                   failure_codes='war:10001,monument:parse:KeyError,crisis:10001')]
    await polling.poll_once(scope,'combat')
    messages = [r.getMessage() for r in caplog.records if r.name == 'game_assistant.scheduler']
    assert messages[-1] == ('scoped_poll_failed game=endfield capability=combat state=error error_code=None '
                            'failed_kinds=- failed_codes=war:10001,monument:parse:KeyError,crisis:10001')
    status = query.status(scope,'combat')
    assert 'RAW' not in caplog.text and 'RAW' not in str(status) and '10001' not in str(status)
    async def broken(capability):
        raise TimeoutError('RAW secret')
    adapter.fetch = broken
    await polling.poll_once(scope,'combat')
    assert caplog.records[-1].getMessage().endswith('failed_codes=exception:TimeoutError')
    assert 'RAW' not in caplog.text and scope.account_id not in caplog.text
