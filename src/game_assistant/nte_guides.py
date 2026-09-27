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

from .nte_guides_catalog import SOURCES

MAX_BYTES = 2 * 1024 * 1024
MAX_AGE = 86400


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
            'url': SOURCES[post_id]['url'], 'paragraphs': paragraphs, 'images': valid_images,
            'published_at': source_time(post.get('createTime')), 'edited_at': source_time(post.get('lastEditTime')),
            'fingerprint': fingerprint}


class GuideService:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.locks = {key: asyncio.Lock() for key in SOURCES}
        self.last_attempt, self.errors = {}, {}
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS guide_posts (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
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
        return {**value, 'stale': age > MAX_AGE or bool(error), 'error': error,
                'summary_changed': value['fingerprint'] != SOURCES[post_id]['fingerprint'], 'refresh_deferred': deferred}

    async def read(self, post_id, force=False):
        if post_id not in SOURCES: raise GuideSourceError('未收录的攻略来源')
        async with self.locks[post_id]:
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
                self.errors.pop(post_id, None)
                return self.present(value, post_id)
            except (httpx.HTTPError, GuideSourceError, ValueError, TypeError, RecursionError):
                self.errors[post_id] = '原帖暂时无法读取；保留上次成功资料，请稍后重试。'
                if cached:
                    cached = {**cached, 'source_error': self.errors[post_id]}
                    self.save(post_id, cached)
                    return self.present(cached, post_id)
                raise GuideSourceError('原帖暂时无法读取，请稍后重试或打开来源链接') from None
