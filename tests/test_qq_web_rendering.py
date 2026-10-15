"""Browser tests are opt-in locally and required by the Linux render CI job."""
import asyncio
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from PIL import Image, ImageChops
import pytest

from game_assistant.accounts.models import AccountScope, QueryResult
from game_assistant.qq.assets import PublicAssetCache
from game_assistant.qq.rendering import RenderQueue, RenderingUnavailable, SummaryRenderer, request_key, validate_web
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
        console.log('QQ_TEST:'+JSON.stringify({previous,allowed,missing,writeBlocked,externalBlocked,loopbackBlocked,workerBlocked,socketBlocked,loaded,now:Date.now()}));
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
            externalBlocked=True, loopbackBlocked=True, workerBlocked=True, socketBlocked=True, loaded=True,
            now=data.payload['web']['now']) for item in observations)
        assert downloads == ['https://webstatic.tajiduo.com/bbs/pic/player_003_256.png']
        assert not browser.contexts
    finally:
        await renderer.aclose()
        await cache.aclose()


def parity_view(case):
    """The same API observations feed the real cloud app and the QQ renderer."""
    from scripts.cloud.verify_qq_render import samples
    web = deepcopy(next(samples()))
    if case == 'overview':
        web.update(command='overview', game=None)
        return web, '/', '.game-summary', None
    if case == 'nte-summary':
        return web, '/game/nte', '.summary-metrics, .nte-module-card header h2, .nte-module-card .source-note, .nte-module-card .module-state, .nte-module-card footer', None
    if case == 'nte-gacha':
        web['command'] = 'gacha'
        return web, '/game/nte', '.pool-stat', '抽卡统计'
    if case == 'calendar':
        web['command'] = 'calendar'
        return web, '/calendar?game=nte', '.timeline-event', None
    entry = web['entries'][0]
    if case in ('endfield-summary', 'endfield-gacha'):
        web['game'] = entry['account']['game'] = 'endfield'
        entry['account']['roles'][0]['display_name'] = '同一管理员'
        entry['account']['provider'] = 'skland' if case == 'endfield-summary' else 'hypergryph'
        payloads = dict(account=dict(base=dict(name='同一管理员', level=0),
            stamina=dict(current=0, maximum=240), progress=[dict(name='每日任务', cur=0, total=100)]))
        if case == 'endfield-gacha':
            web['command'] = 'gacha'
            payloads = dict(account=dict(schema_version=1, nickname='同一寻访账号'),
                gacha=dict(schema_version=1, total=30, complete=True, pools=[dict(key='pool', label='特许寻访',
                    total=30, six_star=1, five_star=3, history=[], since_last_six=dict(count=0, status='exact'))]))
        entry['account']['capabilities'] = list(payloads)
        entry['snapshots'] = {key: dict(payload=value, state='ok', fetched_at='2026-10-15T12:00:00+08:00')
                              for key, value in payloads.items()}
        web['publicSnapshots'] = {'endfield': {'events': dict(payload=[], state='ok'), 'news': dict(payload=[], state='ok')}}
        prefix = '/api/accounts/synthetic/roles/synthetic-role/endfield/'
        web['responses'] = {prefix+'skland/card': dict(status=200, body=entry['snapshots']['account']),
                            prefix+'skland/attendance': dict(status=200, body=dict(status='signed', calendar=[])),
                            prefix+'gacha/records?pool_key=&offset=0&limit=50': dict(status=200, body=dict(records=[], total=0))}
        return web, '/game/endfield', '.pool-card' if case == 'endfield-gacha' else '.endfield-grid .cap-card', '抽卡统计' if case == 'endfield-gacha' else None
    if case == 'wuwa-summary':
        web['game'] = entry['account']['game'] = 'wuthering_waves'
        entry['account']['provider'] = 'kuro'
        payloads = dict(
            account=dict(nickname='同一漂泊者', level=70, extra=dict(role_id='synthetic-role', server_id='1')),
            stamina=dict(current=0, maximum=240),
            progress=[dict(name='每日活跃', cur=0, total=100)],
            exploration=[dict(name='合成地区', progress=0)],
            calabash=dict(level=20, max_level=30),
        )
        entry['account']['capabilities'] = list(payloads)
        entry['snapshots'] = {key: dict(payload=value, state='ok', fetched_at='2026-10-15T12:00:00+08:00')
                              for key, value in payloads.items()}
        web['publicSnapshots'] = {'wuthering_waves': {'events': dict(payload=[], state='ok'), 'news': dict(payload=[], state='ok')}}
        return web, '/game/wuthering_waves', '.summary-metrics, .wuwa-module-card h2, .wuwa-module-card > .wuwa-muted, .wuwa-module-card > .wuwa-status', None
    raise AssertionError(case)


