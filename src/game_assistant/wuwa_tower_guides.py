"""Anonymous discovery of per-period 逆境深塔 lineup posts; reviewed static entries stay authoritative."""
import asyncio
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import re
import sqlite3
import time

import httpx
from fastapi import APIRouter

from .wuwa_guide_extract import POST_URL, SourceError, safe_image
from .wuwa_guide_updates import HEADERS, MAX_BYTES, SEARCH_URL, plain

logger = logging.getLogger(__name__)
KEYWORD = '逆境深塔推荐阵容'
TITLE_RE = re.compile(r'逆境深塔\s*(\d{2})(\d{2})(\d{2})\s*期')
# Authors whose per-period lineup posts were reviewed as reliable; others are kept only as a fallback.
PREFERRED_AUTHORS = ('10525366',)
PERIOD = timedelta(days=28)
CN = timezone(timedelta(hours=8))
KEEP_PERIODS = 3
MAX_IMAGES = 12
COOLDOWN = 30
# Read-triggered checks: retry sooner while the current period has no guide.
MISSING_INTERVAL, FRESH_INTERVAL = 6 * 3600, 24 * 3600


def parse_post(post, now):
    """A search hit becomes a candidate only if it names a plausible, already-started tower period."""
    if not isinstance(post, dict) or str(post.get('gameId')) != '3' or str(post.get('postType')) != '1':
        return None
    post_id, title = str(post.get('postId', '')), plain(post.get('postTitle'))[:300]
    match = TITLE_RE.search(title)
    if not re.fullmatch(r'\d{1,22}', post_id) or not match:
        return None
    try:
        start = datetime(2000 + int(match[1]), int(match[2]), int(match[3]), 4, tzinfo=CN)
    except ValueError:
        return None
    # Periods reset on Monday 04:00; skip future periods and anything older than the kept window.
    if start.weekday() != 0 or start > now + timedelta(days=1) or start < now - PERIOD * KEEP_PERIODS:
        return None
    published = None
    try:
        stamp = int(post.get('createTimestamp', 0))
        if stamp > 0:
            published = datetime.fromtimestamp(stamp / 1000, CN).strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    author_id = str(post.get('userId', ''))[:30]
    return {'id': post_id, 'title': title, 'author': plain(post.get('userName'))[:80] or '作者未提供',
            'author_id': author_id, 'preferred': author_id in PREFERRED_AUTHORS, 'publishedAt': published,
            'periodStart': start.isoformat(), 'periodEnd': (start + PERIOD).isoformat(),
            'scope': f'{start:%Y-%m-%d} 期深境区', 'url': f'https://www.kurobbs.com/forum/post/{post_id}'}


def parse_detail(raw, candidate):
    data = raw.get('data') if isinstance(raw, dict) and raw.get('code') == 200 else None
    detail = data.get('postDetail') if isinstance(data, dict) else None
    if (not isinstance(detail, dict) or str(detail.get('id', detail.get('postId'))) != candidate['id']
            or detail.get('isHide') or detail.get('isDown') or detail.get('isDelete')
            or str(detail.get('postUserId', '')) != candidate['author_id']):
        raise SourceError('原帖已不可用或身份不匹配')
    blocks = detail.get('postContent')
    if not isinstance(blocks, list) or len(blocks) > 300 or any(not isinstance(b, dict) for b in blocks):
        raise SourceError('原帖正文格式异常')
    images, summary = [], ''
    for block in blocks:
        if block.get('contentType') == 2 and (url := safe_image(block.get('url'))) and url not in images:
            images.append(url)
        elif block.get('contentType') == 1 and not summary:
            text = plain(block.get('content')).strip()
            if len(text) >= 8 and not re.search(r'UID|账号|关注|点赞|转发', text, re.I):
                summary = text[:120]
    if not images:
        raise SourceError('原帖没有可用的阵容图')
    topics = ' '.join(plain(t.get('topicName')) for t in detail.get('topicList') or [] if isinstance(t, dict))
    version = re.search(r'(?<![\d.])(\d{1,2}\.\d{1,2})版本', topics + ' ' + candidate['title'])
    return {**candidate, 'lineupImages': images[:MAX_IMAGES], 'modes': ['tower'], 'boss': None,
            'version': version.group(1) if version else None, 'format': '图文攻略', 'status': 'unreviewed',
            'summary': (summary + ' ' if summary else '') + '（自动收录，未人工校对）'}


