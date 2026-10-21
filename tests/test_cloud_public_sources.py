"""Source selection regressions with synthetic data and real snapshot storage."""
import json
from datetime import datetime, timedelta, timezone


from game_assistant.accounts.query import CloudPublicQuery
from game_assistant.models import FetchResult
from game_assistant.snapshots import SnapshotStore
from tests.test_api import FakeRegistry
from tests.test_registry import DummyAdapter


class Bili:
    def __init__(self, game, rows=(), **state):
        self.sources = {game: '123'}
        self.store = self
        self.rows = list(rows)
        self.data = state

    def state(self, game, uid):
        return self.data

    def news(self, game):
        return self.rows

    def calendar(self, game):
        return {'events': self.rows, 'version': '3.6'}


def query(game='wuthering_waves', rows=(), **state):
    class Adapter(DummyAdapter):
        game_id = game
    store = SnapshotStore(':memory:')
    return CloudPublicQuery(FakeRegistry(Adapter()), store, bilibili=Bili(game, rows, **state)), store


def save(store, game, cap, rows, time):
    store.save(game, cap, json.dumps(rows))
    store._conn.execute('UPDATE snapshots SET fetched_at=? WHERE game_id=? AND capability=?', (time, game, cap))
    store._conn.commit()


def qq_events_text(public):
    from game_assistant.qq.models import QqIdentity
    from game_assistant.qq.query_routes import QqQueryService
    return QqQueryService(None, None, public).query(QqIdentity('app', 'group', 'g', 's'), 'events', 'wuthering_waves')['text']


def test_empty_successful_bili_does_not_mask_failed_retained_calendar():
    now = datetime.now(timezone.utc).isoformat()
    q, store = query(status='ok', last_success=now, history_complete=True)
    old = '2026-01-01T00:00:00+00:00'
    save(store, 'wuthering_waves', 'events', [{'name': '旧活动'}], old)
    store.record_poll('wuthering_waves', 'events', FetchResult(ok=False, error='原生失败', error_kind='source_error'))
    result = q.read('wuthering_waves', 'events')
    assert result.state == 'error' and result.fetched_at == old
    assert result.complete is None
    assert result.primary_source == 'community' and result.stale
    assert result.poll_status['source_statuses']['community']['error'] == '原生失败'


def test_bili_success_does_not_refresh_old_official_endfield_calendar():
    now = datetime.now(timezone.utc).isoformat()
    q, store = query('endfield', status='ok', last_success=now, history_complete=True)
    old = '2026-01-01T00:00:00+00:00'
    save(store, 'endfield', 'events', [{'name': '官网活动', 'version': '1.0'}], old)
    store.record_poll('endfield', 'events', FetchResult(ok=False, error_kind='source_error'))
    result = q.read('endfield', 'events')
    assert result.fetched_at == old and result.state == 'error'
    assert result.primary_source == 'official' and result.version == '1.0'
    assert result.stale and result.payload[0]['source_stale']


def test_expired_successful_native_snapshot_is_stale_without_changing_poll_state():
    q, store = query()
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    save(store, 'wuthering_waves', 'events', [{'name': '旧活动'}], old)
    store.record_poll('wuthering_waves', 'events', FetchResult(ok=True), now=datetime.fromisoformat(old))
    result = q.read('wuthering_waves', 'events')
    assert result.state == 'ok' and result.stale
    assert result.payload[0]['source_stale']


def test_bili_history_completeness_is_not_calendar_coverage():
    now = datetime.now(timezone.utc).isoformat()
    q, _ = query(rows=[{'name': 'B站活动', 'source': 'bilibili'}], status='ok', last_success=now, history_complete=True)
    result = q.read('wuthering_waves', 'events')
    assert result.complete is None and result.primary_source == 'bilibili'
    assert result.version == '3.6' and result.fetched_at == now
    assert result.poll_status['source_statuses']['bilibili']['state'] == 'ok'


def test_failed_bili_preserves_native_rows_and_reports_degradation():
    q, store = query(status='error', message='B站不可达', failures=1)
    now = datetime.now(timezone.utc).isoformat()
    save(store, 'wuthering_waves', 'events', [{'name': '社区活动'}], now)
    store.record_poll('wuthering_waves', 'events', FetchResult(ok=True))
    result = q.read('wuthering_waves', 'events')
    assert result.state == 'error' and not result.stale
    assert result.payload[0]['name'] == '社区活动'
    assert result.poll_status['source_statuses']['bilibili']['error'] == 'B站不可达'


