"""Bounded public icon cache. Renderer getters never use the network or caller paths.

Only anonymous HTTPS images from the frontend's audited official CDN hosts are
accepted. DNS results are vetted then the TLS socket is connected to that exact
IP, with the original CDN hostname used for certificate verification and SNI.
No disk cache, proxies, account headers, redirects, SVG or token URLs are used.
"""
import asyncio
import base64
from collections import OrderedDict
import hashlib
import ipaddress
from itertools import islice
from io import BytesIO
import re
import socket
import ssl
import threading
import time
from urllib.parse import unquote, urlsplit, urlunsplit
import warnings

from PIL import Image, UnidentifiedImageError

from .public_asset_catalog import CATALOG, OWNED_EMBLEMS

ALLOWED_HOSTS = frozenset(('web-static.kurobbs.com', 'prod-alicdn-community.kurobbs.com',
                         'webstatic.tajiduo.com', 'bbs-upload.tajiduo.com'))
ASSET_REF_RE = re.compile(r'qqasset_[0-9a-f]{64}\Z')
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024
MAX_SOURCE_PIXELS = 4_000_000
MAX_ICON_EDGE = 192
MAX_SANITIZED_BYTES = 192 * 192 * 4 + 2048


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


def sanitize_image(raw):
    """Return a small static RGBA PNG, stripping metadata and original encoding."""
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_DOWNLOAD_BYTES:
        raise ValueError('qq_asset_size_limit')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw), formats=('JPEG', 'PNG', 'WEBP')) as source:
                if (source.width <= 0 or source.height <= 0
                        or source.width * source.height > MAX_SOURCE_PIXELS
                        or getattr(source, 'n_frames', 1) != 1):
                    raise ValueError('qq_asset_pixels_or_animation')
                source.load()
                source.thumbnail((MAX_ICON_EDGE, MAX_ICON_EDGE), Image.Resampling.LANCZOS)
                # Fresh image drops EXIF, text chunks, ICC profiles and other metadata.
                result = Image.new('RGBA', source.size)
                result.paste(source.convert('RGBA'))
                output = BytesIO()
                result.save(output, 'PNG')
                png = output.getvalue()
                if len(png) > MAX_SANITIZED_BYTES:
                    raise ValueError('qq_asset_sanitized_size_limit')
                return png
    except (OSError, UnidentifiedImageError, Image.DecompressionBombWarning,
            Image.DecompressionBombError, SyntaxError) as error:
        raise ValueError('qq_asset_invalid_image') from error


async def _read_body(reader, headers):
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
            if len(body) + size > MAX_DOWNLOAD_BYTES:
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
        if not re.fullmatch(r'[0-9]{1,9}', length) or not 0 < int(length) <= MAX_DOWNLOAD_BYTES:
            raise ValueError('qq_asset_size_limit')
        return await reader.readexactly(int(length))
    body = bytearray()
    while True:
        chunk = await reader.read(min(65536, MAX_DOWNLOAD_BYTES + 1 - len(body)))
        if not chunk:
            return bytes(body)
        body.extend(chunk)
        if len(body) > MAX_DOWNLOAD_BYTES:
            raise ValueError('qq_asset_size_limit')


async def _download(value, *, timeout_seconds=3):
    url = safe_public_url(value)
    if not url:
        raise ValueError('qq_asset_invalid_url')
    target = urlsplit(url)
    writer = None
    # timeout spans DNS, TLS, headers and entire body, including slow streaming.
    async with asyncio.timeout(max(.001, min(timeout_seconds, 5))):
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
            if not re.fullmatch(b'HTTP/1[.][01] 200(?: [^\r\n]*)?', lines[0]) or len(lines) > 64:
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
            return await _read_body(reader, headers)
        finally:
            if writer is not None:
                writer.close()


class PublicAssetCache:
    def __init__(self, *, cache_entries=128, cache_bytes=16*1024*1024, cache_ttl=3600,
                 concurrency=6, request_timeout=3):
        self.cache_entries = max(1, min(cache_entries, 256))
        self.cache_bytes = max(1, min(cache_bytes, 32*1024*1024))
        self.cache_ttl = max(.001, min(cache_ttl, 86400))
        self.request_timeout = max(.001, min(request_timeout, 5))
        self._cache = OrderedDict()
        self._sources = OrderedDict()
        self._failures = OrderedDict()
        self._inflight = {}
        self._lock = threading.RLock()
        self._semaphore = asyncio.Semaphore(max(1, min(concurrency, 8)))
        self._bytes = 0
        self._catalog = CATALOG

    def register_url(self, url):
        safe = safe_public_url(url)
        if not safe:
            return None
        ref = 'qqasset_' + hashlib.sha256(safe.encode('ascii')).hexdigest()
        with self._lock:
            if ref not in self._sources and len(self._sources) >= 2048:
                return None
            self._sources[ref] = safe
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
        return self.register_url(entry) if entry else None

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

    def _store(self, ref, png):
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

    def get_image(self, ref):
        png = self.get_png(ref)
        if png is None:
            return None
        with Image.open(BytesIO(png)) as image:
            return image.convert('RGBA')

    def get_png(self, ref):
        """Return immutable, sanitized bytes for one offline render job."""
        if not isinstance(ref, str) or not ASSET_REF_RE.fullmatch(ref):
            return None
        with self._lock:
            self._expire()
            item = self._cache.get(ref)
            if not item:
                return None
            self._cache.move_to_end(ref)
            return item[1]

    def fingerprint(self, ref):
        with self._lock:
            self._expire()
            item = self._cache.get(ref) if isinstance(ref, str) else None
            return item[2] if item else 'missing'

    async def _fetch(self, ref, deadline):
        try:
            async with self._semaphore:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                raw = await _download(self._sources[ref], timeout_seconds=min(remaining, self.request_timeout))
                if time.monotonic() < deadline:
                    self._store(ref, sanitize_image(raw))
        except (ValueError, OSError, TimeoutError, UnicodeError, asyncio.IncompleteReadError,
                asyncio.LimitOverrunError):
            with self._lock:
                self._failures[ref] = time.monotonic() + 30
                while len(self._failures) > 256:
                    self._failures.popitem(last=False)
        finally:
            self._inflight.pop(ref, None)

    async def prefetch(self, refs, *, budget_seconds=1.5):
        """Bounded caller-deadline fetch; all outstanding owned sockets cancel on timeout.

        Input is opaque refs already registered by the safe projection. Cached
        refs consume no sockets; misses are coalesced across concurrent replies.
        Scan at most 512 document refs; cached early rows do not prevent later
        rows being filled on the next reply. No more than 80 tasks or eight
        sockets can exist for this cache.
        """
        if budget_seconds <= 0:
            return
        deadline = time.monotonic() + min(budget_seconds, 5)
        tasks, owned = [], []
        for ref in dict.fromkeys(ref for ref in islice(refs, 512) if isinstance(ref, str)):
            with self._lock:
                self._expire()
                if ref not in self._sources or ref in self._cache or ref in self._failures:
                    continue
            task = self._inflight.get(ref)
            if task is None:
                if len(self._inflight) >= 80:
                    break
                task = asyncio.create_task(self._fetch(ref, deadline))
                self._inflight[ref] = task
                owned.append(task)
            tasks.append(task)
        try:
            if tasks:
                await asyncio.wait(tasks, timeout=max(0, deadline - time.monotonic()))
        finally:
            for task in owned:
                if not task.done():
                    task.cancel()
            if owned:
                await asyncio.gather(*owned, return_exceptions=True)

    async def aclose(self):
        tasks = list(self._inflight.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