def parity_service(source, renderer):
    from game_assistant.identity.models import Principal
    from game_assistant.qq.query_routes import QqQueryService
    from tests.test_qq_unified_queries import CachedQuery
    query = CachedQuery()
    for entry in source['entries']:
        account = entry['account']
        query.add(account['game'], account['provider'], account['account_id'],
                  {cap: deepcopy(snap['payload']) for cap, snap in entry['snapshots'].items()}, role=entry['role'])
        query.rows[-1]['roles'] = deepcopy(account['roles'])
        for cap, snap in entry['snapshots'].items():
            query.data[(account['account_id'], cap)] = QueryResult(deepcopy(snap['payload']), snap.get('fetched_at'), snap['state'], snap.get('complete'))
    if source['game'] == 'endfield':
        query.private = SimpleNamespace(
            ledger=lambda *args: SimpleNamespace(records=lambda *args: dict(records=[], total=0)),
            cached_skland=lambda scope: dict(attendance=dict(status='signed', calendar=[]), operators={}),
        )
    def public_read(game, cap):
        snap = source['publicSnapshots'].get(game, {}).get(cap, dict(payload=[], state='ok'))
        return QueryResult(deepcopy(snap['payload']), snap.get('fetched_at'), snap['state'], snap.get('complete'))
    queue = RenderQueue(renderer)
    service = QqQueryService(SimpleNamespace(resolve_qq_identity=lambda _: Principal('u', False)), query,
        SimpleNamespace(read=public_read), render_queue=queue,
        clock=lambda: datetime.fromtimestamp(source['now']/1000, timezone.utc))
    return service, queue


def crop_panel(image, box, scale, origin=None):
    origin = origin or dict(x=0, y=0)
    left, top = round((box['x']-origin['x'])*scale), round((box['y']-origin['y'])*scale)
    return image.crop((left, top, left+round(box['width']*scale), top+round(box['height']*scale)))


def pixel_difference(actual, expected, scale):
    # Raster origins can differ by one CSS pixel when a shared card follows
    # a different header. CSS geometry is checked separately, without tolerance.
    radius = scale
    area = (actual.width-2*radius)*(actual.height-2*radius)
    inner = actual.crop((radius, radius, actual.width-radius, actual.height-radius))
    differences = []
    for dx in range(-radius, radius+1):
        for dy in range(-radius, radius+1):
            reference = expected.crop((radius+dx, radius+dy, expected.width-radius+dx, expected.height-radius+dy))
            delta = ImageChops.difference(inner, reference)
            differences.append(sum(max(pixel) > 32 for pixel in delta.get_flattened_data()) / area)
    return min(differences)


async def panel_observations(page, selector):
    """Compare data, geometry and inherited styles, independently of either adapter."""
    return await page.locator(selector).evaluate_all("""nodes => nodes.map(node => {
        const origin = node.getBoundingClientRect();
        const styles = element => {
            const s = getComputedStyle(element), rect = element.getBoundingClientRect();
            return Object.fromEntries(['color','backgroundColor','fontFamily','fontSize','fontWeight',
                'lineHeight','borderRadius','padding','margin','gap','display','alignItems','gridTemplateColumns'].map(key => [key,s[key]])
                .concat([['width',Math.round(rect.width*100)/100],['height',Math.round(rect.height*100)/100],
                    ['left',Math.round((rect.x-origin.x)*100)/100],['top',Math.round((rect.y-origin.y)*100)/100]]));
        };
        return {text:node.innerText.replace(/\\s+/g,' ').trim(), geometry:node.getAttribute('style'), style:styles(node),
            children:[...node.querySelectorAll('h3,p,dl,dt,dd,strong,small,span,b,.metric-copy,.metric-symbol')].map(styles)};
    })""")


