"""Bounded anonymous guide reads with persistent last-good public source snapshots."""
import asyncio
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlsplit

import httpx

from .nte_guides_catalog import ALL_POST, AUTHOR, ROLE_POST, SOURCES, post_url
from .wuwa_guide_updates import error_code

MAX_BYTES = 2 * 1024 * 1024
MAX_AGE = 86400
AUTHOR_MAX_BYTES = 1024 * 1024
AUTHOR_URL = 'https://bbs-api.tajiduo.com/bbs/wapi/getUserPostList'


class GuideSourceError(Exception):
    pass


class TextBlocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'): self.hidden += 1
        if not self.hidden and tag in ('p', 'br', 'li', 'div', 'h1', 'h2', 'h3'): self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in ('p', 'li', 'div', 'h1', 'h2', 'h3'): self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)


def safe_image(value):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value): return None
    try:
        url = urlsplit(value)
        if (url.scheme == 'https' and url.hostname in ('bbs-upload.tajiduo.com', 'webstatic.tajiduo.com')
                and not url.username and not url.password and url.port in (None, 443)):
            return value
    except ValueError:
        pass
    return None


def source_time(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0: return None
    try: return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError): return None


def parse_post(raw, post_id):
    if not isinstance(raw, dict) or raw.get('code') not in (0, 200): raise GuideSourceError('原帖返回异常')
    data = raw.get('data')
    post = data.get('post') if isinstance(data, dict) else None
    if (not isinstance(post, dict) or str(post.get('postId')) != str(post_id)
            or post.get('isDelete') or post.get('deleteTime')): raise GuideSourceError('原帖已不可用')
    title, content, images = post.get('subject'), post.get('content'), post.get('images', [])
    if (not isinstance(title, str) or not title.strip() or not isinstance(content, str)
            or len(content) > 200000 or not isinstance(images, list) or len(images) > 40
            or any(not isinstance(image, dict) for image in images)):
        raise GuideSourceError('原帖格式异常')
    parser = TextBlocks(); parser.feed(content)
    paragraphs = [line.strip() for line in ''.join(parser.parts).splitlines() if line.strip()]
    # Page numbers are source evidence: never shift them by filtering/deduplicating.
    valid_images = [safe_image(item.get('url')) for item in images]
    if not paragraphs and not any(valid_images): raise GuideSourceError('原帖内容为空')
    author = next((u.get('nickname') for u in data.get('users', []) if isinstance(u, dict) and str(u.get('uid')) == str(post.get('uid'))), None)
    digest = {'subject': title, 'content': content, 'images': [item.get('url') for item in images]}
    fingerprint = hashlib.sha256(json.dumps(digest, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'id': post_id, 'title': title, 'author': author if isinstance(author, str) else '作者未提供',
            'url': post_url(post_id), 'paragraphs': paragraphs, 'images': valid_images,
            'published_at': source_time(post.get('createTime')), 'edited_at': source_time(post.get('lastEditTime')),
            'fingerprint': fingerprint}


def parse_author_posts(raw):
    """The author's latest posts: id, title, publish time and image count only."""
    data = raw.get('data') if isinstance(raw, dict) and raw.get('code') in (0, 200) else None
    posts = data.get('posts') if isinstance(data, dict) else None
    if not isinstance(posts, list) or len(posts) > 50 or any(not isinstance(p, dict) for p in posts):
        raise GuideSourceError('作者帖子列表格式异常')
    out = []
    for post in posts:
        post_id, title, images = post.get('postId'), post.get('subject'), post.get('images')
        if (type(post_id) is not int or post_id <= 0 or not isinstance(title, str) or len(title) > 200
                or post.get('isDelete') or post.get('deleteTime')):
            continue
        out.append({'id': post_id, 'title': title.strip(), 'published_at': source_time(post.get('createTime')),
                    'images': len(images) if isinstance(images, list) else 0})
    return out


def new_guide_posts(posts):
    """Guides in the author's list newer than the catalog's: a role post newer than the role's
    catalog source (or for a role without one), and an all-role post newer than the catalog's.
    Post IDs grow with time on this forum, so they order posts without a timestamp."""
    from .nte_guides_catalog import guide_catalog
    names = {name: g for g in guide_catalog()['guides'] for name in [g['name'], *g.get('aliases', [])]}
    newest_all = max((pid for pid, source in SOURCES.items() if ALL_POST.match(source['title'])), default=0)
    found = {}
    for post in posts:
        if post['id'] in SOURCES:
            continue
        base = {**post, 'author': AUTHOR['name'], 'url': post_url(post['id'])}
        if role := ROLE_POST.match(post['title']):
            guide = names.get(role[2])
            if guide is None or post['id'] > guide['source_id']:
                found[post['id']] = {**base, 'version': role[1], 'role': role[2], 'known_role': guide is not None}
        elif (every := ALL_POST.match(post['title'])) and post['id'] > newest_all:
            found[post['id']] = {**base, 'version': every[1], 'role': None, 'known_role': None}
    return sorted(found.values(), key=lambda post: post['id'], reverse=True)


class GuideService:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.locks = {key: asyncio.Lock() for key in SOURCES}
        self.author_lock = asyncio.Lock()
        self.last_attempt, self.errors, self.error_codes = {}, {}, {}
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS guide_posts (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS guide_author_posts (uid INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
            conn.commit()

    def cached(self, post_id):
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute('SELECT payload FROM guide_posts WHERE id=?', (post_id,)).fetchone()
        if not row: return None
        try:
            data = json.loads(row[0])
            if (not isinstance(data, dict) or data.get('id') != post_id or not data.get('fingerprint')
                    or not isinstance(data.get('images'), list) or not isinstance(data.get('paragraphs'), list)
                    or datetime.fromisoformat(data['fetched_at']).tzinfo is None): return None
            return data
        except (ValueError, KeyError, TypeError): return None

    def save(self, post_id, value):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('INSERT INTO guide_posts VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                         (post_id, json.dumps(value, ensure_ascii=False)))
            conn.commit()

    def present(self, value, post_id, deferred=False):
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(value['fetched_at'])).total_seconds()
        error = self.errors.get(post_id) or value.get('source_error')
        # A discovered post has no reviewed summary that could fall behind it.
        changed = post_id in SOURCES and value['fingerprint'] != SOURCES[post_id]['fingerprint']
        return {**value, 'stale': age > MAX_AGE or bool(error), 'error': error,
                'summary_changed': changed, 'refresh_deferred': deferred}

    def author_posts(self):
        """The last author list read, or None; never a request."""
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute('SELECT payload FROM guide_author_posts WHERE uid=?', (AUTHOR['uid'],)).fetchone()
        try:
            value = json.loads(row[0]) if row else None
        except ValueError:
            return None
        return value if isinstance(value, dict) and isinstance(value.get('posts'), list) and value.get('fetched_at') else None

    def new_posts(self):
        value = self.author_posts()
        return new_guide_posts(value['posts']) if value else []

    def known(self, post_id):
        """A catalog source, or a guide post the author list reported as new."""
        return post_id in SOURCES or any(post['id'] == post_id for post in self.new_posts())

    async def read_author(self, force=False):
        """At most one anonymous list request a day; a failure keeps the last list."""
        async with self.author_lock:
            cached = self.author_posts()
            if cached and not force and (datetime.now(timezone.utc) - datetime.fromisoformat(cached['fetched_at'])).total_seconds() < MAX_AGE:
                return cached
            try:
                async with httpx.AsyncClient(timeout=15, follow_redirects=False, headers={'User-Agent': 'Mozilla/5.0'}) as client:
                    async with client.stream('GET', AUTHOR_URL, params={'uid': AUTHOR['uid'], 'count': 20}) as response:
                        response.raise_for_status()
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > AUTHOR_MAX_BYTES: raise GuideSourceError('作者帖子列表过大')
                value = {'fetched_at': datetime.now(timezone.utc).isoformat(), 'posts': parse_author_posts(json.loads(body))}
            except (httpx.HTTPError, GuideSourceError, ValueError, TypeError, RecursionError) as error:
                self.error_codes['author'] = error_code(error)
                raise GuideSourceError('作者帖子列表暂时无法读取') from None
            self.save_author(value)
            self.error_codes.pop('author', None)
            return value

    def save_author(self, value):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('INSERT INTO guide_author_posts VALUES (?,?) ON CONFLICT(uid) DO UPDATE SET payload=excluded.payload',
                         (AUTHOR['uid'], json.dumps(value, ensure_ascii=False)))
            conn.commit()

    def status(self, post_id):
        """Cache-only freshness for the administrator and QQ; None until the post was fetched once."""
        cached = self.cached(post_id) if self.known(post_id) else None
        if not cached: return None
        value = self.present(cached, post_id)
        return {'fetched_at': cached['fetched_at'], 'summary_changed': value['summary_changed'],
                'stale': value['stale'], 'error': bool(value['error'])}

    async def read(self, post_id, force=False):
        if not self.known(post_id): raise GuideSourceError('未收录的攻略来源')
        async with self.locks.setdefault(post_id, asyncio.Lock()):
            cached = self.cached(post_id)
            if cached and not force and not self.present(cached, post_id)['stale']:
                return self.present(cached, post_id)
            now = time.monotonic()
            if now - self.last_attempt.get(post_id, -1000) < 30:
                if cached: return self.present(cached, post_id, deferred=True)
                raise GuideSourceError('原帖暂时无法读取，请稍后重试')
            self.last_attempt[post_id] = now
            try:
                async with httpx.AsyncClient(timeout=15, follow_redirects=False, headers={'User-Agent':'Mozilla/5.0'}) as client:
                    async with client.stream('GET', 'https://bbs-api.tajiduo.com/bbs/wapi/getPostFull', params={'postId':post_id}) as response:
                        response.raise_for_status()
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > MAX_BYTES: raise GuideSourceError('原帖内容过大')
                value = parse_post(json.loads(body), post_id)
                value['fetched_at'] = datetime.now(timezone.utc).isoformat()
                self.save(post_id, value)
                self.errors.pop(post_id, None); self.error_codes.pop(post_id, None)
                return self.present(value, post_id)
            except (httpx.HTTPError, GuideSourceError, ValueError, TypeError, RecursionError) as error:
                self.errors[post_id] = '原帖暂时无法读取；保留上次成功资料，请稍后重试。'
                self.error_codes[post_id] = error_code(error)
                if cached:
                    cached = {**cached, 'source_error': self.errors[post_id], 'error_code': self.error_codes[post_id]}
                    self.save(post_id, cached)
                    return self.present(cached, post_id)
                raise GuideSourceError('原帖暂时无法读取，请稍后重试或打开来源链接') from None
