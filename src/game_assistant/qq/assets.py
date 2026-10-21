"""Bounded public icon cache. Renderer getters never use the network or caller paths.

Only anonymous HTTPS images from the frontend's audited official CDN hosts are
accepted. DNS results are vetted then the TLS socket is connected to that exact
IP, with the original CDN hostname used for certificate verification and SNI.
An optional bounded disk tier retains sanitized public PNGs only, with opaque
content-mode keys. No proxies, account headers, redirects, SVG or token URLs are used.
System DNS is the default; operators may explicitly select a fixed trusted DoH
resolver for public-image hosts without changing machine-wide DNS settings.
"""
import asyncio
import base64
from collections import OrderedDict
from contextlib import contextmanager
import hashlib
import ipaddress
from itertools import islice
from io import BytesIO
import logging
import re
import socket
import ssl
import threading
import time
from urllib.parse import unquote, urlsplit, urlunsplit
import warnings

from PIL import Image, UnidentifiedImageError

from .public_asset_catalog import CATALOG, OWNED_EMBLEMS

logger = logging.getLogger(__name__)

ALLOWED_HOSTS = frozenset(('web-static.kurobbs.com', 'prod-alicdn-community.kurobbs.com',
                         'webstatic.tajiduo.com', 'bbs-upload.tajiduo.com',
                         'web.hycdn.cn', 'bbs.hycdn.cn'))
ASSET_REF_RE = re.compile(r'qqasset_[0-9a-f]{64}\Z')
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024
MAX_SOURCE_PIXELS = 4_000_000
MAX_ARTWORK_DOWNLOAD_BYTES = 6 * 1024 * 1024
MAX_ARTWORK_SOURCE_PIXELS = 12_000_000
MAX_ICON_EDGE = 192
MAX_SANITIZED_BYTES = 192 * 192 * 4 + 2048
MAX_PORTRAIT_EDGE = 512
MAX_PORTRAIT_BYTES = 512 * 512 * 4 + 4096
MAX_ARTWORK_EDGE = 1080
MAX_ARTWORK_BYTES = MAX_ARTWORK_EDGE * MAX_ARTWORK_EDGE * 4 + 4096
# A missing or invalid public image stays so; a network failure may clear up soon.
FAILURE_SECONDS = 30
DETERMINISTIC_FAILURE_SECONDS = 600
DETERMINISTIC_FAILURES = frozenset(('qq_asset_http_not_found', 'qq_asset_content_type', 'qq_asset_invalid_image',
                                    'qq_asset_pixels_or_animation', 'qq_asset_size_limit', 'qq_asset_sanitized_size_limit'))


def safe_public_url(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 1024 or not value.isascii():
        return None
    if any(ord(c) <= 32 or ord(c) >= 127 for c in value) or '\\' in value:
        return None
    try:
        url = urlsplit(value)
        decoded = unquote(url.path)
        if (url.scheme != 'https' or url.hostname not in ALLOWED_HOSTS or url.username
                or url.password or url.query or url.fragment or '?' in value or '#' in value
                or url.port not in (None, 443) or not url.path.startswith('/')
                or not re.search(r'\.(?:png|jpe?g|webp)\Z', url.path, re.I)
                or any(ord(c) <= 32 or ord(c) >= 127 for c in decoded)
                or '\\' in decoded or '%' in decoded
                or any(part in ('.', '..') for part in decoded.split('/'))):
            return None
        return urlunsplit(('https', url.hostname, url.path, '', ''))
    except (ValueError, UnicodeError):
        return None


def sanitize_image(raw, *, portrait=False, artwork=False):
    """Return a small static RGBA PNG, stripping metadata and original encoding."""
    if portrait and artwork:raise ValueError('qq_asset_conflicting_modes')
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= (MAX_ARTWORK_DOWNLOAD_BYTES if artwork else MAX_DOWNLOAD_BYTES):
        raise ValueError('qq_asset_size_limit')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw), formats=('JPEG', 'PNG', 'WEBP')) as source:
                if (source.width <= 0 or source.height <= 0
                        or source.width * source.height > (MAX_ARTWORK_SOURCE_PIXELS if artwork else MAX_SOURCE_PIXELS)
                        or getattr(source, 'n_frames', 1) != 1):
                    raise ValueError('qq_asset_pixels_or_animation')
                source.load()
                edge = MAX_ARTWORK_EDGE if artwork else MAX_PORTRAIT_EDGE if portrait else MAX_ICON_EDGE
                source.thumbnail((edge, edge), Image.Resampling.LANCZOS)
                # Fresh image drops EXIF, text chunks, ICC profiles and other metadata.
                result = Image.new('RGBA', source.size)
                result.paste(source.convert('RGBA'))
                output = BytesIO()
                result.save(output, 'PNG')
                png = output.getvalue()
                if len(png) > (MAX_ARTWORK_BYTES if artwork else MAX_PORTRAIT_BYTES if portrait else MAX_SANITIZED_BYTES):
                    raise ValueError('qq_asset_sanitized_size_limit')
                return png
    except (OSError, UnidentifiedImageError, Image.DecompressionBombWarning,
            Image.DecompressionBombError, SyntaxError) as error:
        raise ValueError('qq_asset_invalid_image') from error


