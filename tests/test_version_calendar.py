"""Version calendars retain source scope rather than silently applying a month."""
from datetime import datetime, timezone
from types import SimpleNamespace

from game_assistant.qq.event_views import event_document
from game_assistant.sources.public_content import calendar_from_posts, parse_post_events
from tests.test_public_content import notice

NOW = datetime(2026, 12, 29, 4, tzinfo=timezone.utc)


def test_version_calendar_keeps_ended_future_unknown_and_separate_games():
    def snapshot(version, events):
        return SimpleNamespace(payload=events, fetched_at=NOW.isoformat(), state='ok', complete=None,
            stale=False, version=version, version_metadata={'id': version, 'status': 'current',
            'coverage': 'unverified', 'start_at': None, 'end_at': None, 'sources': [], 'diagnostics': []})
    a = dict(name='已结束', version='3.9', start_at='2026-11-20T10:00:00+08:00', end_at='2026-12-01T10:00:00+08:00')
    b = dict(name='明年活动', version='3.9', start_at='2027-01-01T10:00:00+08:00', end_at='2027-01-10T10:00:00+08:00')
    c = dict(name='待定', version='3.9', start_at=None, end_at=None)
    old = dict(name='旧版本', version='3.8', start_at=None, end_at=None)
    card = event_document('calendar', {'wuthering_waves': snapshot('3.9', [a, b, c, old]),
        'nte': snapshot('1.6', [dict(name='另一版本', version='1.6', start_at=None, end_at=None)])}, now=NOW)
    text = str(card)
    assert all(name in text for name in ['已结束', '明年活动', '待定', '另一版本'])
    assert '旧版本' not in text
    assert '3.9' in text and '1.6' in text and '覆盖待核验' in text
    assert 'timeline' not in card  # No artificial shared version range.


def test_unknown_version_summary_is_not_natural_month_or_current_claim():
    snap = SimpleNamespace(payload=[dict(name='以前已知活动', start_at='2026-10-01T10:00:00+08:00',
        end_at='2026-10-02T10:00:00+08:00')], fetched_at=NOW.isoformat(), state='error', complete=None)
    text = str(event_document('calendar', {'nte': snap}, now=NOW))
    assert '以前已知活动' in text and '版本未确认' in text and '陈旧' in text


def test_notice_metadata_uses_next_maintenance_not_last_activity_or_fixed_duration():
    base = notice('3.9版本内容说明\n更新维护时间：2026年12月20日06:00\n[短活动]活动\n活动时间：2026年12月20日10:00 ~ 2026年12月21日10:00',
        published='2026-12-19T04:00:00+00:00')
    future = notice('4.0版本内容说明\n更新维护时间：2027年1月30日06:00\n[未来]活动\n活动时间：4.0版本更新后 ~ 2027年2月10日10:00',
        id='2', published='2026-12-28T04:00:00+00:00')
    result = calendar_from_posts([base, future], 'wuthering_waves', NOW)
    meta = result['version_metadata']
    assert meta['id'] == '3.9' and meta['start_precision'] == 'day'
    assert meta['end_at'] == '2027-01-30T06:00:00+08:00' and meta['end_precision'] == 'minute'
    assert meta['end_source']['post_id'] == '2' and meta['coverage'] == 'unverified'
    without_next = calendar_from_posts([base], 'wuthering_waves', NOW)['version_metadata']
    assert without_next['end_at'] is None and without_next['end_precision'] == 'unknown'


def test_explicit_unknown_and_date_only_activity_boundaries_are_retained():
    post = notice('3.9版本内容说明\n[日期活动]活动\n活动时间：2026年12月30日 ~ 2027年1月2日\n[时间待定]活动\n活动时间：待定\n[永久]活动\n活动时间：永久')
    events = parse_post_events(post, 'wuthering_waves', '3.9')
    assert [e['name'] for e in events] == ['日期活动', '时间待定']
    assert events[0]['end_at'] is None and events[0]['end_date'] == '2027-01-02'
    assert events[0]['end_precision'] == 'day'
    assert events[1]['start_at'] is None and events[1]['end_at'] is None


def test_cached_current_metadata_expires_and_day_boundary_does_not_invent_midnight():
    from game_assistant.version_calendar import snapshot_version
    meta = dict(id='3.9', status='current', start_date='2026-12-20', start_precision='day',
                end_at='2026-12-29T10:00:00+08:00', end_precision='minute')
    result = snapshot_version('wuthering_waves', [], metadata=meta, now=NOW)
    assert result['status'] == 'historical'
    day_only = {**meta, 'end_at':None, 'end_date':'2026-12-29', 'end_precision':'day'}
    assert snapshot_version('wuthering_waves', [], metadata=day_only, now=NOW)['status'] == 'unverified'
    assert snapshot_version('wuthering_waves', [], metadata=day_only,
        now=datetime(2026, 12, 30, 4, tzinfo=timezone.utc))['status'] == 'historical'
    assert snapshot_version('wuthering_waves', [], metadata={**meta, 'end_at':None}, now=NOW)['status'] == 'unverified'


