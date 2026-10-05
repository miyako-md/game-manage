"""Synthetic responses only: pagination failures stay failures without leaking data."""
import json
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from game_assistant.sources.bilibili import BilibiliClient, RULE_VERSION, SourceError, collect_pages
from tests.test_bilibili_source import NOW, UID, post
from tests.test_bilibili_integration import setup
from tests.test_public_source_status import seed, effective, without_observation

SECRET = 'SECRET_COOKIE_TOKEN_CURSOR_BODY_ACCOUNT'
KEYS = {'page', 'item_count', 'has_more', 'cursor_present', 'http_status', 'business_code'}


def test_save_busy_exception_keeps_its_existing_no_argument_contract():
    from game_assistant.sources.bilibili_service import BilibiliSaveBusy
    error = BilibiliSaveBusy()
    assert str(error) == '' and error.http_status is None and error.business_code is None


@pytest.mark.parametrize('case,expected_pages,error_text', [
    ('empty_false', 0, '首页返回空列表'),
    ('empty_true', 0, '首页返回空列表'),
    ('terminal', 1, None),
    ('later_empty', 1, '第2页返回空列表'),
    ('two_pages', 2, None),
    ('repeat', 2, '第2页分页游标异常'),
])
async def test_pagination_six_cases_emit_only_safe_metadata(case, expected_pages, error_text):
    first = {'items': [post('9月15日活动')], 'has_more': True, 'offset': SECRET}
    second = {'items': [post('9月15日活动', '2')], 'has_more': False}
    if case.startswith('empty'):
        first.update(items=[], has_more=case == 'empty_true')
    if case == 'terminal': first['has_more'] = False
    if case == 'later_empty': second['items'] = []
    if case == 'repeat': second.update(has_more=True, offset=SECRET)
    first.update(cookie=SECRET, headers=SECRET, body=SECRET, uid=SECRET)
    calls, saved, diagnostics = [], [], []
    async def fetch(offset):
        calls.append(offset)
        return second if offset else first
    options = dict(days=2, mode='incremental', pause=0,
                   on_page=lambda rows, page: saved.append(page), on_diagnostic=diagnostics.append)
    if error_text:
        with pytest.raises(SourceError) as caught:
            await collect_pages(fetch, UID, NOW, **options)
        assert error_text in str(caught.value)
        assert '2天增量采集' in str(caught.value) and '60天' not in str(caught.value)
    else:
        result = await collect_pages(fetch, UID, NOW, **options)
        assert result['complete'] and result['pages'] == expected_pages
    assert len(saved) == expected_pages
    assert len(calls) == len(diagnostics) == (2 if case in ('later_empty', 'two_pages', 'repeat') else 1)
    assert all(set(d) == KEYS for d in diagnostics)
    assert SECRET not in json.dumps(diagnostics)
    assert diagnostics[0]['cursor_present'] is True
    assert diagnostics[0]['item_count'] == len(first['items'])
    assert diagnostics[0]['http_status'] is None  # SDK does not expose these on success.
    assert diagnostics[0]['business_code'] is None


@pytest.mark.parametrize('payload', [None, {'items': SECRET, 'has_more': SECRET, 'offset': SECRET},
                                     {'items': [], 'has_more': {'cookie': SECRET}}])
async def test_malformed_response_diagnostic_does_not_copy_arbitrary_values(payload):
    records = []
    async def fetch(offset): return payload
    with pytest.raises(SourceError):
        await collect_pages(fetch, UID, NOW, on_diagnostic=records.append)
    assert len(records) == 1 and set(records[0]) == KEYS
    assert records[0]['has_more'] is None
    assert SECRET not in json.dumps(records)


@pytest.mark.parametrize('kind,code,expected', [
    ('network', 412, {'http_status': 412, 'business_code': None}),
    ('business', -101, {'http_status': None, 'business_code': -101}),
    ('business', SECRET, {'http_status': None, 'business_code': None}),
    ('business', True, {'http_status': None, 'business_code': None}),
])
async def test_sdk_failure_retains_only_numeric_codes_without_retry(kind, code, expected):
    from bilibili_api.exceptions import NetworkException, ResponseCodeException
    error = NetworkException(code, SECRET) if kind == 'network' else ResponseCodeException(code, SECRET, {'cookie': SECRET})
    calls, diagnostics = [], []
    async def fail(**kwargs):
        calls.append(kwargs)
        raise error
    client = BilibiliClient.__new__(BilibiliClient)
    client.user = SimpleNamespace(get_dynamics_new=fail)
    with pytest.raises(SourceError) as caught:
        await collect_pages(client.page, UID, NOW, days=7, mode='backfill', on_diagnostic=diagnostics.append)
    assert len(calls) == 1 and len(diagnostics) == 1
    assert {k: diagnostics[0][k] for k in expected} == expected
    assert '7天历史回补' in str(caught.value)
    assert SECRET not in str(caught.value) + json.dumps(diagnostics)


@pytest.mark.parametrize('backfill', [False, True])
async def test_failure_retains_calendar_history_and_logs_only_allowlisted_metadata(tmp_path, caplog, backfill):
    app, store = setup(tmp_path)
    row, now = seed(app, store)
    service = app.state.bilibili
    service.settings.bilibili_history_days = 7
    service.store.set_state('nte', UID, history_complete=True, rule_version=RULE_VERSION,
                            coverage_since='previous-coverage', next_retry=0)
    service.credentials = SimpleNamespace(load=lambda: {})
    before = service.store.rows('nte', UID)
    class Empty:
        def __init__(self, *args): pass
        async def page(self, offset):
            return {'items': [], 'has_more': False, 'offset': SECRET, 'body': SECRET}
    service.client_factory = Empty
    with caplog.at_level(logging.WARNING, logger='game_assistant.sources.bilibili_service'):
        await service.run('nte', backfill)
    state = service.store.state('nte', UID)
    assert state['status'] == 'error' and state['pages'] == 0
    assert ('7天历史回补' if backfill else '2天增量采集') in state['message']
    assert '首页返回空列表' in state['message']
    assert state['last_success'] == now.isoformat()
    assert state['history_complete'] is True and state['coverage_since'] == 'previous-coverage'
    assert service.store.rows('nte', UID) == before
    assert set(state['diagnostic']) == KEYS | {'game_id'}
    assert state['diagnostic']['game_id'] == 'nte'
    assert 'item_count' in caplog.text and 'has_more' in caplog.text
    assert SECRET not in caplog.text + json.dumps(state['diagnostic'])
    assert UID not in caplog.text
    with TestClient(app, base_url='http://127.0.0.1:8010') as client:
        snap = client.get('/api/games/nte/snapshot/events').json()
        status = effective(client)
        assert status['error'] == state['message'] and status['state'] == 'error'
        assert without_observation(status) == without_observation(snap['poll_status'])
        assert snap['version'] == '1.4' and len(snap['payload']) == 1 and snap['stale']
        assert any(r['id'] == row['id'] for r in client.get('/api/games/nte/snapshot/news').json()['payload'])


async def test_missing_cursor_and_page_limit_use_actual_window():
    async def missing(offset): return {'items': [post('9月15日活动')], 'has_more': True}
    with pytest.raises(SourceError, match='第1页分页游标异常.*7天历史回补'):
        await collect_pages(missing, UID, NOW, days=7, mode='backfill', pause=0)
    async def more(offset): return {'items': [post('9月15日活动')], 'has_more': True, 'offset': 'next'}
    with pytest.raises(SourceError, match='7天历史回补'):
        await collect_pages(more, UID, NOW, days=7, mode='backfill', max_pages=1, pause=0)
