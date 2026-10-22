"""Daily guide job: synthetic roster and upstream, injected pause and clock, no real network."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from game_assistant import guide_jobs
from game_assistant.guide_jobs import CN, GuideJob, guide_roster, static_sources
from game_assistant.nte_guides import GuideService
from game_assistant.nte_guides_catalog import SOURCES
from game_assistant.wuwa_guide_extract import POST_URL
from game_assistant.wuwa_guide_updates import SEARCH_URL, GuideUpdates, Search
from game_assistant.wuwa_tower_guides import TowerGuides

NAMES = ['甲乙', '丙丁', '戊己', '庚辛', '壬癸', '子丑', '寅卯', '辰巳', '午未', '申酉']


def roster(monkeypatch, names=NAMES, static=('甲乙',)):
    rows = [dict(character_id=str(9000 + i), name=name, attribute='', static=name in static) for i, name in enumerate(names)]
    monkeypatch.setattr(guide_jobs, 'guide_roster', lambda: [dict(r) for r in rows])
    # The static entry's reviewed source is exactly what the search finds: not new, not extracted.
    monkeypatch.setattr(guide_jobs, 'static_sources', lambda cid: frozenset({'100'}) if cid == '9000' else frozenset())
    return rows


def post(index, name, author='1'):
    return {'postId': str(100 + index), 'postTitle': f'{name}培养攻略', 'gameId': 3, 'postType': 1,
            'userName': '作者', 'userId': author, 'createTimestamp': '1790760000000'}


class Upstream:
    """Search answers by keyword; failures can be injected for one role."""
    def __init__(self, names=NAMES, fail=None, detail_status=200):
        self.names, self.fail, self.detail_status = list(names), fail or {}, detail_status
        self.searches, self.details = [], []

    def search(self, request):
        keyword = parse_qs(request.content.decode())['keyword'][0].removesuffix('培养攻略')
        self.searches.append(keyword)
        if keyword in self.fail or keyword not in self.names:  # the tower keyword always fails here
            return httpx.Response(self.fail.get(keyword, 503), text='DO_NOT_EXPOSE')
        index = self.names.index(keyword)
        return httpx.Response(200, json={'code': 200, 'data': {'postList': [post(index, keyword)], 'hasNext': False}})

    def detail(self, request):
        post_id = parse_qs(request.content.decode())['postId'][0]
        self.details.append(post_id)
        if self.detail_status != 200:
            return httpx.Response(self.detail_status, text='DO_NOT_EXPOSE')
        name = self.names[int(post_id) - 100]
        return httpx.Response(200, json={'code': 200, 'data': {'postDetail': {
            'id': post_id, 'postTitle': f'{name}培养攻略', 'gameId': 3, 'postType': 1, 'postUserId': '1',
            'postContent': [{'contentType': 1, 'content': '武器推荐：合成武器。'}]}}})


def fresh_caches(tower, nte):
    now = datetime.now(timezone.utc)
    tower.save({'guides': [{'id': '1', 'periodStart': (now - timedelta(days=1)).isoformat(),
                            'periodEnd': (now + timedelta(days=27)).isoformat()}],
                'checked_at': now.isoformat(), 'attempted_at': now.isoformat(), 'error': None})
    for post_id, source in SOURCES.items():
        nte.save(post_id, {'id': post_id, 'fingerprint': source['fingerprint'], 'title': source['title'],
                           'images': [], 'paragraphs': ['合成内容'], 'fetched_at': now.isoformat()})


@pytest.fixture
def job(tmp_path):
    path = tmp_path / 'public.wuwa-guides.sqlite3'
    pauses = []
    async def sleep(seconds):
        pauses.append(seconds)
    clock = [datetime(2026, 10, 22, 5, 31, tzinfo=CN)]
    updates, tower = GuideUpdates(path), TowerGuides(path)
    nte = GuideService(tmp_path / 'public.nte-guides.sqlite3')
    fresh_caches(tower, nte)
    result = GuideJob(updates, tower, nte, sleep=sleep, now=lambda: clock[0])
    result.pauses, result.clock = pauses, clock
    return result


def test_roster_is_static_entries_then_default_weight_roles():
    rows = guide_roster()
    static = json.loads((guide_jobs.ROOT / 'qq/role_guides.json').read_text(encoding='utf-8'))['guides']['wuthering_waves']
    assert [(r['character_id'], r['name'], r['attribute']) for r in rows[:len(static)]] == [
        (g['id'], g['name'], g['attribute']) for g in static]
    assert all(r['static'] for r in rows[:len(static)])
    extra = rows[len(static):]
    assert extra and all(not r['static'] and r['attribute'] == '' for r in extra)
    assert {'character_id': '1311', 'name': '心', 'attribute': '', 'static': False} in extra
    assert len({r['character_id'] for r in rows}) == len(rows)
    for row in rows:  # every entry is a valid search key
        Search(character_id=row['character_id'], name=row['name'], attribute=row['attribute'])
    assert '1482734021209260032' in static_sources('1102') and static_sources('1311') == frozenset()
    rows[0]['name'] = 'changed'
    assert guide_roster()[0]['name'] != 'changed'


@respx.mock
async def test_run_pauses_extracts_only_changed_posts_within_the_budget(job, monkeypatch, caplog):
    roster(monkeypatch)
    upstream = Upstream()
    respx.post(SEARCH_URL).mock(side_effect=upstream.search)
    respx.post(POST_URL).mock(side_effect=upstream.detail)
    caplog.set_level(logging.INFO, 'game_assistant.guide_jobs')
    assert await job.run() == 'ok'
    assert upstream.searches == NAMES
    assert job.pauses == [3] * (len(NAMES) - 1)
    # 甲乙's post is its static source; 8 of the other 9 new posts are read, the last one waits.
    assert upstream.details == [str(100 + i) for i in range(1, 9)]
    status = job.status()
    assert [p['character_id'] for p in status['wuthering_waves']['pending']] == ['9009']
    assert status['wuthering_waves']['roles_checked'] == 10 and not status['wuthering_waves']['failed']
    assert status['job']['last_run']['outcome'] == 'ok' and status['job']['last_run']['stop_code'] is None
    finished = [r.getMessage() for r in caplog.records if r.getMessage().startswith('guide_job_finished')]
    assert finished == ['guide_job_finished outcome=ok checked=10 extracted=8 failed=0']
    # Next day: unchanged posts are not read again; only the waiting role is extracted.
    import time
    later = time.time() + 31
    monkeypatch.setattr('game_assistant.wuwa_guide_updates.time.time', lambda: later)
    job.clock[0] += timedelta(days=1)
    assert await job.run() == 'ok'
    assert upstream.details[8:] == ['109']
    assert job.status()['wuthering_waves']['pending'] == []


@respx.mock
@pytest.mark.parametrize('status', [429, 403])
async def test_rate_limit_or_refusal_stops_the_run_and_skips_the_tower(job, monkeypatch, caplog, status):
    roster(monkeypatch)
    upstream = Upstream(fail={'戊己': status})
    respx.post(SEARCH_URL).mock(side_effect=upstream.search)
    respx.post(POST_URL).mock(side_effect=upstream.detail)
    nte = respx.get('https://bbs-api.tajiduo.com/bbs/wapi/getPostFull')
    monkeypatch.setattr(job.tower, 'due', lambda value=None: True)
    caplog.set_level(logging.INFO, 'game_assistant.guide_jobs')
    assert await job.run() == 'stopped'
    assert upstream.searches == NAMES[:3]
    assert respx.calls.call_count == len(upstream.searches) + len(upstream.details)  # no tower search
    assert nte.call_count == 0  # fresh NTE caches are read without a request
    last = job.status()['job']['last_run']
    assert last['outcome'] == 'stopped' and last['stop_code'] == f'http:{status}'
    messages = [r.getMessage() for r in caplog.records]
    assert messages.count(f'guide_job_stopped code=http:{status}') == 1
    assert any(m.startswith('guide_job_finished outcome=stopped checked=2') for m in messages)
    assert 'DO_NOT_EXPOSE' not in caplog.text and '戊己' not in caplog.text
    failed = job.status()['wuthering_waves']['failed']
    assert failed == [{'character_id': '9002', 'name': '戊己', 'error_code': f'http:{status}'}]


@respx.mock
async def test_extraction_refusal_also_stops_and_is_listed(job, monkeypatch):
    roster(monkeypatch)
    upstream = Upstream(detail_status=429)
    respx.post(SEARCH_URL).mock(side_effect=upstream.search)
    respx.post(POST_URL).mock(side_effect=upstream.detail)
    assert await job.run() == 'stopped'
    assert upstream.searches == NAMES[:2] and upstream.details == ['101']
    status = job.status()
    assert status['job']['last_run']['stop_code'] == 'http:429'
    assert status['wuthering_waves']['extraction_failed'] == [{'character_id': '9001', 'name': '丙丁'}]


@respx.mock
async def test_search_failures_are_partial_or_failed_and_due_tower_is_checked(job, monkeypatch):
    roster(monkeypatch, names=NAMES[:2], static=())
    upstream = Upstream(names=NAMES[:2], fail={'丙丁': 503})
    respx.post(SEARCH_URL).mock(side_effect=upstream.search)
    respx.post(POST_URL).mock(side_effect=upstream.detail)
    job.tower.save({'guides': [], 'checked_at': None, 'attempted_at': None, 'error': None})
    assert await job.run() == 'partial'
    assert upstream.searches == NAMES[:2] + ['逆境深塔推荐阵容']
    assert job.status()['tower'] == {'checked_at': None, 'current_period_covered': False, 'error_code': 'http:503'}
    upstream.fail = {'甲乙': 500, '丙丁': 500}
    import time
    later = time.time() + 31
    monkeypatch.setattr('game_assistant.wuwa_guide_updates.time.time', lambda: later)
    assert await job.run() == 'failed'


def test_slot_is_beijing_time_and_a_restart_never_reruns_it(job):
    job.clock[0] = datetime(2026, 10, 22, 5, 29, tzinfo=CN)
    assert not job.due('05:30')
    assert job.next_run_at('05:30') == '2026-10-21T21:30:00+00:00'
    job.clock[0] = datetime(2026, 10, 21, 21, 30, tzinfo=timezone.utc)  # 05:30 Beijing time
    assert job.due('05:30')
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(job.path)) as conn:
        conn.execute('INSERT INTO guide_runs (started_at) VALUES (?)', (job.clock[0].isoformat(),))
        conn.commit()
    restarted = GuideJob(job.updates, job.tower, job.nte, now=lambda: job.clock[0])
    assert not restarted.due('05:30')
    assert restarted.next_run_at('05:30') == '2026-10-22T21:30:00+00:00'
    # The unfinished row of a killed process is never reported as a success.
    assert restarted.last_run()['outcome'] == 'failed' and restarted.last_run()['finished_at'] is None
    job.clock[0] = datetime(2026, 10, 23, 5, 31, tzinfo=CN)
    assert restarted.due('05:30') and not restarted.due('05:32')


async def test_background_state_and_cancellation_are_recorded(job, monkeypatch):
    roster(monkeypatch, names=NAMES[:1])
    gate = asyncio.Event()
    async def check(query, extract='always', known=()):
        await gate.wait()
    monkeypatch.setattr(job.updates, 'check', check)
    assert job.updates.background() == {'running': False, 'last_run_at': None}
    task = asyncio.create_task(job.run())
    await asyncio.sleep(0)
    assert job.updates.background()['running'] is True
    assert job.status()['job']['last_run'] is None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert job.running is False
    last = job.status()['job']['last_run']
    assert last['outcome'] == 'stopped' and last['stop_code'] == 'shutdown' and last['finished_at']
    assert job.updates.background() == {'running': False, 'last_run_at': last['finished_at']}


def test_status_shape_with_empty_caches(tmp_path):
    path = tmp_path / 'public.wuwa-guides.sqlite3'
    job = GuideJob(GuideUpdates(path), TowerGuides(path), GuideService(tmp_path / 'nte.sqlite3'))
    status = job.status(state='queued', next_run_at='2026-10-22T21:30:00+00:00', retry_after=12)
    assert status['job'] == {'state': 'queued', 'last_run': None, 'next_run_at': '2026-10-22T21:30:00+00:00',
                             'retry_after': 12}
    wuwa = status['wuthering_waves']
    assert wuwa['roles_total'] == len(guide_roster()) and wuwa['roles_checked'] == 0
    assert wuwa['checked_at_oldest'] is None and wuwa['pending'] == wuwa['failed'] == wuwa['extraction_failed'] == []
    # Never checked is unknown, not "not covered".
    assert status['tower'] == {'checked_at': None, 'current_period_covered': None, 'error_code': None}
    assert [p['post_id'] for p in status['nte']['posts']] == list(SOURCES)
    assert all(p['fetched_at'] is None and p['stale'] and not p['error'] for p in status['nte']['posts'])


def test_pending_ignores_static_and_active_sources(tmp_path):
    path = tmp_path / 'public.wuwa-guides.sqlite3'
    updates = GuideUpdates(path)
    job = GuideJob(updates, TowerGuides(path), GuideService(tmp_path / 'nte.sqlite3'))
    def candidate(post_id, author='1', kind='article'):
        return {'id': post_id, 'title': '合成攻略', 'author': '作者', 'author_id': author, 'kind': kind,
                'published_at': '2026-10-01T00:00:00+00:00'}
    def save(row, candidates):
        updates.save(Search(character_id=row['character_id'], name=row['name'], attribute=row['attribute']),
                     {**row, 'candidates': candidates, 'checked_at': '2026-10-21T00:00:00+00:00',
                      'attempted_at': '2026-10-21T00:00:00+00:00', 'error': None, 'error_code': None, 'limited': False})
    rows = {r['character_id']: {k: r[k] for k in ('character_id', 'name', 'attribute')} for r in guide_roster()}
    save(rows['1102'], [candidate('1482734021209260032')])          # static source: not pending
    save(rows['1311'], [candidate('7', kind='video'), candidate('8'), candidate('9', author='10525366')])
    pending = job.status()['wuthering_waves']['pending']
    assert pending == [{'character_id': '1311', 'name': '心', 'post_id': '9', 'title': '合成攻略',
                        'author': '作者', 'published_at': '2026-10-01T00:00:00+00:00'}]
    assert job.status()['wuthering_waves']['checked_at_oldest'] == '2026-10-21T00:00:00+00:00'