def test_public_qq_partial_failure_labels_fresh_native_content_as_available():
    from types import SimpleNamespace
    from game_assistant.accounts.models import QueryResult
    q, store = query(status='error', message='B站不可达', failures=1)
    now = datetime.now(timezone.utc).isoformat()
    save(store, 'wuthering_waves', 'events', [{'name': '最新社区活动'}], now)
    store.record_poll('wuthering_waves', 'events', FetchResult(ok=True))
    text = qq_events_text(q)
    assert '部分来源不可用，显示可用来源数据' in text and '旧快照' not in text
    # A failed result without its own stale flag and genuinely stale public content keep the old-cache warning.
    private = SimpleNamespace(read=lambda game, cap: QueryResult([{'name': '旧记录'}], now, 'error', None))
    assert '显示旧快照' in qq_events_text(private)
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    save(store, 'wuthering_waves', 'events', [{'name': '旧社区活动'}], old)
    assert '显示旧快照' in qq_events_text(q)


def test_qq_image_projection_keeps_the_public_results_own_freshness():
    from types import SimpleNamespace
    from game_assistant.accounts.models import QueryResult
    from game_assistant.qq.models import QqIdentity
    from game_assistant.qq.query_routes import QqQueryService
    now = datetime.now(timezone.utc)
    def projected(public, command):
        context = {}
        QqQueryService(None, None, public, clock=lambda: now).query(
            QqIdentity('app', 'group', 'g', 's'), command, 'wuthering_waves', image_context=context)
        data = context['render_snapshot']['display_data']
        return data['snapshots']['wuthering_waves']['events'] if command == 'calendar' else data['panels'][0]['snapshot']
    q, store = query(status='error', message='B站不可达', failures=1)
    save(store, 'wuthering_waves', 'events', [{'name': '最新社区活动'}], now.isoformat())
    store.record_poll('wuthering_waves', 'events', FetchResult(ok=True))
    source = q.read('wuthering_waves', 'events')
    assert source.state == 'error' and source.stale is False
    for command in ('calendar', 'events', 'recent_events'):
        row = projected(q, command)
        assert row['state'] == 'error' and row['stale'] is False
    version = projected(q, 'calendar')['version_metadata']
    assert version['coverage'] == 'partial' and version['diagnostics'] == source.version_metadata['diagnostics']
    # A successful poll whose cache has expired is still stale, and a result
    # without its own stale flag (private, or a failed public read) is judged by state.
    q, store = query()
    old = (now - timedelta(days=2)).isoformat()
    save(store, 'wuthering_waves', 'events', [{'name': '旧活动'}], old)
    store.record_poll('wuthering_waves', 'events', FetchResult(ok=True), now=datetime.fromisoformat(old))
    failed = SimpleNamespace(read=lambda game, cap: QueryResult([{'name': '旧活动'}], old, 'error', None))
    for command in ('calendar', 'events', 'recent_events'):
        assert projected(q, command)['state'] == 'ok' and projected(q, command)['stale'] is True
        assert projected(failed, command)['stale'] is True


def test_partial_and_expired_bili_keep_rows_warn_and_use_contributing_time():
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    q, _ = query(rows=[{'name': 'B站旧活动', 'source': 'bilibili', 'source_stale': True}],
                 status='ok', last_success=old)
    result = q.read('wuthering_waves', 'events')
    assert result.state == 'error' and result.stale and len(result.payload) == 1
    assert result.poll_status['error_kind'] == 'partial_data'
    assert result.fetched_at == old


def test_announcement_failure_and_time_are_separate_from_news():
    q, store = query()
    old = '2026-01-01T00:00:00+00:00'
    save(store, 'wuthering_waves', 'announcement', [{'title': '公告'}], old)
    store.record_poll('wuthering_waves', 'announcement', FetchResult(ok=False, error='正文失败', error_kind='source_error'))
    result = q.read('wuthering_waves', 'news')
    assert result.state == 'error' and result.fetched_at == old and result.stale
    assert result.poll_status['source_statuses']['announcement']['error'] == '正文失败'


def test_deduplicated_native_calendar_does_not_refresh_bili_content():
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    event = {'name': '同一活动', 'source': 'bilibili', 'end_at': '2026-11-01T05:59:00+08:00'}
    q, store = query(rows=[event], status='ok', last_success=old)
    save(store, 'wuthering_waves', 'events', [{**event, 'source': 'community', 'version': '3.6'}], datetime.now(timezone.utc).isoformat())
    result = q.read('wuthering_waves', 'events')
    assert len(result.payload) == 1 and result.fetched_at == old and result.stale


