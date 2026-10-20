from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from game_assistant.accounts.models import AccountScope
from game_assistant.reminder_policy import ReminderRule, stamina_candidates, in_quiet_time
from game_assistant.scoped_reminders import ReminderStore, ScopedReminderService
from game_assistant.models import StaminaInfo, FetchResult
from tests.test_account_queries import query_fixture

NOW = datetime(2026, 10, 14, 8, tzinfo=timezone.utc)
SCOPE = AccountScope('u', 'a', 'r')


def test_stamina_pushed_over_the_cap_still_counts_as_full():
    # Items can lift stamina above its maximum; the local reminder always treated that as full.
    rule = ReminderRule(enabled=True, threshold_percent=90, notify_full=True)
    value = dict(current=260, maximum=240, updated_at=NOW.isoformat())
    assert [r['rule'] for r in stamina_candidates(value, rule, NOW)] == ['full']
    assert stamina_candidates(dict(value, current=-1), rule, NOW) == []


def test_threshold_edges_unknown_real_zero_and_stale_reading():
    rule = ReminderRule(enabled=True, threshold_percent=90, city_threshold_percent=90, notify_full=True)
    value = dict(current=89, maximum=100, city_current=None, city_maximum=100, updated_at=NOW.isoformat())
    assert stamina_candidates(value, rule, NOW) == []
    value['current'] = 90
    assert [r['rule'] for r in stamina_candidates(value, rule, NOW)] == ['threshold']
    value['current'] = 100
    assert [r['rule'] for r in stamina_candidates(value, rule, NOW)] == ['full']
    value['city_current'] = 0
    assert [r['rule'] for r in stamina_candidates(value, rule, NOW)] == ['full']
    value['city_current'] = 90
    assert [r['rule'] for r in stamina_candidates(value, rule, NOW)] == ['full', 'city_threshold']
    for stamp in [None, (NOW - timedelta(hours=1)).isoformat(), NOW.replace(tzinfo=None).isoformat(), (NOW + timedelta(minutes=1)).isoformat()]:
        value['updated_at'] = stamp
        assert stamina_candidates(value, rule, NOW) == []
    assert stamina_candidates(dict(value, updated_at=NOW.isoformat(), source_delayed=True), rule, NOW) == []


def test_quiet_midnight_bounds_and_default_disabled():
    rule = ReminderRule(quiet_start='22:00', quiet_end='08:00')
    for hour in [15, 22, 23]:  # Shanghai 23:00, 06:00, 07:00
        assert in_quiet_time(rule, NOW.replace(hour=hour))
    assert not in_quiet_time(rule, NOW.replace(hour=0))  # 08:00 boundary
    assert not ReminderRule().enabled
    for body in [dict(quiet_start='22:00'), dict(quiet_start='22:00', quiet_end='22:00'), dict(quiet_start='24:00', quiet_end='08:00'), dict(daily_cap=0), dict(cooldown_seconds=-1), dict(timezone='UTC')]:
        with pytest.raises(ValidationError):
            ReminderRule(**body)


def test_atomic_claim_retry_cap_cooldown_day_restart_and_scope(tmp_path):
    path = tmp_path / 'reminders.db'
    rule = ReminderRule(enabled=True, cooldown_seconds=60, daily_cap=1)
    store = ReminderStore(path)
    lease = store.claim(SCOPE, 'full', 'inbox', rule, NOW)
    assert lease
    assert not ReminderStore(path).claim(SCOPE, 'full', 'inbox', rule, NOW)
    store.finish(lease, success=False, now=NOW)
    assert not store.claim(SCOPE, 'full', 'inbox', rule, NOW + timedelta(seconds=59))
    retry = store.claim(SCOPE, 'full', 'inbox', rule, NOW + timedelta(seconds=60))
    assert retry
    store.finish(retry, success=True, now=NOW + timedelta(seconds=60))
    assert not store.claim(SCOPE, 'full', 'inbox', rule, NOW + timedelta(hours=2))
    assert ReminderStore(path).claim(SCOPE, 'full', 'inbox', rule, NOW + timedelta(days=1))
    assert store.claim(AccountScope('v', 'a', 'r'), 'full', 'inbox', rule, NOW)
    assert store.claim(AccountScope('u', 'b', 'r'), 'full', 'inbox', rule, NOW)
    assert store.claim(AccountScope('u', 'a', 's'), 'full', 'inbox', rule, NOW)
    assert store.claim(SCOPE, 'city_threshold', 'inbox', rule, NOW)
    assert store.claim(SCOPE, 'full', 'local', rule, NOW)