class TowerGuides:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock, self.lock, self.task = clock, asyncio.Lock(), None
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS tower_guides (key TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            conn.commit()

    def cached(self):
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute("SELECT payload FROM tower_guides WHERE key='state'").fetchone()
        if row:
            try:
                value = json.loads(row[0])
                if isinstance(value, dict) and isinstance(value.get('guides'), list):
                    return value
            except ValueError:
                pass
        return {'guides': [], 'checked_at': None, 'attempted_at': None, 'error': None}

    def save(self, value):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("INSERT INTO tower_guides VALUES ('state', ?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",
                         (json.dumps(value, ensure_ascii=False),))
            conn.commit()

    def due(self, value=None):
        value = value or self.cached()
        if not value.get('attempted_at'):
            return True
        now = self.clock()
        age = now - datetime.fromisoformat(value['attempted_at']).timestamp()
        current = any(datetime.fromisoformat(g['periodStart']).timestamp() <= now
                      < datetime.fromisoformat(g['periodEnd']).timestamp() for g in value['guides'])
        return age >= (FRESH_INTERVAL if current else MISSING_INTERVAL)

    def read(self):
        """Return the cache at once; a due read starts one background check."""
        value = self.cached()
        if self.due(value) and not self.lock.locked() and (self.task is None or self.task.done()):
            self.task = asyncio.get_running_loop().create_task(self.background())
        return value

    async def background(self):
        try:
            await self.check()
        except Exception:
            logger.warning('Wuwa tower guide check failed')

    async def check(self):
        async with self.lock:
            previous = self.cached()
            attempt = previous.get('attempted_at')
            if attempt and self.clock() - datetime.fromisoformat(attempt).timestamp() < COOLDOWN:
                return {**previous, 'deferred': True}
            now = datetime.fromtimestamp(self.clock(), timezone.utc)
            attempted = now.isoformat()
            try:
                async with asyncio.timeout(40), httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=False) as client:
                    periods = {}
                    for page in range(1, 3):
                        raw = json.loads(await self.read_bytes(client, 'POST', SEARCH_URL, data={'gameId': 3,
                            'keyword': KEYWORD, 'pageIndex': page, 'pageSize': 20, 'searchType': 1, 'forumType': 1}))
                        data = raw.get('data') if isinstance(raw, dict) and raw.get('code') == 200 else None
                        if not isinstance(data, dict) or not isinstance(data.get('postList'), list) or len(data['postList']) > 20:
                            raise ValueError('invalid search response')
                        for post in data['postList']:
                            if item := parse_post(post, now):
                                # One post per period: a preferred author wins, then the earliest post.
                                best = periods.get(item['periodStart'])
                                if not best or (item['preferred'], best['publishedAt'] or '') > (best['preferred'], item['publishedAt'] or ''):
                                    periods[item['periodStart']] = item
                        if not data.get('hasNext'):
                            break
                    # Periods missing from this search, or whose post cannot be read, keep their last good entry.
                    kept = {g['periodStart']: g for g in previous['guides']
                            if datetime.fromisoformat(g['periodStart']) >= now - PERIOD * KEEP_PERIODS}
                    for start in sorted(periods, reverse=True)[:KEEP_PERIODS]:
                        candidate, old = periods[start], kept.get(start, {})
                        if old.get('id') == candidate['id'] or (old.get('preferred') and not candidate['preferred']):
                            continue
                        try:
                            blob = await self.read_bytes(client, 'POST', POST_URL, data={'postId': candidate['id']})
                            kept[start] = parse_detail(json.loads(blob), candidate)
                        except (httpx.HTTPError, SourceError, ValueError, TypeError):
                            pass
                guides = [kept[start] for start in sorted(kept, reverse=True)[:KEEP_PERIODS]]
                value = {'guides': guides, 'checked_at': attempted, 'attempted_at': attempted, 'error': None}
            except (httpx.HTTPError, SourceError, ValueError, TypeError, TimeoutError):
                value = {**previous, 'attempted_at': attempted, 'error': '社区搜索暂时不可用，保留上次结果，请稍后重试。'}
            self.save(value)
            return value

    @staticmethod
    async def read_bytes(client, method, url, **kwargs):
        body = bytearray()
        async with client.stream(method, url, **kwargs) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    raise SourceError('source body too large')
        return bytes(body)


def install_wuwa_tower_guides(app, settings):
    service = TowerGuides(Path(settings.db_path).with_suffix('.wuwa-guides.sqlite3'))
    app.state.wuwa_tower_guides = service
    router = APIRouter(prefix='/api/wuwa/guides/tower')

    @router.get('')
    async def cached():
        return service.read()

    @router.post('/check')
    async def check():
        return await service.check()

    app.include_router(router)
