"""Phase timings, browser warm-up and page-only cleanup; numbers and fixed codes only."""
import asyncio
import logging
from datetime import datetime
from types import SimpleNamespace

import pytest

from game_assistant.accounts.models import AccountScope, QueryResult
from game_assistant.qq.browser_rendering import BrowserRenderer
from game_assistant.qq.render_snapshot import game_panel, game_snapshot
from game_assistant.qq.rendering import RENDER_TIMING, RenderQueue, RenderedImage, RenderingUnavailable
from tests.test_qq_unified_queries import CachedQuery, IDENTITY, service

NOW = datetime.fromisoformat('2026-10-18T12:00:00+08:00')
SCOPE = AccountScope('fixture', 'fixture', 'fixture')


class Page:
    def __init__(self, state):
        self.state, self.closed = state, False
    def is_closed(self):
        return self.closed
    async def close(self):
        self.closed = True
    async def evaluate(self, script, *args):
        return self.state if '__LONG_RENDER_STATE__' in script else None


def renderer_with(tmp_path, ready):
    dist = tmp_path / 'dist'
    dist.mkdir(exist_ok=True)
    for name in ('render.html', 'render-a.html'):
        (dist / name).write_text('<!doctype html>', encoding='utf-8')
    renderer = BrowserRenderer(template='a', dist_path=str(dist))
    recycled = []
    async def recycle():
        recycled.append(1)
        renderer._a_page = None
    renderer._recycle = recycle
    renderer._a_ready = ready
    return renderer, recycled


def snapshot():
    panel = game_panel('nte', 'tajiduo', 'account', QueryResult({'nickname': '合成'}, NOW.isoformat(), 'ok', True))
    return game_snapshot([panel], NOW, title='异环 · 总览', command='异环 总览')


async def test_layout_failure_closes_only_the_page_and_keeps_phase_timings(tmp_path):
    page = Page({'state': 'loading'})
    async def ready():
        renderer._browser = SimpleNamespace(is_connected=lambda: True)
        renderer._a_page = page
    renderer, recycled = renderer_with(tmp_path, ready)
    timing = {}
    token = RENDER_TIMING.set(timing)
    try:
        with pytest.raises(RenderingUnavailable, match='qq_browser_not_ready'):
            await renderer._render_a(SCOPE, None, snapshot(), asyncio.get_running_loop().time() + 5, 'key', 0)
    finally:
        RENDER_TIMING.reset(token)
    assert not recycled and page.closed and renderer._a_page is None
    assert timing['render_cache'] == 'miss' and timing['browser'] == 'cold'
    assert {'ready_ms', 'mount_ms', 'images', 'images_cached', 'image_misses'} <= set(timing)
    assert all(type(value) is int for key, value in timing.items() if key.endswith('_ms'))
    assert renderer.last_state['timing'] is timing


@pytest.mark.parametrize('error', [RuntimeError('playwright target crashed'), RenderingUnavailable('qq_browser_runtime_unavailable')])
async def test_browser_failures_still_recycle_the_browser(tmp_path, error):
    async def ready():
        raise error
    renderer, recycled = renderer_with(tmp_path, ready)
    with pytest.raises(type(error)):
        await renderer._render_a(SCOPE, None, snapshot(), asyncio.get_running_loop().time() + 5, 'key', 0)
    assert recycled == [1]


async def test_prewarm_needs_an_enabled_built_renderer_and_recycles_on_failure(tmp_path):
    started = []
    async def ready():
        started.append(1)
    renderer, recycled = renderer_with(tmp_path, ready)
    assert await renderer.prewarm() is True and started == [1]
    renderer.enabled = False
    assert await renderer.prewarm() is False and started == [1]
    assert await BrowserRenderer(template='a', dist_path=str(tmp_path / 'missing')).prewarm() is False
    async def broken():
        raise RuntimeError('launch failed')
    renderer.enabled, renderer._a_ready = True, broken
    with pytest.raises(RuntimeError):
        await renderer.prewarm()
    assert recycled == [1]


