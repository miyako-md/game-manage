"""Render the cloud dashboard's Vue components in an isolated offline browser."""
import asyncio
from collections import OrderedDict
import hashlib
from io import BytesIO
import json
import mimetypes
from pathlib import Path
import re
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

from PIL import Image, ImageFont

from game_assistant.accounts.models import AccountScope, QueryResult
from .assets import safe_public_url
from .cards import validate_card_document, card_to_text

TEMPLATE_VERSION = 'cloud-components-1'
RENDER_ORIGIN = 'https://qq-render.invalid'
ENTRY_PATH = '/qq-render.html'
MAX_PAYLOAD_BYTES = 4 * 1024 * 1024
STATIC_TYPES = {'.js', '.css', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.ico', '.woff', '.woff2', '.ttf'}
WEB_COMMANDS = frozenset(('overview', 'summary', 'roles', 'stamina', 'exploration', 'combat',
    'progress', 'gacha', 'calendar', 'events', 'recent_events', 'news', 'calabash',
    'activities', 'resources', 'realestate', 'vehicles', 'teams', 'record'))


class RenderingUnavailable(Exception):
    """The caller may use its text reply without attempting an image send."""


class ImagePreparationFailed(Exception):
    """No message send was attempted; a text reply with the same sequence is safe."""


def request_key(value):
    """Canonicalize a frozen GET key without accepting arbitrary destinations."""
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise RenderingUnavailable('qq_render_invalid_response_path')
    parts = urlsplit(value)
    if (parts.scheme or parts.netloc or parts.fragment or not parts.path.startswith('/api/')
            or '\\' in value or '..' in value or '%' in parts.path):
        raise RenderingUnavailable('qq_render_invalid_response_path')
    query = parse_qsl(parts.query, keep_blank_values=True, max_num_fields=20)
    return parts.path + ('?' + urlencode(sorted(query)) if query else '')


def validate_web(value):
    allowed = {'version', 'command', 'game', 'roleName', 'now', 'entries', 'publicSnapshots', 'responses'}
    if not isinstance(value, dict) or set(value) != allowed or type(value['version']) is not int or value['version'] != 1:
        raise RenderingUnavailable('qq_render_invalid_document')
    if (not isinstance(value['command'], str) or value['command'] not in WEB_COMMANDS
            or value['game'] not in (None, 'wuthering_waves', 'nte', 'endfield')
            or type(value['now']) is not int or not 0 < value['now'] < 10**15
            or value['roleName'] is not None and (not isinstance(value['roleName'], str) or not 1 <= len(value['roleName']) <= 64)):
        raise RenderingUnavailable('qq_render_invalid_document')
    entries = value['entries']
    if not isinstance(entries, list) or len(entries) > 4 or not isinstance(value['publicSnapshots'], dict):
        raise RenderingUnavailable('qq_render_invalid_document')
    for entry in entries:
        if (not isinstance(entry, dict) or set(entry) != {'account', 'role', 'snapshots'}
                or not isinstance(entry['account'], dict) or not isinstance(entry['snapshots'], dict)
                or not isinstance(entry['role'], str) or not 1 <= len(entry['role']) <= 256):
            raise RenderingUnavailable('qq_render_invalid_document')
        if set(entry['account']) - {'account_id', 'game', 'provider', 'state', 'capabilities', 'roles', 'is_default'}:
            raise RenderingUnavailable('qq_render_invalid_document')
    responses = value['responses']
    if not isinstance(responses, dict) or len(responses) > 48:
        raise RenderingUnavailable('qq_render_invalid_responses')
    for key, response in responses.items():
        request_key(key)
        if (not isinstance(response, dict) or set(response) != {'status', 'body'}
                or type(response['status']) is not int or response['status'] not in (200, 404, 503)):
            raise RenderingUnavailable('qq_render_invalid_responses')
    try:
        encoded = json.dumps(value, ensure_ascii=True, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise RenderingUnavailable('qq_render_invalid_document') from None
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise RenderingUnavailable('qq_render_payload_limit')
    return value


def encode_image(png, *, max_bytes):
    if len(png) <= max_bytes:
        return png
    with Image.open(BytesIO(png)) as source:
        image = source.convert('RGB')
    for quality in (88, 80, 72):
        output = BytesIO()
        image.save(output, format='JPEG', quality=quality, subsampling=0, optimize=True)
        if output.tell() <= max_bytes:
            return output.getvalue()
    raise RenderingUnavailable('qq_image_size_limit')


class SummaryRenderer:
    def __init__(self, *, frontend_dist=None, font_path='', max_bytes=1048576, cache_entries=16,
                 cache_ttl=120, max_pixels=16000000, budget_seconds=8, asset_cache=None):
        self.frontend_dist = Path(frontend_dist).absolute() if frontend_dist else None
        self.font_path = font_path
        self.max_bytes = max(1, min(max_bytes, 1048576))
        self.max_pixels = max(1, min(max_pixels, 16000000))
        self.budget_seconds = max(.001, min(budget_seconds, 10))
        self.asset_cache = asset_cache
        self.cache_entries = max(0, min(cache_entries, 32))
        self.cache_ttl = max(0, min(cache_ttl, 300))
        self.cache = OrderedDict()
        self.generation = 0
        self._static = None
        self._build_digest = ''
        self._playwright = None
        self._browser = None

    def _payload(self, result):
        payload = result.payload
        allowed = {'text', 'card', 'web', 'grant_version', 'snapshot_times', 'scopes', 'snapshot_fingerprints'}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise RenderingUnavailable('qq_image_safe_summary_required')
        if 'card' in payload:
            try:
                card = validate_card_document(payload['card'])
            except (ValueError, TypeError):
                raise RenderingUnavailable('qq_image_safe_summary_required') from None
            if 'text' in payload and payload['text'] != card_to_text(card):
                raise RenderingUnavailable('qq_image_text_card_mismatch')
        if 'web' in payload:
            validate_web(payload['web'])
        version = payload.get('grant_version')
        if version is not None and (type(version) is not int or version < 1):
            raise RenderingUnavailable('qq_image_safe_summary_required')
        scopes = payload.get('scopes', [])
        if not isinstance(scopes, list) or len(scopes) > 4:
            raise RenderingUnavailable('qq_image_safe_summary_required')
        for item in scopes:
            if (not isinstance(item, dict) or set(item) != {'account_id', 'role_id', 'grant_version'}
                    or any(not isinstance(item[k], str) or not 1 <= len(item[k]) <= 256 for k in ('account_id', 'role_id'))
                    or type(item['grant_version']) is not int or item['grant_version'] < 1):
                raise RenderingUnavailable('qq_image_safe_summary_required')
        fingerprints = payload.get('snapshot_fingerprints', [])
        times = payload.get('snapshot_times', [])
        if (not isinstance(fingerprints, list) or len(fingerprints) > 64
                or any(not isinstance(f, str) or not re.fullmatch('[0-9a-f]{64}', f) for f in fingerprints)
                or not isinstance(times, list) or len(times) > 64
                or any(t is not None and (not isinstance(t, str) or len(t) > 128) for t in times)):
            raise RenderingUnavailable('qq_image_safe_summary_required')
        return payload

    def cache_key(self, scope, result, *, assets=None):
        payload = self._payload(result)
        fingerprint = [scope.user_id, scope.account_id, scope.role_id, payload, result.fetched_at,
            result.state, result.complete, TEMPLATE_VERSION, self._build_digest, self.font_path,
            self.max_bytes, self.max_pixels, self.budget_seconds,
            sorted((ref, hashlib.sha256(raw).hexdigest()) for ref, raw in (assets or {}).items())]
        return hashlib.sha256(json.dumps(fingerprint, ensure_ascii=True, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def invalidate_account(self, user_id, account_id=None):
        self.generation += 1
        for key, (owner, _, _, _) in list(self.cache.items()):
            if owner[0] == user_id and (account_id is None or account_id in owner[1]):
                del self.cache[key]

    def _load_static(self):
        if self._static is not None:
            return
        dist = self.frontend_dist
        if dist is None or not dist.is_dir() or any(p.is_symlink() for p in (dist, *dist.parents)):
            raise RenderingUnavailable('qq_render_frontend_unavailable')
        entry = dist / ENTRY_PATH[1:]
        if not entry.is_file() or entry.is_symlink() or 'data-qq-render' not in entry.read_text(encoding='utf-8'):
            raise RenderingUnavailable('qq_render_frontend_unavailable')
        files = {}
        total = 0
        for path in sorted(dist.rglob('*')):
            if path.is_symlink() or not path.resolve().is_relative_to(dist.resolve()):
                raise RenderingUnavailable('qq_render_unsafe_frontend')
            if path.is_file() and (path == entry or path.suffix in STATIC_TYPES):
                raw = path.read_bytes()
                total += len(raw)
                if len(raw) > 32 * 1024 * 1024 or total > 64 * 1024 * 1024:
                    raise RenderingUnavailable('qq_render_frontend_limit')
                files['/' + path.relative_to(dist).as_posix()] = (raw, mimetypes.guess_type(path)[0] or 'application/octet-stream')
        path = Path(self.font_path)
        if not self.font_path or not path.is_absolute() or not path.is_file():
            raise RenderingUnavailable('qq_image_cjk_font_unavailable')
        try:
            index = 2 if path.name == 'NotoSansCJK-Regular.ttc' else 0
            font = ImageFont.truetype(str(path), 30, index=index)
            tofu = bytes(font.getmask('\uffff'))
            if any(bytes(font.getmask(c)) == tofu for c in '鸣潮未知账号等级'):
                raise ValueError()
        except (OSError, ValueError):
            raise RenderingUnavailable('qq_image_cjk_font_unavailable') from None
        font_bytes = path.read_bytes()
        if len(font_bytes) > 32 * 1024 * 1024:
            raise RenderingUnavailable('qq_image_font_limit')
        files['/__qq_font__'] = (font_bytes, 'font/collection' if path.suffix.lower() == '.ttc' else 'font/ttf')
        self._build_digest = hashlib.sha256(b''.join(key.encode() + hashlib.sha256(raw).digest()
            for key, (raw, _) in sorted(files.items()))).hexdigest()
        self._static = files

    async def _assets(self, payload, budget, known_refs=()):
        if self.asset_cache is None:
            return {}
        refs = list(known_refs)
        pending = [payload['web']]
        while pending and len(refs) < 512:
            item = pending.pop()
            if isinstance(item, dict):
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
            elif isinstance(item, str) and safe_public_url(item):
                ref = self.asset_cache.register_url(item)
                if ref:
                    refs.append(ref)
        refs = list(dict.fromkeys(refs))[:512]
        await self.asset_cache.prefetch(refs, budget_seconds=min(2, budget * .25))
        return {ref: self.asset_cache.get_png(ref) for ref in refs}

    async def _start_browser(self, timeout):
        # This optional extra is needed only by the API process when images are enabled.
        try:
            from playwright.async_api import async_playwright, Error
        except ModuleNotFoundError:
            raise RenderingUnavailable('qq_render_dependency_unavailable') from None
        self._browser_error = Error
        if self._browser is not None and self._browser.is_connected():
            return self._browser
        try:
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True, chromium_sandbox=True,
                timeout=timeout, args=['--host-resolver-rules=MAP * ~NOTFOUND', '--disable-background-networking'])
            return self._browser
        except (Error, OSError, NotImplementedError):
            await self.aclose()
            raise RenderingUnavailable('qq_render_browser_unavailable') from None

    async def _capture(self, web, assets, deadline):
        browser = await self._start_browser(max(1, (deadline - time.monotonic()) * 1000))
        calendar = web['command'] in ('calendar', 'events', 'recent_events')
        width, scale = (1080, 1) if calendar else (540, 2)
        try:
            context = await browser.new_context(viewport={'width': width, 'height': 900}, device_scale_factor=scale,
                locale='zh-CN', timezone_id='Asia/Shanghai', color_scheme='dark', reduced_motion='reduce',
                service_workers='block', accept_downloads=False)
        except self._browser_error:
            raise RenderingUnavailable('qq_render_browser_unavailable') from None
        responses = {request_key(path): response for path, response in web['responses'].items()}
        state = {key: value for key, value in web.items() if key != 'responses'}
        asset_tasks = {}
        csp = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
               "img-src 'self' https: data:; font-src 'self'; connect-src 'self'; "
               "worker-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'")

        async def route_request(route):
            request = route.request
            url = urlsplit(request.url)
            if request.method != 'GET':
                await route.abort()
                return
            if request.is_navigation_request() and (request.url != RENDER_ORIGIN + ENTRY_PATH or request.frame.parent_frame is not None):
                await route.abort()
                return
            if url.scheme == 'https' and url.netloc == 'qq-render.invalid':
                if url.path.startswith('/api/'):
                    try:
                        response = responses.get(request_key(url.path + ('?' + url.query if url.query else '')))
                    except (RenderingUnavailable, ValueError):
                        response = None
                    await route.fulfill(status=response['status'] if response else 404, content_type='application/json',
                        body=json.dumps(response['body'] if response else {'detail': '尚无此项缓存，请先在网站查看。'}, ensure_ascii=True),
                        headers={'Cache-Control': 'no-store'})
                    return
                item = self._static.get(url.path) if not url.query and not url.fragment else None
                if item:
                    await route.fulfill(body=item[0], content_type=item[1],
                        headers={'Content-Security-Policy': csp, 'Cache-Control': 'no-store'})
                    return
            if request.resource_type == 'image' and self.asset_cache is not None:
                ref = self.asset_cache.register_url(request.url)
                if ref is not None and ref not in assets and len(assets) < 512:
                    # Shared components also resolve images from their own audited catalogs.
                    # Only Python fetches these; freeze exactly the sanitized bytes we serve.
                    assets[ref] = None
                    async def load_asset(reference):
                        await self.asset_cache.prefetch([reference], budget_seconds=min(2, max(0, deadline - time.monotonic()) * .5))
                        assets[reference] = self.asset_cache.get_png(reference)
                    asset_tasks[ref] = asyncio.create_task(load_asset(ref))
                if ref in asset_tasks:
                    await asset_tasks[ref]
                if assets.get(ref) is not None:
                    await route.fulfill(body=assets[ref], content_type='image/png', headers={'Cache-Control': 'no-store'})
                    return
            await route.abort()

        try:
            context.set_default_timeout(max(1, (deadline - time.monotonic()) * 1000))
            await context.route('**/*', route_request)
            await context.route_web_socket('**/*', lambda socket: socket.close())
            # JSON is passed as a JS string to JSON.parse, never embedded in HTML.
            await context.add_init_script(script='window.__QQ_RENDER__ = JSON.parse(' +
                json.dumps(json.dumps(state, ensure_ascii=True, allow_nan=False)) + ');' +
                "window.open = () => null; window.RTCPeerConnection = undefined; window.webkitRTCPeerConnection = undefined;")
            page = await context.new_page()
            await page.goto(RENDER_ORIGIN + ENTRY_PATH, wait_until='load')
            await page.add_style_tag(content="@font-face{font-family:QqRenderFont;src:url('/__qq_font__')}"
                "#qq-capture{font-family:QqRenderFont,var(--font-sans)}")
            while True:
                ready = await page.evaluate('() => ({ready: window.__QQ_RENDER_READY__ === true, error: !!window.__QQ_RENDER_ERROR__})')
                if ready['ready'] or ready['error']:
                    break
                await asyncio.sleep(.025)
            if ready['error']:
                raise RenderingUnavailable('qq_render_component_failed')
            await page.evaluate("""async () => {
                for (const image of document.images) image.loading = 'eager';
                await document.fonts.ready;
                await Promise.all([...document.images].map(image => image.decode().catch(() => {})));
                await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame);
            }""")
            capture = page.locator('#qq-capture')
            bounds = await capture.bounding_box()
            if (not bounds or bounds['width'] <= 0 or bounds['width'] > width + .1 or bounds['height'] <= 0
                    or bounds['width'] * bounds['height'] * scale**2 > self.max_pixels or bounds['height'] * scale > 16000):
                raise RenderingUnavailable('qq_image_pixel_limit')
            return await capture.screenshot(type='png', animations='disabled', caret='hide', scale='device')
        except self._browser_error:
            raise RenderingUnavailable('qq_render_browser_failed') from None
        finally:
            for task in asset_tasks.values():
                if not task.done():
                    task.cancel()
            if asset_tasks:
                await asyncio.gather(*asset_tasks.values(), return_exceptions=True)
            await context.close()

    async def render_summary(self, scope: AccountScope, result: QueryResult, *, budget_seconds=None) -> bytes:
        payload = self._payload(result)
        if 'web' not in payload:
            raise RenderingUnavailable('qq_render_web_document_required')
        budget = min(self.budget_seconds, budget_seconds if budget_seconds is not None else self.budget_seconds)
        deadline = time.monotonic() + budget
        generation = self.generation
        try:
            async with asyncio.timeout(budget):
                self._load_static()
                key = self.cache_key(scope, result)
                for expired, (_, expiry, _, _) in list(self.cache.items()):
                    if expiry <= time.monotonic():
                        del self.cache[expired]
                cached = self.cache.get(key)
                assets = await self._assets(payload, budget, cached[3] if cached else ())
                fingerprints = lambda: {ref: hashlib.sha256(raw).hexdigest() if raw else 'missing' for ref, raw in assets.items()}
                if cached is not None and self.cache.get(key) is cached and self.generation == generation and fingerprints() == cached[3]:
                    self.cache.move_to_end(key)
                    return cached[2]
                png = await self._capture(payload['web'], assets, deadline)
                encoded = await asyncio.to_thread(encode_image, png, max_bytes=self.max_bytes)
                if self.generation == generation and self.cache_entries:
                    accounts = frozenset([scope.account_id] + [s['account_id'] for s in payload.get('scopes', [])])
                    self.cache[key] = ((scope.user_id, accounts), time.monotonic() + self.cache_ttl, encoded, fingerprints())
                    while len(self.cache) > self.cache_entries:
                        self.cache.popitem(last=False)
                return encoded
        except TimeoutError:
            raise RenderingUnavailable('qq_image_time_limit') from None

    async def aclose(self):
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self.cache.clear()


class RenderQueue:
    """One browser job at a time, retaining its slot until context cleanup finishes."""
    def __init__(self, renderer, *, queue_limit=10):
        self.renderer = renderer
        self.queue_limit = max(1, min(queue_limit, 10))
        self.pending = 0
        self.lock = asyncio.Semaphore(1)
        self.tasks = set()

    async def render(self, scope, result, *, budget_seconds):
        if budget_seconds <= 0 or self.pending >= self.queue_limit:
            return None
        expires = time.monotonic() + min(budget_seconds, 10)
        self.pending += 1

        async def work():
            try:
                async with self.lock:
                    remaining = expires - time.monotonic()
                    if remaining <= 0:
                        return None
                    try:
                        return await self.renderer.render_summary(scope, result, budget_seconds=remaining)
                    except RenderingUnavailable:
                        return None
            finally:
                self.pending -= 1

        task = asyncio.create_task(work())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=max(0, expires - time.monotonic()))
        except asyncio.TimeoutError:
            return None

    async def aclose(self):
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        await self.renderer.aclose()