def test_native_article_body_repair_counts_as_actual_contribution():
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    q, store = query(rows=[{'title': '同一公告', 'source': 'bilibili', 'body': ''}], status='ok', last_success=old)
    save(store, 'wuthering_waves', 'announcement', [{'title': '同一公告', 'body': '社区完整正文', 'content_status': 'full'}], now)
    result = q.read('wuthering_waves', 'news')
    assert len(result.payload) == 1 and result.fetched_at == now
    assert result.payload[0]['body'] == '社区完整正文'


def test_same_version_community_event_survives_bili_merge_without_version_in_title():
    now = datetime.now(timezone.utc).isoformat()
    q, store = query(rows=[{'name': 'B站活动', 'source': 'bilibili'}], status='ok', last_success=now)
    save(store, 'wuthering_waves', 'events', [{'name': '独立卡池', 'version': '3.6', 'source_title': '独立唤取公告'}], now)
    result = q.read('wuthering_waves', 'events')
    assert {r['name'] for r in result.payload} == {'B站活动', '独立卡池'}


def test_public_qq_reply_warns_when_successful_cache_has_expired():
    q, store = query()
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    save(store, 'wuthering_waves', 'events', [{'name': '旧活动'}], old)
    store.record_poll('wuthering_waves', 'events', FetchResult(ok=True), now=datetime.fromisoformat(old))
    text = qq_events_text(q)
    assert '旧活动' in text and '过期' in text and '完整性：未知' in text


def test_cloud_http_preserves_public_source_metadata(tmp_path):
    from fastapi.testclient import TestClient
    from game_assistant.cloud_app import create_cloud_app
    from tests.test_account_queries import cloud_settings
    from tests.test_identity import write
    app = create_cloud_app(cloud_settings(tmp_path), start_scheduler=False)
    admin = app.state.identity.bootstrap_admin('admin', 'Admin-password-123')
    invite = app.state.identity.create_invite(admin)
    with TestClient(app, base_url='https://cloud.example') as client:
        assert client.get('/api/public/games/wuthering_waves/events').status_code == 401
        assert write(client, '/api/identity/register', {'username': 'alice',
            'password': 'Password-alice-123', 'invite': invite}).status_code == 200
        def seed():
            old = '2026-01-01T00:00:00+00:00'
            save(app.state.store, 'wuthering_waves', 'events', [{'name': '旧活动', 'version': '3.6'}], old)
            app.state.store.record_poll('wuthering_waves', 'events', FetchResult(ok=True), now=datetime.fromisoformat(old))
        client.portal.call(seed)
        response = client.get('/api/public/games/wuthering_waves/events')
        assert response.status_code == 200
        data = response.json()
        assert data['state'] == 'ok' and data['stale'] is True
        assert data['primary_source'] == 'community' and data['version'] == '3.6'
        assert data['poll_status']['source_statuses']['community']['state'] == 'ok'
        assert data['complete'] is None


def test_calendar_media_index_is_cache_only_and_omits_article_bodies():
    q,store=query()
    now=datetime.now(timezone.utc).isoformat()
    save(store,'wuthering_waves','events',[{'name':'活动','source_post_id':'123','source_url':'https://official.example/123'}],now)
    save(store,'wuthering_waves','announcement',[{'id':'123','title':'公告','body':'完整正文不能进入日历索引','summary':'摘要也不进入',
         'url':'https://official.example/123','images':['https://official.example/123.jpg'],'private_token':'must-not-return'}],now)
    result=q.read('wuthering_waves','events')
    assert result.artwork_sources==[{'id':'123','source':'community','url':'https://official.example/123','images':['https://official.example/123.jpg']}]
    assert result.artwork_status['state']=='ok'
    assert result.payload[0]['name']=='活动'


def test_calendar_media_cache_failure_does_not_fail_dates():
    q,store=query()
    now=datetime.now(timezone.utc).isoformat()
    save(store,'wuthering_waves','events',[{'name':'保留日期'}],now)
    original=store.get
    def broken(game,cap):
        if cap in ('news','announcement'):raise RuntimeError('private raw exception')
        return original(game,cap)
    store.get=broken
    result=q.read('wuthering_waves','events')
    assert result.payload[0]['name']=='保留日期'
    assert result.artwork_status['state']=='error'
    assert 'private raw exception' not in str(result.artwork_status)

