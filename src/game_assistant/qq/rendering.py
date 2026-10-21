"""Shared renderer contract and the bounded render queue for QQ images.

No remote assets or disk cache. Fonts are operator-provided system fonts;
Ubuntu operators can install fonts-noto-cjk. Windows fonts are never bundled.
"""
import asyncio
from collections import OrderedDict
from contextvars import ContextVar
import hashlib
import json
import logging
import re
from pathlib import Path
import threading
import time

from PIL import ImageFont

from game_assistant.accounts.models import AccountScope, QueryResult
from .commands import safe_text
from .cards import validate_card_document, card_to_text, image_references

TEMPLATE_VERSION = 'qq-unified-4-skins'
logger = logging.getLogger(__name__)
# Exact codes only: never put exception text, scopes or rendered input in logs.
RENDER_DIAGNOSTIC_CODES = frozenset('''
qq_browser_build_unavailable qq_browser_cleanup_failed qq_browser_cleanup_unconfirmed
qq_browser_data_limit qq_browser_disabled qq_browser_invalid_snapshot
qq_browser_not_ready qq_browser_page_limit qq_browser_private_field
qq_browser_runtime_unavailable qq_browser_selected_role_unavailable
qq_browser_shared_content_incomplete qq_browser_shared_content_unavailable qq_browser_unsupported_panel
qq_image_cjk_font_unavailable qq_image_pixel_limit qq_image_safe_summary_required
qq_image_size_limit qq_image_text_card_mismatch qq_image_time_limit
'''.split())
# One reply's phase timings: whole milliseconds, counts and the fixed codes above only.
# The render task copies the caller's context, so the renderer fills the caller's dict.
RENDER_TIMING = ContextVar('qq_render_timing', default=None)


def elapsed_ms(started):
    return round((time.monotonic() - started) * 1000)


class RenderingUnavailable(Exception):
    """Known pre-send failure: the caller may safely use its text reply."""


class RenderingPageUnavailable(RenderingUnavailable):
    def __init__(self, page, total_pages):
        self.page, self.total_pages = page, total_pages
        super().__init__('qq_browser_page_out_of_range')


class RenderedImage(bytes):
    def __new__(cls, value, *, page=1, total_pages=1):
        result=super().__new__(cls,value)
        result.page,result.total_pages=page,total_pages
        return result


class ImagePreparationFailed(Exception):
    """No message send was attempted; a text reply with the same sequence is safe."""