def test_cross_version_intersection_and_unknown_version_boundaries():
    from game_assistant.version_calendar import select_version_events
    meta = dict(id='3.9',start_date='2026-12-20',end_at='2027-01-30T06:00:00+08:00')
    old = dict(name='延续活动',version='3.8',start_at='2026-12-01T10:00:00+08:00',end_at='2026-12-25T10:00:00+08:00')
    assert select_version_events([old],meta)[0]['cross_version'] is True
    assert select_version_events([old],{**meta,'end_at':None}) == []
    assert select_version_events([dict(name='归属未知')],meta)[0]['name'] == '归属未知'


def test_no_version_anchor_returns_source_backed_available_summary():
    post = notice('[独立活动]活动\n活动时间：2026年12月1日10:00 ~ 2027年1月5日10:00',
                  published='2026-11-30T04:00:00+00:00')
    result = calendar_from_posts([post], 'wuthering_waves', NOW)
    assert result['version'] is None and [e['name'] for e in result['events']] == ['独立活动']
    assert result['version_metadata']['status'] == 'unknown'


def test_year_less_maintenance_date_takes_the_year_nearest_the_notice():
    from game_assistant.event_calendar import BEIJING_TZ
    from game_assistant.version_calendar import maintenance
    # Announced in late December for January: the version opens next year, not last January.
    december = {'body': '更新维护时间：1月7日06:00-11:00', 'published_at': '2026-12-28T04:00:00+00:00'}
    assert maintenance(december) == (datetime(2027, 1, 7, 6, tzinfo=BEIJING_TZ), 'minute')
    january = {'body': '更新维护时间：12月30日', 'published_at': '2027-01-02T04:00:00+00:00'}
    assert maintenance(january) == (datetime(2026, 12, 30, tzinfo=BEIJING_TZ), 'day')


def test_late_independent_events_use_version_boundaries_and_keep_unknown_ownership():
    now = datetime(2026, 10, 20, 4, tzinfo=timezone.utc)
    base = notice('3.7版本内容说明\n更新维护时间：2026年10月1日06:00\n[首周活动]活动\n活动时间：2026年10月1日10:00 ~ 2026年10月10日10:00',
                  published='2026-09-30T04:00:00+00:00')
    late = notice('[后半程活动]活动\n活动时间：2026年10月12日10:00 ~ 2026年10月25日10:00',
                  id='2', published='2026-10-11T04:00:00+00:00')
    future = notice('3.8版本内容说明\n更新维护时间：2026年11月1日06:00\n[未来活动]活动\n活动时间：2026年11月1日10:00 ~ 2026年11月10日10:00',
                    id='3', published='2026-10-19T04:00:00+00:00')
    outside = notice('[下一窗口活动]活动\n活动时间：2026年11月2日10:00 ~ 2026年11月10日10:00',
                     id='4', published='2026-10-19T04:00:00+00:00')
    result = calendar_from_posts([base, late, future, outside], 'wuthering_waves', now)
    assert {e['name'] for e in result['events']} == {'首周活动', '后半程活动'}
    assert result['version_metadata']['end_at'] == '2026-11-01T06:00:00+08:00'
    assert next(e for e in result['events'] if e['name'] == '后半程活动')['version'] is None
    unknown_end = calendar_from_posts([base, outside], 'wuthering_waves', now)
    assert next(e for e in unknown_end['events'] if e['name'] == '下一窗口活动')['version'] is None


def test_day_precision_extension_merges_but_distinct_phases_and_identities_remain():
    base = notice('3.9版本内容说明\n[活动甲]活动\n活动时间：2026年12月1日 ~ 2026年12月10日')
    revision = notice('3.9版本活动延期\n[活动甲]活动\n活动时间：2026年12月1日 ~ 2026年12月12日',
                      id='2', published='2026-12-08T04:00:00+00:00')
    result = calendar_from_posts([base, revision], 'wuthering_waves', NOW)
    assert len(result['events']) == 1 and result['events'][0]['end_date'] == '2026-12-12'
    from game_assistant.sources.public_content import _same_event
    a = result['events'][0]
    assert not _same_event(a, {**a, 'start_date':'2026-12-13', 'end_date':'2026-12-15'})
    assert not _same_event({**a, 'server_id':'one'}, {**a, 'server_id':'two'})
    assert not _same_event(a, {**a, 'version':'4.0'})