async def _read_body(reader, headers, *, artwork=False):
    max_bytes = MAX_ARTWORK_DOWNLOAD_BYTES if artwork else MAX_DOWNLOAD_BYTES
    encoding = headers.get('content-encoding', 'identity').lower()
    if encoding not in ('', 'identity'):
        raise ValueError('qq_asset_content_encoding')
    transfer = headers.get('transfer-encoding', '').lower()
    length = headers.get('content-length')
    if transfer:
        if transfer != 'chunked' or length is not None:
            raise ValueError('qq_asset_transfer_encoding')
        body = bytearray()
        for _ in range(2048):
            line = await reader.readline()
            if not line.endswith(b'\r\n') or len(line) > 128:
                raise ValueError('qq_asset_chunk_header')
            # Extensions/trailers are unnecessary for static public icons.
            size_text = line[:-2]
            if not re.fullmatch(b'[0-9a-fA-F]{1,8}', size_text):
                raise ValueError('qq_asset_chunk_header')
            size = int(size_text, 16)
            if len(body) + size > max_bytes:
                raise ValueError('qq_asset_size_limit')
            if not size:
                if await reader.readexactly(2) != b'\r\n':
                    raise ValueError('qq_asset_chunk_trailer')
                return bytes(body)
            body.extend(await reader.readexactly(size))
            if await reader.readexactly(2) != b'\r\n':
                raise ValueError('qq_asset_chunk_end')
        raise ValueError('qq_asset_too_many_chunks')
    if length is not None:
        if not re.fullmatch(r'[0-9]{1,9}', length) or not 0 < int(length) <= max_bytes:
            raise ValueError('qq_asset_size_limit')
        return await reader.readexactly(int(length))
    body = bytearray()
    while True:
        chunk = await reader.read(min(65536, max_bytes + 1 - len(body)))
        if not chunk:
            return bytes(body)
        body.extend(chunk)
        if len(body) > max_bytes:
            raise ValueError('qq_asset_size_limit')