@pytest.mark.parametrize('case', ['overview', 'nte-summary', 'wuwa-summary', 'endfield-summary', 'endfield-gacha', 'nte-gacha', 'calendar'])
async def test_cloud_and_sent_image_share_display_results(case, browser_font, tmp_path):
    """Run index.html and the actual PNG path, without a user session or network."""
    import mimetypes
    web, path, selector, section = parity_view(case)
    dist = Path(__file__).resolve().parents[1] / 'frontend/dist'
    renderer = SummaryRenderer(frontend_dist=dist, font_path=browser_font, budget_seconds=15)
    service, queue = parity_service(web, renderer)
    browser = await renderer._start_browser(10000)
    new_context = browser.new_context
    captured = {}
    async def observe_capture(**kwargs):
        context = await new_context(**kwargs)
        close = context.close
        async def observe_and_close(**options):
            if context.pages:
                page = context.pages[0]
                captured['panels'] = await panel_observations(page, selector)
                captured['root'] = await page.locator('#qq-capture').bounding_box()
                captured['boxes'] = [await node.bounding_box() for node in await page.locator(selector).all()]
                if case == 'calendar':
                    captured['page_png'] = await page.screenshot(full_page=True, animations='disabled')
            await close(**options)
        context.close = observe_and_close
        return context
    browser.new_context = observe_capture
    calendar = case == 'calendar'
    width, scale = (1080, 1) if calendar else (540, 2)
    context = await new_context(viewport=dict(width=width, height=900), device_scale_factor=scale,
                                locale='zh-CN', timezone_id='Asia/Shanghai', color_scheme='dark',
                                reduced_motion='reduce', service_workers='block')
    errors, requests = [], []
    responses = {key: value['body'] for key, value in web['responses'].items()}
    responses.update({'/api/identity/me': dict(user_id='synthetic', is_admin=False),
                      '/api/identity/csrf': dict(csrf_token='synthetic-only'),
                      '/api/accounts': dict(accounts=[entry['account'] for entry in web['entries']])})
    for entry in web['entries']:
        prefix = '/api/accounts/' + entry['account']['account_id'] + '/roles/' + entry['role']
        responses.update({prefix + '/snapshot/' + cap: snap for cap, snap in entry['snapshots'].items()})
    for game in ('nte', 'wuthering_waves', 'endfield'):
        for cap in ('news', 'events'):
            responses[f'/api/public/games/{game}/{cap}'] = web['publicSnapshots'].get(game, {}).get(cap, dict(payload=[], state='ok'))
    static = {'/' + item.relative_to(dist).as_posix(): item for item in dist.rglob('*') if item.is_file()}
    async def offline(route):
        request = route.request
        requests.append(request.url)
        url = urlsplit(request.url)
        if request.method != 'GET' or url.netloc != 'cloud-parity.invalid':
            await route.abort()
        elif url.path == '/__qq_font__':
            await route.fulfill(body=Path(browser_font).read_bytes(), content_type='font/ttf')
        elif url.path.startswith('/api/'):
            key = url.path + ('?' + url.query if url.query else '')
            body = responses.get(key)
            await route.fulfill(status=200 if body is not None else 404, json=body if body is not None else {})
        elif url.path in static:
            item = static[url.path]
            await route.fulfill(body=item.read_bytes(), content_type=mimetypes.guess_type(item.name)[0] or 'application/octet-stream')
        else:
            await route.abort()
    await context.route('**/*', offline)
    await context.route_web_socket('**/*', lambda socket: socket.close())
    try:
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.clock.set_fixed_time(web['now'] / 1000)
        await page.goto('https://cloud-parity.invalid/index.html#' + path)
        await page.add_style_tag(content="@font-face{font-family:'Game CJK';src:url('/__qq_font__')}")
        await page.wait_for_load_state('networkidle')
        if calendar:
            await page.get_by_role('button', name='读取公共活动', exact=True).click()
            await page.wait_for_load_state('networkidle')
        (tmp_path/'cloud.html').write_text(await page.content(), encoding='utf-8')
        if section:
            await page.get_by_role('button', name=section, exact=True).click()
            if case == 'nte-gacha':
                await page.get_by_role('button', name='查看抽卡统计', exact=True).click()
        await page.locator(selector).first.wait_for()
        await page.wait_for_load_state('networkidle')
        await page.evaluate('document.fonts.ready')
        await page.mouse.move(0, 0)
        expected = await panel_observations(page, selector)
        assert expected, 'The reference cloud page must contain real data panels'
        from tests.test_qq_unified_queries import IDENTITY
        reply = await service.query_reply(IDENTITY, web['command'], web['game'], image_requested=True, budget_seconds=10)
        assert 'image' in reply, reply.get('text')
        raw = base64.b64decode(reply['image'], validate=True)
        image = Image.open(BytesIO(raw)).convert('RGB')
        assert image.width == 1080 and len(raw) <= 1048576
        assert not errors
        if calendar:
            # The export includes the full scrollable axis; percentages and
            # styling must match even when the surrounding sidebar is absent.
            for panel in [*expected, *captured['panels']]:
                panel['style'].pop('width')
                for child in panel['children']:
                    child.pop('width')
        (tmp_path/'qq-panels.json').write_text(json.dumps(captured['panels'], ensure_ascii=False, indent=2), encoding='utf-8')
        (tmp_path/'cloud-panels.json').write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding='utf-8')
        assert captured['panels'] == expected
        # Calendar intentionally exports the entire horizontally scrollable axis;
        # its event geometry/text comparison above must still agree.
        if calendar:
            reference_image = Image.open(BytesIO(captured['page_png'])).convert('RGB')
            expected_capture = crop_panel(reference_image, captured['root'], scale)
            assert image.size == expected_capture.size
            assert ImageChops.difference(image, expected_capture).getbbox() is None
        else:
            origin = captured['root']
            dialog_body = page.locator('dialog[open] > .nte-dialog-body, dialog[open] > .role-dialog-body')
            if await dialog_body.count():
                # Native dialogs center on fractional CSS coordinates. Align
                # only the reference raster phase; the shipped QQ PNG and all
                # layout/style assertions above remain untouched.
                reference = await page.locator(selector).first.bounding_box()
                phase = (captured['boxes'][0]['y'] - reference['y']) % (1 / scale)
                await dialog_body.evaluate("(node, phase) => { node.style.position='relative'; node.style.top=phase+'px' }", phase)
            cloud_boxes = await page.locator(selector).evaluate_all("nodes => nodes.map(node => { const r=node.getBoundingClientRect(); return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height} })")
            cloud_image = Image.open(BytesIO(await page.screenshot(full_page=case != 'nte-gacha', animations='disabled'))).convert('RGB')
            for index, (reference_box, box) in enumerate(zip(cloud_boxes, captured['boxes'])):
                if not box['width'] or not box['height']:
                    continue  # The equal DOM observations include empty status containers.
                actual = crop_panel(image, box, scale, origin)
                expected_image = crop_panel(cloud_image, reference_box, scale)
                actual.save(tmp_path / f'{case}-{index}-qq.png')
                expected_image.save(tmp_path / f'{case}-{index}-cloud.png')
                assert actual.size == expected_image.size
                changed = pixel_difference(actual, expected_image, scale)
                assert changed < .01, (case, index, changed)
        assert all(urlsplit(url).netloc == 'cloud-parity.invalid' for url in requests
                   if '/api/' in url), 'No real account or upstream API may be called'
    finally:
        await context.close()
        await queue.aclose()


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
