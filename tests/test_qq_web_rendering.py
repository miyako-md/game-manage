"""Browser tests are opt-in locally and required by the Linux render CI job."""
import asyncio
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path

from PIL import Image
import pytest

from game_assistant.accounts.models import AccountScope
from game_assistant.qq.assets import PublicAssetCache
from game_assistant.qq.rendering import RenderingUnavailable, SummaryRenderer, request_key, validate_web
from tests.qq_render_helpers import StubRenderer, png_bytes, result, web_document


@pytest.mark.parametrize('change', [
    lambda w: w.update(version=True),
    lambda w: w.update(command='refresh'),
    lambda w: w.update(url='https://private.example'),
    lambda w: w.update(now=float('nan')),
    lambda w: w['entries'][0]['account'].update(token='secret'),
    lambda w: w.update(responses={'https://private.example/api/x': {'status':200,'body':{}}}),
    lambda w: w.update(responses={'/api/../private': {'status':200,'body':{}}}),
    lambda w: w.update(responses={'/api/x': {'status':302,'body':{}}}),
])
def test_render_contract_rejects_non_display_inputs(change):
    web = web_document()
    change(web)
    with pytest.raises(RenderingUnavailable):
        validate_web(web)


def test_frozen_gets_allow_query_order_but_not_another_page_or_destination():
    path = '/api/accounts/a/roles/r/wuwa/gacha'
    assert request_key(path+'?limit=50&offset=0') == request_key(path+'?offset=0&limit=50')
    assert request_key(path+'?offset=50&limit=50') != request_key(path+'?offset=0&limit=50')
    for invalid in ('//private/api/a', '/api/a#private', '/api/%2e%2e/secret', '/api/a\\secret'):
        with pytest.raises(RenderingUnavailable):
            request_key(invalid)


async def test_frozen_asset_bytes_and_missing_images_invalidate_the_real_cache(monkeypatch):
    cache = PublicAssetCache()
    url = 'https://webstatic.tajiduo.com/bbs/pic/player_003_256.png'
    ref = cache.register_url(url)
    async def no_fetch(*args, **kwargs):
        pass
    monkeypatch.setattr(cache, 'prefetch', no_fetch)
    renderer = StubRenderer(asset_cache=cache)
    data = result()
    data.payload['web']['entries'][0]['snapshots']['account']['payload']['avatar_url'] = url
    scope = AccountScope('u', 'a', 'r')
    await renderer.render_summary(scope, data)
    await renderer.render_summary(scope, data)
    assert len(renderer.captures) == 1
    cache._store(ref, png_bytes())
    await renderer.render_summary(scope, data)
    assert len(renderer.captures) == 2
    await renderer.render_summary(scope, data)
    assert len(renderer.captures) == 2
    await renderer.aclose()
    await cache.aclose()


async def test_cancelled_caller_does_not_release_an_active_browser_slot():
    from game_assistant.qq.rendering import RenderQueue
    started, finish = asyncio.Event(), asyncio.Event()
    class Paused(StubRenderer):
        async def _capture(self, web, assets, deadline):
            started.set()
            await finish.wait()
            return png_bytes()
    queue = RenderQueue(Paused(), queue_limit=1)
    task = asyncio.create_task(queue.render(AccountScope('u','a','r'), result(), budget_seconds=2))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert queue.pending == 1
    assert await queue.render(AccountScope('v','b','s'), result(), budget_seconds=1) is None
    finish.set()
    await queue.aclose()
    assert queue.pending == 0


async def test_revocation_while_checking_assets_does_not_reuse_or_reinsert_cached_image(monkeypatch):
    renderer = StubRenderer()
    scope = AccountScope('u','a','r')
    await renderer.render_summary(scope, result())
    original = renderer._assets
    async def revoked(*args, **kwargs):
        renderer.invalidate_account('u','a')
        return await original(*args, **kwargs)
    monkeypatch.setattr(renderer, '_assets', revoked)
    assert await renderer.render_summary(scope, result())
    assert len(renderer.captures) == 2 and not renderer.cache
    await renderer.aclose()


@pytest.fixture
def browser_font():
    if os.environ.get('GA_RUN_BROWSER_TESTS') != '1':
        pytest.skip('Set GA_RUN_BROWSER_TESTS=1 after installing the render extra and Chromium')
    pytest.importorskip('playwright.async_api')
    return next(path for path in ('C:/Windows/Fonts/msyh.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc') if Path(path).is_file())


