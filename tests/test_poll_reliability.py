import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult, GameEvent, StaminaInfo
from game_assistant.reminder import ReminderEngine
from game_assistant.reminder_store import ReminderDedup
from game_assistant.scheduler import PollingScheduler
from game_assistant.snapshots import SnapshotStore
from tests.test_reminder import FakeNotify


def engine(tmp_path, **settings):
    return ReminderEngine(ReminderDedup(str(tmp_path / 'reminders.db')),
                          FakeNotify(), Settings(**settings))


def freeze(monkeypatch, instant):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
    monkeypatch.setattr('game_assistant.reminder.datetime', Frozen)


async def test_daily_reminders_reset_at_beijing_midnight(tmp_path, monkeypatch):
    eng = engine(tmp_path)
    result = FetchResult(ok=True, payload=StaminaInfo(current=240, maximum=240,
                        updated_at=datetime.now(timezone.utc)))
    for hour, minute in [(15, 59), (16, 1)]:
        freeze(monkeypatch, datetime(2026, 9, 14, hour, minute, tzinfo=timezone.utc))
        await eng.handle_poll('g', 'G', Capability.STAMINA, result)
    assert len(eng.notifier.sent) == 2


@pytest.mark.parametrize('seconds,expected', [(0, False), (-1, False), (1, True),
    (3 * 86400, True), (3 * 86400 + 1, False)])
async def test_event_window_uses_strict_seconds(tmp_path, monkeypatch, seconds, expected):
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    freeze(monkeypatch, now)
    eng = engine(tmp_path, activity_remind_days=3)
    await eng.handle_poll('g', 'G', Capability.EVENTS, FetchResult(ok=True,
        payload=[GameEvent(name='event', end_at=now + timedelta(seconds=seconds))]))
    assert bool(eng.notifier.sent) is expected
    if seconds == 1:
        assert '还剩 1 天' in eng.notifier.sent[0][1]
        assert '09-14 08:00' in eng.notifier.sent[0][1]


async def test_reverse_event_interval_never_notifies(tmp_path, monkeypatch):
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    freeze(monkeypatch, now)
    eng = engine(tmp_path)
    await eng.handle_poll('g', 'G', Capability.EVENTS, FetchResult(ok=True,
        payload=[GameEvent(name='bad', start_at=now + timedelta(days=2),
                           end_at=now + timedelta(days=1))]))
    assert eng.notifier.sent == []


@pytest.mark.parametrize('kind', ['offline', 'unconfigured'])
async def test_expected_unavailable_breaks_failure_streak_without_alert(tmp_path, kind):
    eng = engine(tmp_path, fail_notify_threshold=2)
    for result in [FetchResult(ok=False, error='source', error_kind='source_error'),
                   FetchResult(ok=False, error='expected', error_kind=kind),
                   FetchResult(ok=False, error='source', error_kind='source_error')]:
        await eng.handle_poll('g', 'G', Capability.ACCOUNT, result)
    assert eng.notifier.sent == []


def test_poll_state_survives_restart_and_recovers_without_erasing_snapshot(tmp_path):
    db = str(tmp_path / 'state.db')
    store = SnapshotStore(db)
    store.save('g', 'events', '[{"name":"old"}]')
    success_at = store.get('g', 'events')['fetched_at']
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    status = store.record_poll('g', 'events', FetchResult(ok=False,
        error='无法解析活动', error_kind='invalid_data'), now=now)
    assert status == dict(game_id='g', capability='events', state='error',
        last_attempt_at=now.isoformat(), last_success_at=success_at,
        consecutive_failures=1, error='无法解析活动', error_kind='invalid_data')
    restarted = SnapshotStore(db)
    assert restarted.get_poll_status('g', 'events') == status
    status = restarted.record_poll('g', 'events', FetchResult(ok=False, error='source'))
    assert status['consecutive_failures'] == 2
    assert restarted.get('g', 'events')['payload'] == '[{"name":"old"}]'
    status = restarted.record_poll('g', 'events', FetchResult(ok=True), now=now)
    assert status['state'] == 'ok' and status['last_success_at'] == now.isoformat()
    assert status['consecutive_failures'] == 0 and status['error'] is None
    assert status['error_kind'] is None