def test_parallel_connections_have_single_claim_and_lease_expires(tmp_path):
    path = tmp_path / 'parallel.db'
    stores = [ReminderStore(path) for _ in range(8)]
    rule = ReminderRule(enabled=True, cooldown_seconds=60)
    with ThreadPoolExecutor(8) as pool:
        claims = list(pool.map(lambda s: s.claim(SCOPE, 'full', 'inbox', rule, NOW), stores))
    assert sum(bool(x) for x in claims) == 1
    expired_retry = stores[0].claim(SCOPE, 'full', 'inbox', rule, NOW + timedelta(minutes=6))
    assert expired_retry
    previous = next(x for x in claims if x)
    assert not stores[0].finish(previous, success=True, now=NOW + timedelta(minutes=6))


async def test_poll_wires_owned_inbox_revoke_and_get_never_evaluates(tmp_path):
    from game_assistant.scheduler import AccountPollingScheduler
    from game_assistant.config import Settings
    from game_assistant.identity.models import Principal
    from game_assistant.accounts.store import AccountNotFoundError
    accounts, scope, snapshots, query = await query_fixture(tmp_path)
    service = ScopedReminderService(ReminderStore(tmp_path / 'r.db'), accounts, clock=lambda: NOW)
    service.set_rule(scope, ReminderRule(enabled=True, notify_full=True))
    scheduler = AccountPollingScheduler(accounts, query, Settings(), tmp_path, reminders=service)
    async def fetch(cap):
        return FetchResult(ok=True, payload=StaminaInfo(current=100, maximum=100, updated_at=NOW))
    query.adapter(scope).fetch = fetch
    assert service.inbox(scope) == []
    await scheduler.poll_once(scope, 'stamina')
    messages = service.inbox(scope)
    assert len(messages) == 1 and '读取时间' in messages[0]['body']
    assert messages[0]['source_read_at'] == NOW.isoformat()
    assert service.inbox(scope) == messages
    accounts.revoke(Principal(scope.user_id, False), scope.account_id)
    assert not service.get_rule(scope).enabled
    with pytest.raises(AccountNotFoundError):
        service.inbox(scope)
    with pytest.raises(AccountNotFoundError):
        service.handle_poll(scope, 'stamina', await fetch(None), 1)


def test_cooldown_crosses_shanghai_midnight_and_quiet_consumes_nothing(tmp_path):
    store = ReminderStore(tmp_path / 'day.db')
    rule = ReminderRule(enabled=True, cooldown_seconds=3600, daily_cap=1, quiet_start='22:00', quiet_end='08:00')
    before_midnight = NOW.replace(hour=15, minute=59)
    lease = store.claim(SCOPE, 'full', 'inbox', rule, before_midnight)
    store.finish(lease, success=True, now=before_midnight)
    assert not store.claim(SCOPE,'full','inbox',rule,before_midnight + timedelta(minutes=2))
    assert store.claim(SCOPE,'full','inbox',rule,before_midnight + timedelta(hours=1))
    assert stamina_candidates(dict(current=100,maximum=100,updated_at=before_midnight),rule,before_midnight) == []


async def test_inbox_preserves_rotation_history_but_not_new_authorization(tmp_path):
    from game_assistant.identity.models import Principal
    from game_assistant.accounts.store import AccountNotFoundError
    from tests.test_account_auth import setup, authorize
    db, credentials, accounts, login = setup(tmp_path)
    row = await authorize(login)
    principal = Principal('a',False)
    scope = accounts.require_scope(principal,row['account_id'],row['role_id'])
    store = ReminderStore(tmp_path/'inbox.db')
    service = ScopedReminderService(store,accounts,clock=lambda:NOW)
    service.set_rule(scope,ReminderRule(enabled=True,notify_full=True))
    service.handle_poll(scope,'stamina',FetchResult(ok=True,
        payload={'current':100,'maximum':100,'updated_at':NOW.isoformat()}),1)
    original = service.inbox(scope)
    assert len(original) == 1
    await login.renew(principal,row['grant_id'])
    assert service.inbox(scope) == original
    # A future revision must remain unreadable even inside the same generation.
    store.db.execute('UPDATE reminder_inbox SET grant_version=99')
    store.db.commit()
    assert service.inbox(scope) == []
    store.db.execute('UPDATE reminder_inbox SET grant_version=1')
    store.db.commit()
    saved = credentials.load_grant('a',row['grant_id'])
    accounts.save_verified(principal,'tajiduo',saved)
    assert service.inbox(scope) == []
    accounts.revoke(principal,scope.account_id)
    with pytest.raises(AccountNotFoundError):
        service.inbox(scope)
    store.close()
