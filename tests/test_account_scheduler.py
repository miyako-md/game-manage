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


@pytest.mark.parametrize('method', ['save_scoped', 'record_poll_scoped'])
async def test_storage_failure_logs_safe_code_and_keeps_queue_usable(tmp_path, monkeypatch, caplog, method):
    import sqlite3
    accounts, scope, store, query = await query_fixture(tmp_path)
    polling = scheduler(tmp_path, accounts, query)
    await polling.poll_once(scope, 'account')
    original = getattr(store, method)
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError('private credential and snapshot details')
    monkeypatch.setattr(store, method, fail)
    polling.start(periodic=False)
    try:
        query.request_refresh(scope, 'account')
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