@pytest.fixture
def offline_dist(tmp_path):
    root = tmp_path / 'dist'
    root.mkdir()
    (root/'qq-render.html').write_text('<html data-qq-render="1"><body><main id="qq-capture"></main>'
        '<script type="module" src="/fixture.js"></script></body></html>', encoding='utf-8')
    (root/'fixture.js').write_text("""
        const data = window.__QQ_RENDER__;
        const root = document.getElementById('qq-capture');
        root.style.cssText='width:500px;min-height:180px;font-size:24px;color:#fff;background:#14171c';
        root.textContent = data.entries[0].snapshots.account.payload.nickname;
        const previous = localStorage.getItem('owner');
        localStorage.setItem('owner', root.textContent);
        const allowed = await fetch('/api/accounts/a/roles/r/frozen?limit=50&offset=0').then(r=>r.json());
        const missing = await fetch('/api/accounts/a/roles/r/frozen?offset=50&limit=50').then(r=>r.status);
        const writeBlocked = await fetch('/api/accounts/a/roles/r/refresh',{method:'POST'}).then(()=>false,()=>true);
        const externalBlocked = await fetch('https://example.com/private').then(()=>false,()=>true);
        const loopbackBlocked = await fetch('http://127.0.0.1:8020/internal/operations/health').then(()=>false,()=>true);
        const workerBlocked = await navigator.serviceWorker.register('/worker.js').then(registration=>!registration,()=>true);
        const socketBlocked = await new Promise(resolve=>{
          const socket=new WebSocket('wss://qq-render.invalid/socket');
          socket.onopen=()=>resolve(false);socket.onclose=()=>resolve(true);socket.onerror=()=>resolve(true);
        });
        const image=new Image();
        image.src='https://webstatic.tajiduo.com/bbs/pic/player_003_256.png';root.append(image);
        const loaded=await image.decode().then(()=>true,()=>false);
        console.log('QQ_TEST:'+JSON.stringify({previous,allowed,missing,writeBlocked,externalBlocked,loopbackBlocked,workerBlocked,socketBlocked,loaded}));
        window.__QQ_RENDER_READY__=true;
    """, encoding='utf-8')
    return root


async def test_browser_isolated_gets_assets_and_storage(offline_dist, browser_font, monkeypatch):
    from game_assistant.qq import assets as asset_module
    downloads, observations = [], []
    async def public_image(url, **kwargs):
        downloads.append(url)
        return png_bytes()
    monkeypatch.setattr(asset_module, '_download', public_image)
    cache = PublicAssetCache()
    renderer = SummaryRenderer(frontend_dist=offline_dist, font_path=browser_font, asset_cache=cache,
                               budget_seconds=10)
    browser = await renderer._start_browser(10000)
    original = browser.new_context
    async def new_context(**kwargs):
        context = await original(**kwargs)
        context.on('page', lambda page: page.on('console',
            lambda message: observations.append(json.loads(message.text[8:])) if message.text.startswith('QQ_TEST:') else None))
        return context
    monkeypatch.setattr(browser, 'new_context', new_context)
    try:
        for owner in ('first', 'second'):
            data = result(owner)
            data.payload['web']['responses'] = {'/api/accounts/a/roles/r/frozen?offset=0&limit=50':{'status':200,'body':{'frozen':True}}}
            raw = await renderer.render_summary(AccountScope(owner,'a','r'), data)
            image = Image.open(BytesIO(raw))
            assert image.width == 1000 and image.width * image.height <= 16000000 and len(raw) <= 1048576
        assert len(observations) == 2
        assert all(item == dict(previous=None, allowed={'frozen':True}, missing=404, writeBlocked=True,
            externalBlocked=True, loopbackBlocked=True, workerBlocked=True, socketBlocked=True, loaded=True) for item in observations)
        assert downloads == ['https://webstatic.tajiduo.com/bbs/pic/player_003_256.png']
        assert not browser.contexts
    finally:
        await renderer.aclose()
        await cache.aclose()


async def test_browser_uses_real_vue_components_and_rejects_oversized_capture(browser_font):
    dist = Path(__file__).resolve().parents[1] / 'frontend/dist'
    assert (dist/'qq-render.html').is_file(), 'Build the cloud frontend before browser tests'
    renderer = SummaryRenderer(frontend_dist=dist, font_path=browser_font, budget_seconds=10)
    seen = []
    browser = await renderer._start_browser(10000)
    original = browser.new_context
    async def observe(**kwargs):
        context = await original(**kwargs)
        close = context.close
        async def close_and_observe(**kwargs):
            if context.pages:
                seen.append(await context.pages[0].locator('#qq-capture').inner_text())
            await close(**kwargs)
        context.close = close_and_observe
        return context
    browser.new_context = observe
    try:
        data = result('合成面板账号')
        raw = await renderer.render_summary(AccountScope('u','a','r'), data)
        assert Image.open(BytesIO(raw)).width == 1080
        assert '异环' in seen[0] and '合成面板账号' in seen[0]
        assert await renderer.render_summary(AccountScope('u','a','r'), data) == raw
        assert len(seen) == 1
        renderer.max_pixels = 100
        with pytest.raises(RenderingUnavailable, match='pixel_limit'):
            await renderer.render_summary(AccountScope('u','a','r'), data)
        assert not browser.contexts
    finally:
        await renderer.aclose()