def test_matched_community_pictures_survive_cached_public_events_and_news():
    now = datetime.now(timezone.utc).isoformat()
    primary = {'name': '材料双倍', 'version': '3.6', 'source': 'bilibili',
               'source_url': 'https://www.bilibili.com/read/cv42',
               'start_at': '2026-10-01T04:00:00+08:00', 'end_at': '2026-10-30T04:00:00+08:00'}
    q, store = query(rows=[primary], status='ok', last_success=now)
    community = {**primary, 'source': 'community', 'source_post_id': '42',
                 'source_url': 'https://www.kurobbs.com/forum/post/42',
                 'image_urls': ['https://img.kurobbs.com/42.jpg']}
    save(store, 'wuthering_waves', 'events', [community], now)
    result = q.read('wuthering_waves', 'events')
    assert len(result.payload) == 1
    assert result.payload[0]['source_url'] == primary['source_url']
    assert result.payload[0]['start_at'] == primary['start_at']
    assert result.payload[0]['supplement_sources'][0]['image_urls'] == community['image_urls']
    save(store, 'wuthering_waves', 'announcement', [{
        'id': '42', 'title': '材料双倍', 'url': community['source_url'],
        'images': community['image_urls'], 'content_status': 'full'}], now)
    news = q.read('wuthering_waves', 'news')
    assert any(row.get('images') == community['image_urls'] for row in news.payload)


def test_six_hourly_public_collection_is_not_reported_stale_between_runs():
    from game_assistant.config import Settings
    from game_assistant.sources.public_snapshot import read_public_snapshot
    def read(hours):
        at = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        q, store = query(rows=[{'name': 'B站活动', 'source': 'bilibili'}], status='ok', last_success=at)
        save(store, 'wuthering_waves', 'events', [{'name': '社区活动'}], at)
        store.record_poll('wuthering_waves', 'events', FetchResult(ok=True), now=datetime.fromisoformat(at))
        return q, store
    q, store = read(5)
    assert q.settings.cloud_public_poll_seconds == 21600
    statuses = q.read('wuthering_waves', 'events').poll_status['source_statuses']
    assert not statuses['bilibili']['stale'] and not statuses['community']['stale']
    # The local app keeps its own hourly announcement interval.
    local = read_public_snapshot(store, 'wuthering_waves', 'events', Settings(), q.bilibili)
    assert local['poll_status']['source_statuses']['community']['stale']
    q, _ = read(13)
    statuses = q.read('wuthering_waves', 'events').poll_status['source_statuses']
    assert statuses['bilibili']['stale'] and statuses['community']['stale']


class CollectingBili(Bili):
    def __init__(self, game, **state):
        super().__init__(game, **state)
        self.runs = []

    async def run(self, game, backfill=False, *, history_days=None):
        self.runs.append((game, backfill, history_days))
        self.data = {**self.data, 'status': 'ok'}


def forced_query(game, bili):
    from game_assistant.models import Capability
    class Adapter(DummyAdapter):
        game_id = game
        capabilities = [Capability.NEWS, Capability.EVENTS]
        def prepare_refresh(self):
            self.calls.append('prepare')
        async def fetch(self, cap):
            self.calls.append(cap.value)
            return FetchResult(ok=cap == Capability.NEWS, payload=[], error_kind=None if cap == Capability.NEWS else 'source_error')
    adapter = Adapter()
    return CloudPublicQuery(FakeRegistry(adapter), SnapshotStore(':memory:'), bilibili=bili), adapter


async def test_forced_public_poll_refreshes_official_cache_then_backfills_bilibili():
    bili = CollectingBili('endfield')
    q, adapter = forced_query('endfield', bili)
    outcome = await q.poll('endfield', force=True, backfill=True)
    assert adapter.calls == ['prepare', 'news', 'events']
    assert bili.runs == [('endfield', True, 60)]
    assert outcome == {'bilibili': 'ok', 'failed': ['events']}
    # The periodic pass neither forces the official cache nor backfills.
    adapter.calls.clear()
    assert (await q.poll('endfield'))['bilibili'] == 'ok'
    assert adapter.calls == ['news', 'events'] and bili.runs[-1] == ('endfield', False, None)


async def test_forced_public_poll_respects_bilibili_backoff_and_still_reads_other_sources():
    import time
    bili = CollectingBili('wuthering_waves', status='error', next_retry=time.time() + 600)
    q, adapter = forced_query('wuthering_waves', bili)
    outcome = await q.poll('wuthering_waves', force=True, backfill=True)
    assert bili.runs == [] and outcome['bilibili'] == 'backoff'
    assert adapter.calls == ['prepare', 'news', 'events']
    bili.data = {'status': 'ok', 'next_retry': time.time() + 30}
    assert (await q.poll('wuthering_waves', force=True, backfill=True))['bilibili'] == 'cooldown'