async def test_queue_prewarm_runs_under_the_render_lock_and_logs_codes_only(caplog):
    caplog.set_level(logging.INFO)
    events = []
    class Renderer:
        async def prewarm(self):
            events.append('prewarm-start')
            await asyncio.sleep(.02)
            events.append('prewarm-end')
            return True
        async def render_summary_async(self, *args, **kwargs):
            events.append('render')
            return RenderedImage(b'png')
    queue = RenderQueue(Renderer())
    try:
        task = queue.prewarm()
        await asyncio.sleep(0)
        assert await queue.render(SCOPE, QueryResult({}, None, 'ok', None), budget_seconds=1) == b'png'
        await task
        assert events == ['prewarm-start', 'prewarm-end', 'render']
        assert any(record.getMessage().startswith('QQ render prewarm: ready ms=') for record in caplog.records)
    finally:
        await queue.aclose()
    class Failing:
        async def prewarm(self):
            raise RenderingUnavailable('C:/private/path')
    queue = RenderQueue(Failing())
    await queue.prewarm()
    await queue.aclose()
    assert 'QQ render prewarm failed: qq_render_unavailable' in caplog.text and 'private' not in caplog.text
    assert RenderQueue(SimpleNamespace()).prewarm() is None


async def test_queue_close_cancels_a_pending_prewarm():
    class Renderer:
        async def prewarm(self):
            await asyncio.sleep(30)
    queue = RenderQueue(Renderer())
    task = queue.prewarm()
    await asyncio.sleep(0)
    await asyncio.wait_for(queue.aclose(), 2)
    assert task.done()


def test_service_does_not_prewarm_when_qq_images_are_disabled():
    assert service(CachedQuery()).start_prewarm() is None


def test_cloud_start_prewarms_only_with_qq_images_enabled(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from tests.test_account_queries import cloud_settings
    from game_assistant.cloud_app import create_cloud_app
    from game_assistant.scheduler import AccountPollingScheduler
    monkeypatch.setattr(AccountPollingScheduler, 'start', lambda self: None)
    calls = []
    monkeypatch.setattr(RenderQueue, 'prewarm', lambda self, **kwargs: calls.append(self))
    for enabled in (False, True):
        (tmp_path / str(enabled)).mkdir()
        settings = cloud_settings(tmp_path / str(enabled), qq_app_id='app', qq_service_token='fixture', qq_images_enabled=enabled)
        app = create_cloud_app(settings, start_scheduler=True)
        with TestClient(app, base_url='https://cloud.example'):
            assert (app.state.qq_query.render_queue is not None) is enabled
    assert len(calls) == 1


async def test_query_reply_records_one_timing_line_without_user_data(caplog):
    caplog.set_level(logging.INFO)
    query = CachedQuery()
    query.add('nte', 'tajiduo', 'PRIVATE-ACCOUNT', {'account': {'nickname': 'PRIVATE-NAME'}, 'roles': {'entries': [{'id': '1003', 'name': '早雾'}]}})
    from game_assistant.qq.assets import PublicAssetCache
    class Cache(PublicAssetCache):
        async def prefetch(self, refs, **kwargs):
            return {'hit': 1, 'miss': 2, 'failed': 0, 'timeout': 1}
    class Queue:
        renderer = SimpleNamespace(invalidate_account=lambda *args: None)
        async def render(self, scope, result, **kwargs):
            RENDER_TIMING.get().update(render_cache='miss', browser='warm', ready_ms=1, mount_ms=2, screenshot_ms=3, encode_ms=4)
            return RenderedImage(b'png')
    api = service(query, queue=Queue())
    api.asset_cache = Cache()
    reply = await api.query_reply(IDENTITY, 'summary', 'nte', image_requested=True, budget_seconds=5)
    assert reply['image']
    timing = api.last_timing
    assert timing['command'] == 'summary' and timing['game'] == 'nte' and timing['result'] == 'image'
    assert (timing['prefetch_hit'], timing['prefetch_miss'], timing['prefetch_timeout'], timing['browser']) == (1, 2, 1, 'warm')
    assert {'query_ms', 'prefetch_ms', 'total_ms', 'mount_ms'} <= set(timing)
    lines = [record.getMessage() for record in caplog.records if record.getMessage().startswith('QQ render timing: ')]
    assert len(lines) == 1 and 'PRIVATE' not in caplog.text and '早雾' not in caplog.text
    assert RENDER_TIMING.get() is None


async def test_queue_fallbacks_record_their_code_in_the_reply_timing():
    class Renderer:
        async def render_summary_async(self, *args, **kwargs):
            raise RenderingUnavailable('qq_browser_not_ready')
    queue = RenderQueue(Renderer())
    try:
        for budget, code in ((0, 'qq_render_budget_exhausted'), (1, 'qq_browser_not_ready')):
            timing = {}
            token = RENDER_TIMING.set(timing)
            try:
                assert await queue.render(SCOPE, QueryResult({}, None, 'ok', None), budget_seconds=budget) is None
            finally:
                RENDER_TIMING.reset(token)
            assert timing['result'] == code
    finally:
        await queue.aclose()