class SummaryRenderer:
    def __init__(self, *, font_path='', max_bytes=1048576, cache_entries=16, cache_ttl=120,
                 max_pixels=16000000, budget_seconds=8, asset_cache=None):
        self.font_path = font_path
        self.max_bytes = max(1,min(max_bytes,1048576))
        self.max_pixels = max(1, min(max_pixels, 16000000))
        self.asset_cache = asset_cache
        self.budget_seconds = max(0.001, min(budget_seconds, 10))
        self.cache_entries = max(0, min(cache_entries, 32))
        self.cache_ttl = max(0, min(cache_ttl, 300))
        self.cache = OrderedDict()
        self.lock = threading.RLock()
        self.generation = 0

    def _payload(self, result):
        payload = result.payload
        if not isinstance(payload, dict) or set(payload) - {'text', 'card', 'render_snapshot', 'shared_required', 'grant_version', 'snapshot_times', 'scopes', 'snapshot_fingerprints'}:
            raise RenderingUnavailable('qq_image_safe_summary_required')
        payload = dict(payload)
        if 'card' in payload:
            try:
                payload['card'] = validate_card_document(payload['card'])
                text = card_to_text(payload['card'])
            except (ValueError, TypeError):
                raise RenderingUnavailable('qq_image_safe_summary_required') from None
            if 'text' in payload and payload['text'] != text:
                raise RenderingUnavailable('qq_image_text_card_mismatch')
            payload['text'] = text
        else:
            text = payload.get('text')
            if not isinstance(text, str) or not text or len(text) > 1800:
                raise RenderingUnavailable('qq_image_safe_summary_required')
            payload['text'] = safe_text(text)
        grant_version = payload.get('grant_version')
        if grant_version is not None and (type(grant_version) is not int or grant_version < 1):
            raise RenderingUnavailable('qq_image_safe_summary_required')
        times = payload.get('snapshot_times', [])
        if not isinstance(times, list) or len(times) > 24 or any(t is not None and (not isinstance(t, str) or len(t)>128) for t in times):
            raise RenderingUnavailable('qq_image_safe_summary_required')
        scopes = payload.get('scopes', [])
        if not isinstance(scopes,list) or len(scopes)>4:
            raise RenderingUnavailable('qq_image_safe_summary_required')
        for item in scopes:
            if (not isinstance(item,dict) or set(item)!={'account_id','role_id','grant_version'}
                or any(not isinstance(item[k],str) or not 1<=len(item[k])<=256 for k in ('account_id','role_id'))
                or type(item['grant_version']) is not int or item['grant_version']<1):
                raise RenderingUnavailable('qq_image_safe_summary_required')
        fingerprints = payload.get('snapshot_fingerprints', [])
        if (not isinstance(fingerprints,list) or len(fingerprints)>24
            or any(not isinstance(f,str) or not re.fullmatch('[0-9a-f]{64}',f) for f in fingerprints)):
            raise RenderingUnavailable('qq_image_safe_summary_required')
        return payload

    def cache_key(self, scope: AccountScope, result: QueryResult):
        payload = self._payload(result)
        fingerprint = [scope.user_id, scope.account_id, scope.role_id, payload,
                       result.fetched_at, result.state, result.complete,
                       TEMPLATE_VERSION, self.font_path, self.max_bytes, self.max_pixels, self.budget_seconds]
        if 'card' in payload:
            fingerprint.append([(ref,self.asset_cache.fingerprint(ref) if self.asset_cache is not None else 'missing')
                                for ref in image_references(payload['card'])])
        return hashlib.sha256(json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def invalidate_account(self, user_id, account_id=None):
        with self.lock:
            self.generation += 1
            for key, (owner, _, _) in list(self.cache.items()):
                if owner[0] == user_id and (account_id is None or account_id in owner[1]):
                    del self.cache[key]

    def _font(self):
        # Explicit path only: absence produces text, never unreadable tofu glyphs.
        path = Path(self.font_path)
        if not self.font_path or not path.is_absolute() or not path.is_file():
            raise RenderingUnavailable('qq_image_cjk_font_unavailable')
        try:
            # The standard Noto CJK TTC orders JP, KR, SC, TC, HK faces.
            index = 2 if path.name == 'NotoSansCJK-Regular.ttc' else 0
            font = ImageFont.truetype(str(path), 30,index=index)
            tofu = bytes(font.getmask('\uffff'))
            if any(bytes(font.getmask(c)) == tofu for c in '鸣潮未知账号等级'):
                raise ValueError()
            return font
        except Exception:
            raise RenderingUnavailable('qq_image_cjk_font_unavailable') from None


class RenderQueue:
    """One worker, up to ten admitted requests, with strict caller deadlines.

Timed-out work keeps its slot until the worker really finishes. Cancelling
the HTTP request never starts a second render concurrently.
"""
    def __init__(self, renderer, *, queue_limit=10):
        self.renderer = renderer
        self.queue_limit = max(1, min(queue_limit, 10))
        self.pending = 0
        self.lock = asyncio.Semaphore(1)
        self.tasks = set()
        self._prewarm = None

    async def render(self, scope, result, *, budget_seconds):
        timing = RENDER_TIMING.get()
        def fallback(code):
            logger.warning('QQ render fallback: %s', code)
            if timing is not None:timing['result'] = code
        if budget_seconds <= 0:
            fallback('qq_render_budget_exhausted')
            return None
        if self.pending >= self.queue_limit:
            fallback('qq_render_queue_full')
            return None
        queued = time.monotonic()
        expires = queued + min(budget_seconds, 10)
        self.pending += 1
        async def work():
            try:
                async with self.lock:
                    if timing is not None:timing['queue_ms'] = elapsed_ms(queued)
                    if time.monotonic() >= expires:
                        fallback('qq_render_queue_expired')
                        return None
                    try:
                        return await self.renderer.render_summary_async(scope, result, budget_seconds=max(0, expires-time.monotonic()))
                    except RenderingPageUnavailable as error:
                        return error
                    except RenderingUnavailable as error:
                        code = error.args[0] if len(error.args) == 1 and type(error.args[0]) is str else None
                        fallback(code if code in RENDER_DIAGNOSTIC_CODES else 'qq_render_unavailable')
                        return error if str(error) in ('qq_image_size_limit','qq_image_pixel_limit') else None
                    except asyncio.TimeoutError:
                        fallback('qq_render_timeout')
                        return None
                    except Exception:
                        fallback('qq_render_exception')
                        return None
            finally:
                self.pending -= 1
        task = asyncio.create_task(work())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=max(0, expires - time.monotonic()))
        except asyncio.TimeoutError:
            fallback('qq_render_deadline')
            return None

    def prewarm(self, *, timeout=20):
        """Start the browser in the background so the first reply skips the cold start.

        Runs through the queue lock (never beside a render) and only logs a fixed code;
        a renderer without prewarm(), or one that is disabled, does nothing.
        """
        if not hasattr(self.renderer, 'prewarm'):
            return None
        async def work():
            started = time.monotonic()
            try:
                async with self.lock:
                    ready = await asyncio.wait_for(self.renderer.prewarm(), timeout)
                if ready:
                    logger.info('QQ render prewarm: ready ms=%d', elapsed_ms(started))
            except RenderingUnavailable as error:
                code = error.args[0] if len(error.args) == 1 and type(error.args[0]) is str else None
                logger.warning('QQ render prewarm failed: %s', code if code in RENDER_DIAGNOSTIC_CODES else 'qq_render_unavailable')
            except asyncio.TimeoutError:
                logger.warning('QQ render prewarm failed: qq_render_timeout')
            except Exception:
                logger.warning('QQ render prewarm failed: qq_render_exception')
        task = self._prewarm = asyncio.create_task(work())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def aclose(self):
        # A start-up warm-up must not hold shutdown for its whole timeout.
        if self._prewarm is not None:
            self._prewarm.cancel()
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        if hasattr(self.renderer, 'aclose'):
            await self.renderer.aclose()
