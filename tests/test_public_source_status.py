"""Effective public status must follow the data served, independent of read order."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from game_assistant.models import FetchResult
from tests.test_bilibili_integration import setup
from tests.test_bilibili_source import UID
from tests.test_public_content import notice


def _date_text(value):
    # Windows Python 3.11 strftime cannot encode Chinese under English locales.
    return f'{value.year:04d}年{value.month:02d}月{value.day:02d}日'


def seed(app, store, *, future=False):
    now = datetime.now(timezone.utc)
    start, end = now - timedelta(days=2), now + timedelta(days=20)
    body = ('《异环》1.4版本「祷歌为谁而诵」更新公告\n'
            f'更新维护时间：{_date_text(start)}06:00\n'
            '● 「环期赠礼」签到活动\n'
            f'活动时间：{_date_text(start)}版本更新后-{_date_text(end)}05:59')
    row = notice(body, published=start.isoformat())
    row.update(source_uid=UID, reason='accepted', reason_text='accepted',
               fetched_at=now.isoformat(), content_status='full')
    rows = [row]
    if future:
        upcoming = now + timedelta(days=7)
        rows.append({**row, 'id': 'future', 'body': body.replace('1.4', '1.5').replace(
            _date_text(start), _date_text(upcoming)),
            'title': '《异环》1.5版本更新公告', 'published_at': now.isoformat()})
    app.state.bilibili.store.save_rows('nte', UID, rows)
    app.state.bilibili.store.set_state('nte', UID, status='ok', failures=0,
        last_attempt=now.isoformat(), last_success=now.isoformat())
    store.record_poll('nte', 'events', FetchResult(ok=False,
        error='未找到版本公告，保留上次成功日历', error_kind='source_error'))
    return row, now


def effective(client, capability='events'):
    return next(row for row in client.get('/api/status').json()['collection']
                if row['game_id'] == 'nte' and row['capability'] == capability)


def without_observation(status):
    return {k: v for k, v in status.items() if k != 'observed_at'}


@pytest.mark.parametrize('order', [('status', 'snapshot'), ('snapshot', 'status')])
def test_successful_bilibili_calendar_wins_native_failure_in_either_read_order(tmp_path, order):
    app, store = setup(tmp_path)
    seed(app, store, future=True)
    original = store.get_poll_status('nte', 'events')
    with TestClient(app, base_url='http://127.0.0.1:8010') as client:
        for _ in range(3):
            results = {}
            for kind in order:
                results[kind] = effective(client) if kind == 'status' else client.get(
                    '/api/games/nte/snapshot/events').json()
            snap, status = results['snapshot'], results['status']
            assert status['state'] == 'ok'
            assert status['error'] is None and status['error_kind'] is None
            assert without_observation(status) == without_observation(snap['poll_status'])
            assert snap['version'] == '1.4' and len(snap['payload']) == 1
            assert snap['stale'] is False
            assert status['source_statuses']['community']['error'] == original['error']
        assert store.get_poll_status('nte', 'events') == original
        assert store.get('nte', 'events') is None
        assert effective(client, 'news')['state'] == 'ok'


def test_bilibili_failure_is_visible_with_retained_events_and_consistent_error_kind(tmp_path):
    app, store = setup(tmp_path)
    _, now = seed(app, store)
    app.state.bilibili.store.set_state('nte', UID, status='error', failures=2,
        message='B站采集失败，保留成功记录', last_attempt=(now + timedelta(seconds=1)).isoformat())
    with TestClient(app, base_url='http://127.0.0.1:8010') as client:
        snap = client.get('/api/games/nte/snapshot/events').json()
        status = effective(client)
        assert without_observation(status) == without_observation(snap['poll_status'])
        assert status['state'] == 'error' and status['error_kind'] == 'source_error'
        assert status['error'] == 'B站采集失败，保留成功记录'
        assert status['consecutive_failures'] == 2
        assert status['last_success_at'] == now.isoformat()
        assert snap['stale'] is True and len(snap['payload']) == 1


def test_success_time_tracks_collection_and_expired_collection_stays_stale(tmp_path):
    app, store = setup(tmp_path)
    row, now = seed(app, store)
    row['fetched_at'] = (now - timedelta(days=1)).isoformat()
    app.state.bilibili.store.save_rows('nte', UID, [row])
    with TestClient(app, base_url='http://127.0.0.1:8010') as client:
        snap = client.get('/api/games/nte/snapshot/events').json()
        assert snap['poll_status']['last_success_at'] == now.isoformat()
        assert not snap['stale']  # An unchanged post is not a failed collection.
        old = (now - timedelta(days=1)).isoformat()
        app.state.bilibili.store.set_state('nte', UID, last_success=old, last_attempt=old)
        snap = client.get('/api/games/nte/snapshot/events').json()
        assert snap['stale'] and snap['payload'][0]['source_stale']
        assert effective(client)['stale'] is True


def test_partial_body_failure_is_not_hidden_by_successful_collection(tmp_path):
    app, store = setup(tmp_path)
    row, _ = seed(app, store)
    row.update(content_status='stale', last_observation_error='本次正文获取不完整，保留上次完整记录')
    app.state.bilibili.store.save_rows('nte', UID, [row])
    with TestClient(app, base_url='http://127.0.0.1:8010') as client:
        snap = client.get('/api/games/nte/snapshot/events').json()
        status = effective(client)
        assert status['state'] == 'error' and status['error_kind'] == 'partial_data'
        assert without_observation(status) == without_observation(snap['poll_status'])
        assert len(snap['payload']) == 1 and snap['payload'][0]['source_stale']


def test_native_fallback_and_private_failures_are_not_suppressed(tmp_path):
    app, store = setup(tmp_path)
    error = FetchResult(ok=False, error='真实来源错误', error_kind='source_error')
    store.save('nte', 'events', json.dumps([{'name': '旧活动'}]))
    store.record_poll('nte', 'events', error)
    store.record_poll('nte', 'stamina', FetchResult(ok=False, error='登录失效', error_kind='auth_expired'))
    with TestClient(app, base_url='http://127.0.0.1:8010') as client:
        snap = client.get('/api/games/nte/snapshot/events').json()
        assert snap['primary_source'] == 'community' and snap['stale']
        assert effective(client)['error'] == '真实来源错误'
        assert effective(client, 'stamina')['state'] == 'auth_expired'


@pytest.mark.parametrize('bili_state', ['idle', 'ok'])
def test_no_usable_public_data_preserves_native_failure(tmp_path, bili_state):
    app, store = setup(tmp_path)
    store.record_poll('nte', 'events', FetchResult(ok=False, error='原生首次采集失败', error_kind='source_error'))
    app.state.bilibili.store.set_state('nte', UID, status=bili_state)
    with TestClient(app, base_url='http://127.0.0.1:8010') as client:
        snap = client.get('/api/games/nte/snapshot/events').json()
        assert not snap['payload']
        status = effective(client)
        assert status['state'] == 'error' and status['error'] == '原生首次采集失败'
        assert without_observation(status) == without_observation(snap['poll_status'])


def test_mixed_fresh_and_failed_articles_keep_per_row_staleness(tmp_path):
    app, store = setup(tmp_path)
    row, now = seed(app, store)
    row.update(content_status='stale', last_observation_error='正文获取不完整')
    fresh = {**row, 'id': 'fresh', 'title': '1.4版本新活动公告',
             'body': ('1.4版本新活动公告\n● 「新挑战」限时活动\n'
                      f'活动时间：{_date_text(now)}05:00-{_date_text(now + timedelta(days=2))}05:59'),
             'content_status': 'full', 'last_observation_error': '', 'published_at': now.isoformat()}
    app.state.bilibili.store.save_rows('nte', UID, [row, fresh])
    with TestClient(app, base_url='http://127.0.0.1:8010') as client:
        snap = client.get('/api/games/nte/snapshot/events').json()
        assert len(snap['payload']) == 2 and not snap['stale']
        assert {e['name']: e['source_stale'] for e in snap['payload']} == {'新挑战': False, '环期赠礼': True}
        assert effective(client)['error_kind'] == 'partial_data'


@pytest.mark.parametrize('game', ['wuthering_waves', 'endfield', 'league_of_legends'])
def test_other_games_keep_their_selected_source_and_failure(tmp_path, game):
    from game_assistant.api import create_app
    from game_assistant.config import Settings
    from game_assistant.models import Capability
    from game_assistant.snapshots import SnapshotStore
    from tests.test_api import FakeRegistry
    from tests.test_registry import DummyAdapter

    class Adapter(DummyAdapter):
        game_id = game
        capabilities = [Capability.NEWS, Capability.EVENTS]

    settings = Settings(db_path=str(tmp_path / 'other.db'), bilibili_sources={game: UID})
    store = SnapshotStore(settings.db_path)
    store.save(game, 'events', json.dumps([{'name': '原生活动'}]))
    store.record_poll(game, 'events', FetchResult(ok=False, error='原生真实错误', error_kind='invalid_data'))
    app = create_app(registry=FakeRegistry(Adapter()), store=store, settings=settings, start_scheduler=False)
    # Endfield's own official feed remains authoritative even when Bilibili fails.
    if game == 'endfield':
        app.state.bilibili.store.set_state(game, UID, status='error', message='B站备用源错误', failures=1)
    with TestClient(app, base_url='http://127.0.0.1:8010') as client:
        snap = client.get(f'/api/games/{game}/snapshot/events').json()
        status = next(s for s in client.get('/api/status').json()['collection']
                      if s['game_id'] == game and s['capability'] == 'events')
        assert without_observation(status) == without_observation(snap['poll_status'])
        assert status['error'] == '原生真实错误' and status['error_kind'] == 'invalid_data'
        assert snap['payload'][0]['name'] == '原生活动' and snap['stale']
        if game == 'endfield':
            assert snap['primary_source'] == 'official'
        if game == 'league_of_legends':
            assert 'primary_source' not in snap