async def _download(value, *, timeout_seconds=3, dns_resolver='system', artwork=False):
    url = safe_public_url(value)
    if not url:
        raise ValueError('qq_asset_invalid_url')
    if dns_resolver not in ('system', 'cloudflare'):
        raise ValueError('qq_asset_dns_resolver_invalid')
    target = urlsplit(url)
    writer = None
    # timeout spans DNS, TLS, headers and entire body, including slow streaming.
    async with asyncio.timeout(max(.001, min(timeout_seconds, 5))):
        if dns_resolver == 'cloudflare':
            from .public_asset_dns import cloudflare_addresses
            addresses = await cloudflare_addresses(target.hostname, allowed_hosts=ALLOWED_HOSTS)
        else:
            addresses = await asyncio.get_running_loop().getaddrinfo(
                target.hostname, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        if not addresses or len(addresses) > 32:
            raise ValueError('qq_asset_dns_invalid')
        pinned = []
        for family, _, _, _, address in addresses:
            if family not in (socket.AF_INET, socket.AF_INET6):
                raise ValueError('qq_asset_dns_invalid')
            ip = ipaddress.ip_address(address[0])
            # IPv4-mapped IPv6 can hide a private endpoint; vet its underlying IP.
            if (not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_loopback
                    or ip.is_link_local or (getattr(ip, 'ipv4_mapped', None) is not None
                                    and not ip.ipv4_mapped.is_global)):
                raise ValueError('qq_asset_dns_private')
            if (family, str(ip)) not in pinned:
                pinned.append((family, str(ip)))
        context = ssl.create_default_context()
        try:
            family, ip = pinned[0]
            reader, writer = await asyncio.open_connection(ip, 443, family=family,
                ssl=context, server_hostname=target.hostname, limit=16384)
            request = (f'GET {target.path} HTTP/1.1\r\nHost: {target.hostname}\r\n'
                       'User-Agent: game-manage-public-icons/1\r\n'
                       'Accept: image/png,image/jpeg,image/webp\r\n'
                       'Accept-Encoding: identity\r\nConnection: close\r\n\r\n')
            writer.write(request.encode('ascii'))
            await writer.drain()
            header = await reader.readuntil(b'\r\n\r\n')
            if len(header) > 16384:
                raise ValueError('qq_asset_headers_limit')
            lines = header[:-4].split(b'\r\n')
            status = re.fullmatch(b'HTTP/1[.][01] ([0-9]{3})(?: [^\r\n]*)?', lines[0])
            if status and status[1] in (b'404', b'410'):
                raise ValueError('qq_asset_http_not_found')
            if not status or status[1] != b'200' or len(lines) > 64:
                raise ValueError('qq_asset_http_status')
            headers = {}
            for line in lines[1:]:
                key, separator, val = line.partition(b':')
                if (not separator or not re.fullmatch(b'[A-Za-z0-9-]{1,64}', key)
                        or len(line) > 2048):
                    raise ValueError('qq_asset_headers_invalid')
                key, val = key.decode('ascii').lower(), val.decode('ascii').strip()
                if key in headers:
                    raise ValueError('qq_asset_duplicate_header')
                headers[key] = val
            if headers.get('content-type', '').split(';')[0].strip().lower() not in (
                    'image/png', 'image/jpeg', 'image/webp'):
                raise ValueError('qq_asset_content_type')
            return await _read_body(reader, headers, artwork=artwork)
        finally:
            if writer is not None:
                writer.close()


class PublicAssetCache:
    def __init__(self, *, cache_entries=128, cache_bytes=16*1024*1024, cache_ttl=3600,
                 concurrency=6, request_timeout=3, artwork_request_timeout=5, dns_resolver='system', prefetch_tasks=80, disk_directory=None):
        if dns_resolver not in ('system', 'cloudflare'):
            raise ValueError('qq_asset_dns_resolver_invalid')
        self.dns_resolver = dns_resolver
        self.cache_entries = max(1, min(cache_entries, 256))
        self.cache_bytes = max(1, min(cache_bytes, 32*1024*1024))
        self.cache_ttl = max(.001, min(cache_ttl, 86400))
        self.request_timeout = max(.001, min(request_timeout, 5))
        self.artwork_request_timeout = max(.001, min(artwork_request_timeout, 5))
        self._cache = OrderedDict()
        self._sources = OrderedDict()
        self._failures = OrderedDict()
        self._inflight = {}
        self._lock = threading.RLock()
        self._semaphore = asyncio.Semaphore(max(1, min(concurrency, 8)))
        self._bytes = 0
        self.prefetch_tasks=max(1,min(int(prefetch_tasks),256))
        # Downloads a reply stopped waiting for are fetched again later, one at a time and
        # only while no image is being rendered: they must not take CPU from Chromium.
        self._deferred=OrderedDict()
        self._drainer=None
        self._renders=0
        self._idle=asyncio.Event()
        self._idle.set()
        self._catalog = CATALOG
        self._portrait_sources = frozenset(CATALOG['games'].get('endfield', {}).get('portrait', {}).values())
        self._portrait_refs = set()
        self._artwork_refs = set()
        self._disk=None
        if disk_directory is not None:
            from .public_png_cache import PublicPngCache
            try:self._disk=PublicPngCache(disk_directory)
            except OSError:pass

    def register_url(self, url, *, portrait=False, artwork=False):
        safe = safe_public_url(url)
        if not safe or portrait and artwork or (portrait and safe not in self._portrait_sources):
            return None
        ref = 'qqasset_' + hashlib.sha256((('artwork-v1:' if artwork else 'portrait-v1:' if portrait else '') + safe).encode('ascii')).hexdigest()
        with self._lock:
            if ref in self._sources:
                self._sources.move_to_end(ref)
            elif len(self._sources) >= 2048:
                # Only a download reads the source URL; a cached PNG is served by ref.
                victim = next((old for old in self._sources if old not in self._inflight), None)
                if victim is None:
                    return None
                del self._sources[victim]
                self._portrait_refs.discard(victim)
                self._artwork_refs.discard(victim)
            self._sources[ref] = safe
            if portrait:
                self._portrait_refs.add(ref)
            if artwork:
                self._artwork_refs.add(ref)
        return ref

    def ref_for(self, game, kind, id_or_name):
        if kind == 'game':
            if game not in ('wuthering_waves', 'nte', 'endfield', 'all'):
                return None
            ref = 'qqasset_' + hashlib.sha256(('game-manage-owned-emblem-v1:' + game).encode()).hexdigest()
            if self.get_image(ref) is None:
                self._store(ref, base64.b64decode(OWNED_EMBLEMS[game]))
            return ref
        bucket = self._catalog['games'].get(game, {}).get(kind, {})
        entry = bucket.get(str(id_or_name))
        return self.register_url(entry, portrait=kind == 'portrait') if entry else None

    def skill_ref(self, game, role_id, skill_name):
        return self.ref_for(game, 'skill', str(role_id) + '::' + str(skill_name))

    def _expire(self):
        now = time.monotonic()
        for ref, (expiry, png, _) in list(self._cache.items()):
            if expiry <= now:
                del self._cache[ref]
                self._bytes -= len(png)
        for ref, expiry in list(self._failures.items()):
            if expiry <= now:
                del self._failures[ref]

    def _store(self, ref, png, *, persist=True):
        with self._lock:
            self._expire()
            if ref in self._cache:
                self._bytes -= len(self._cache.pop(ref)[1])
            if len(png) > self.cache_bytes:
                return
            self._cache[ref] = (time.monotonic() + self.cache_ttl, png, hashlib.sha256(png).hexdigest())
            self._bytes += len(png)
            while len(self._cache) > self.cache_entries or self._bytes > self.cache_bytes:
                _, (_, expired, _) = self._cache.popitem(last=False)
                self._bytes -= len(expired)
        if persist and self._disk is not None:self._disk.write(ref,png)

    def get_png(self, ref):
        """The stored PNG bytes, already sanitized when they were fetched."""
        if not isinstance(ref, str) or not ASSET_REF_RE.fullmatch(ref):
            return None
        with self._lock:
            self._expire()
            item = self._cache.get(ref)
            if item is None and self._disk is not None:
                png=self._disk.read(ref)
                if png is not None:
                    self._store(ref,png,persist=False);item=self._cache.get(ref)
            if not item:
                return None
            self._cache.move_to_end(ref)
            return item[1]

    def get_url_png(self, url, *, artwork=False, portrait=False):
        """Read an already sanitized mode-specific image; never start a fetch."""
        safe=safe_public_url(url)
        if not safe or artwork and portrait:return None
        prefix='artwork-v1:' if artwork else 'portrait-v1:' if portrait else ''
        return self.get_png('qqasset_'+hashlib.sha256((prefix+safe).encode('ascii')).hexdigest())

    def url_fingerprint(self, url, *, artwork=False, portrait=False):
        safe=safe_public_url(url)
        if not safe or artwork and portrait:return 'missing'
        prefix='artwork-v1:' if artwork else 'portrait-v1:' if portrait else ''
        return self.fingerprint('qqasset_'+hashlib.sha256((prefix+safe).encode('ascii')).hexdigest())

    def get_image(self, ref):
        png = self.get_png(ref)
        if png is None:
            return None
        with Image.open(BytesIO(png)) as image:
            return image.convert('RGBA')

    def fingerprint(self, ref):
        with self._lock:
            self._expire()
            item = self._cache.get(ref) if isinstance(ref, str) else None
            return item[2] if item else 'missing'

    @contextmanager
    def rendering(self):
        """Held by the render queue around each render; deferred downloads wait for it."""
        self._renders += 1
        self._idle.clear()
        try:
            yield
        finally:
            self._renders -= 1
            if not self._renders:
                self._idle.set()

    async def _fetch(self, ref, deadline, *, deferred=False):
        """One bounded download; returns a status code for the caller's counts."""
        try:
            async with self._semaphore:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return 'expired'
                options = {'dns_resolver': self.dns_resolver} if self.dns_resolver != 'system' else {}
                if ref in self._artwork_refs:options['artwork']=True
                request_timeout=self.artwork_request_timeout if ref in self._artwork_refs else self.request_timeout
                raw = await _download(self._sources[ref], timeout_seconds=min(remaining, request_timeout), **options)
                if deferred:
                    await self._idle.wait()
                # Decoding and resizing a large picture must not stall the event loop.
                png = await asyncio.to_thread(sanitize_image, raw, portrait=ref in self._portrait_refs, artwork=ref in self._artwork_refs)
                self._store(ref, png)
                return 'ok'
        except (ValueError, OSError, TimeoutError, UnicodeError, asyncio.IncompleteReadError,
                asyncio.LimitOverrunError) as error:
            code = error.args[0] if isinstance(error, ValueError) and error.args else None
            with self._lock:
                self._failures[ref] = time.monotonic() + (DETERMINISTIC_FAILURE_SECONDS if code in DETERMINISTIC_FAILURES else FAILURE_SECONDS)
                while len(self._failures) > 256:
                    self._failures.popitem(last=False)
            return 'failed'
        except Exception:
            # Unexpected: not remembered as a failure, so the next reply retries it.
            return 'error'
        finally:
            self._inflight.pop(ref, None)

    async def _drain(self):
        """Fetch deferred refs serially, each started only when no render is in progress."""
        try:
            while self._deferred:
                await self._idle.wait()
                ref, _ = self._deferred.popitem(last=False)
                with self._lock:
                    self._expire()
                    if ref not in self._sources or ref in self._failures or ref in self._inflight or self.get_png(ref) is not None:
                        continue
                task = asyncio.create_task(self._fetch(ref, time.monotonic() + self.artwork_request_timeout, deferred=True))
                self._inflight[ref] = task
                if await task == 'error':
                    logger.warning('qq_asset_prefetch_failed')
        finally:
            self._drainer = None

    async def prefetch(self, refs, *, budget_seconds=1.5):
        """Wait up to the caller's budget; downloads still running then are deferred.

        Input is opaque refs already registered by the safe projection. Cached
        refs consume no sockets; misses are coalesced across concurrent replies.
        Scan at most 512 document refs; cached early rows do not prevent later
        rows being filled on the next reply. At most prefetch_tasks (default
        80, hard bound 256) tasks and eight sockets can exist for this cache.
        Downloads this call started and that are unfinished at the budget are
        cancelled (no network or decoding beside the render) and queued for a
        serial refetch while no render runs, so the next reply finds them.
        Returns counts only: hit (cached), miss (downloads waited for), failed
        (failed now, or a remembered failure) and timeout (deferred or still
        downloading for another reply).
        """
        stats = {'hit': 0, 'miss': 0, 'failed': 0, 'timeout': 0}
        if budget_seconds <= 0:
            return stats
        now = time.monotonic()
        deadline = now + min(budget_seconds, 5)
        tasks, created = [], {}
        for ref in dict.fromkeys(ref for ref in islice(refs, 512) if isinstance(ref, str)):
            with self._lock:
                self._expire()
                if ref not in self._sources:
                    continue
                if self.get_png(ref) is not None:
                    stats['hit'] += 1;continue
                if ref in self._failures:
                    stats['failed'] += 1;continue
            task = self._inflight.get(ref)
            if task is None:
                if len(self._inflight) >= self.prefetch_tasks:
                    break
                task = asyncio.create_task(self._fetch(ref, deadline))
                created[task] = ref
                self._inflight[ref] = task
            tasks.append(task)
        stats['miss'] = len(tasks)
        if not tasks:
            return stats
        done, pending = await asyncio.wait(tasks, timeout=max(0, deadline - time.monotonic()))
        # Another reply's downloads are left to it; this call's own are refetched later.
        stopped = [task for task in pending if task in created]
        for task in stopped:
            task.cancel()
        await asyncio.gather(*stopped, return_exceptions=True)
        for task in stopped:
            self._deferred[created[task]] = None
            self._deferred.move_to_end(created[task])
        while len(self._deferred) > 512:
            self._deferred.popitem(last=False)
        if self._deferred and self._drainer is None:
            self._drainer = asyncio.create_task(self._drain())
        results = ['cancelled' if task.cancelled() else task.result() for task in done]
        stats['failed'] += sum(result != 'ok' for result in results)
        stats['timeout'] = len(pending)
        if 'error' in results:
            logger.warning('qq_asset_prefetch_failed')
        return stats

    async def aclose(self):
        self._deferred.clear()
        tasks = list(self._inflight.values()) + ([self._drainer] if self._drainer is not None else [])
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._drainer = None