@pytest.mark.parametrize('kind,state,count', [('offline','offline',0),
    ('unconfigured','unconfigured',0), ('auth_expired','auth_expired',1),
    ('source_error','error',1)])
def test_poll_state_classifies_unavailability(tmp_path, kind, state, count):
    store = SnapshotStore(':memory:')
    result = store.record_poll('g', 'account', FetchResult(ok=False, error_kind=kind))
    assert result['state'] == state and result['consecutive_failures'] == count
    assert result['last_success_at'] is None


def test_account_switch_clears_only_private_poll_status():
    store = SnapshotStore(':memory:')
    for game, cap in [('g','account'), ('g','events'), ('other','account')]:
        store.record_poll(game, cap, FetchResult(ok=True))
    store.clear_private('g')
    assert store.get_poll_status('g', 'account') is None
    assert len(store.list_poll_status('g')) == 1
    assert len(store.list_poll_status()) == 2


def scheduler(adapter, store=None, reminder=None):
    reg = SimpleNamespace(get=lambda _: adapter)
    return PollingScheduler(reg, store or SnapshotStore(':memory:'), Settings(),
                            FakeNotify(), reminder=reminder)


async def test_same_capability_refreshes_are_serialized():
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0
    async def fetch(_):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return FetchResult(ok=True, payload={'call': calls})
    sched = scheduler(SimpleNamespace(fetch=fetch, display_name='G'))
    first = asyncio.create_task(sched.poll_once('g', Capability.ACCOUNT))
    await entered.wait()
    second = asyncio.create_task(sched.poll_once('g', Capability.ACCOUNT))
    await asyncio.sleep(0)
    observed_calls = calls
    release.set()
    await asyncio.gather(first, second)
    assert observed_calls == 1
    assert sched.store.get_poll_status('g', 'account')['state'] == 'ok'


async def test_account_changed_result_cannot_write_status_or_snapshot(tmp_path):
    # Full stamina would notify if the stale result reached the reminder engine.
    full = StaminaInfo(current=240, maximum=240, updated_at=datetime.now(timezone.utc))
    async def fetch(_):
        return FetchResult(ok=True, payload=full, credential_version=1)
    eng = engine(tmp_path)
    sched = scheduler(SimpleNamespace(fetch=fetch, display_name='G',
                      _auth=SimpleNamespace(version=lambda _: 2)), reminder=eng)
    result = await sched.poll_once('g', Capability.ACCOUNT)
    assert result.error_kind == 'account_changed'
    assert sched.store.get_poll_status('g', 'account') is None
    assert sched.store.get('g', 'account') is None
    assert eng.notifier.sent == []


async def test_restart_preserves_failure_threshold_for_notifications(tmp_path):
    async def fetch(_):
        return FetchResult(ok=False, error='接口失败', error_kind='source_error')
    adapter = SimpleNamespace(fetch=fetch, display_name='G')
    db = str(tmp_path / 'snapshots.db')
    for _ in range(2):
        eng = engine(tmp_path, fail_notify_threshold=2)
        sched = scheduler(adapter, SnapshotStore(db), eng)
        await sched.poll_once('g', Capability.ACCOUNT)
    assert len(eng.notifier.sent) == 1


async def test_unhandled_source_exception_records_failure_without_sensitive_details():
    async def fetch(_):
        raise RuntimeError('https://secret.example/?token=secret-token')
    sched = scheduler(SimpleNamespace(fetch=fetch, display_name='G'))
    result = await sched.poll_once('g', Capability.ACCOUNT)
    assert not result.ok and result.error_kind == 'source_error'
    assert 'secret-token' not in sched.store.get_poll_status('g', 'account')['error']
