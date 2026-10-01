"""Anonymous, bounded discovery of guide sources; never rewrites reviewed advice."""
import asyncio
from contextlib import closing
from datetime import datetime, timezone
from html import unescape
import json
from pathlib import Path
import re
import sqlite3
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

SEARCH_URL = 'https://api.kurobbs.com/forum/search/v2/post'
HEADERS = {'source': 'h5', 'version': '3.0.0', 'countryCode': 'CN',
           'devCode': '9asdpjhjklgfhjko90876532134', 'Origin': 'https://www.kurobbs.com',
           'Referer': 'https://www.kurobbs.com/', 'User-Agent': 'Mozilla/5.0'}
MAX_BYTES = 2 * 1024 * 1024


class Search(BaseModel):
    character_id: str = Field(pattern=r'^\d{1,12}$')
    name: str = Field(min_length=1, max_length=30, pattern=r'^[\u4e00-\u9fffA-Za-z·・]+$')
    attribute: str = Field(default='', max_length=10, pattern=r'^[\u4e00-\u9fff]*$')

    @property
    def key(self):
        return json.dumps([self.character_id, self.name, self.attribute], ensure_ascii=False)

    @property
    def keyword(self):
        return (self.attribute if self.name in ('漂泊者', '秧秧') else '') + self.name + '培养攻略'


class Selection(Search):
    post_id: str = Field(pattern=r'^\d{1,22}$')


def plain(value):
    return unescape(re.sub(r'<[^>]*>', '', value)) if isinstance(value, str) else ''


def parse_candidate(post, query):
    if not isinstance(post, dict) or str(post.get('gameId')) != '3':
        return None
    post_id = str(post.get('postId', ''))
    title = plain(post.get('postTitle'))[:300]
    if not re.fullmatch(r'\d{1,22}', post_id) or not title:
        return None
    if re.search(r'前瞻|爆料|材料|剧情|任务|合集|全角色|汇总|抽奖|提问|求助|怎么|如何|吗|[？?]', title):
        return None
    if not re.search(r'攻略|培养|养成|配队|一图流|解析', title):
        return None
    if query.name == '漂泊者':
        aliases = {'气动': ('气动主', '风主'), '湮灭': ('湮灭主', '暗主'),
                   '衍射': ('衍射主', '光主'), '导电': ('导电主', '雷主')}
        if not query.attribute or not (any(n in title for n in aliases.get(query.attribute, ()))
                or ('漂泊者' in title and query.attribute in title)):
            return None
    elif query.name == '秧秧':
        if '秧秧' not in title or '玄翎' in title or '湮灭' in title or '气动' not in title:
            return None
    elif len(query.name) == 1:
        # A one-character role needs a title boundary, not a substring in 鉴心/剑心.
        pattern = r'(?<![\u4e00-\u9fff])' + re.escape(query.name) + r'(?=培养|配队|攻略|养成|详细|全方位|实用|一图流|月狐|[^\u4e00-\u9fff]|$)'
        if not re.search(pattern, title):
            return None
    elif query.name.replace('・', '·') not in title.replace('・', '·'):
        return None
    version = re.search(r'(?<!\d)(\d{1,2}\.\d{1,2})(?!\d)', title)
    published = None
    try:
        stamp = int(post.get('createTimestamp', 0))
        if stamp > 0:
            published = datetime.fromtimestamp(stamp / 1000, timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    return {'id': post_id, 'title': title, 'author': plain(post.get('userName'))[:80] or '作者未提供',
            'author_id': str(post.get('userId', ''))[:30],
            'version': version.group(1) if version else None, 'published_at': published,
            'kind': 'video' if str(post.get('postType')) == '2' else 'article',
            'url': f'https://www.kurobbs.com/forum/post/{post_id}', 'status': 'unreviewed'}


class GuideUpdates:
    def __init__(self, path, auto_extract=True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # One bounded search at a time, with persisted per-role cooldowns.
        self.lock = asyncio.Lock()
        from .wuwa_guide_extract import GuideExtractor
        self.extractor = GuideExtractor(self.path)
        self.auto_extract = auto_extract
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS guide_checks (key TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            conn.commit()

    def cached(self, query):
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute('SELECT payload FROM guide_checks WHERE key=?', (query.key,)).fetchone()
        if row:
            try:
                value = json.loads(row[0])
                if isinstance(value, dict) and isinstance(value.get('candidates'), list):
                    return self.with_guide(query,value)
            except (ValueError, TypeError):
                pass
        return self.with_guide(query,{**query.model_dump(), 'candidates': [], 'checked_at': None,
                'attempted_at': None, 'error': None, 'limited': False})

    def with_guide(self,query,value):
        active = self.extractor.active(query)
        return {**value,'active_guide':active['guide'],'extraction_error':active['error']}

    async def extract(self,query,post_id,force=True):
        candidate = next((p for p in self.cached(query)['candidates'] if p['id']==post_id),None)
        if not candidate: raise HTTPException(404,'请先检查更新，提炼来源必须来自当前角色的检索结果')
        if candidate['kind']=='video': raise HTTPException(422,'视频尚未转写，不能生成培养建议')
        await self.extractor.extract(query,post_id,force=force)
        return self.cached(query)

    def save(self, query, value):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('INSERT INTO guide_checks VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload',
                         (query.key, json.dumps(value, ensure_ascii=False)))
            conn.commit()

    async def check(self, query):
        async with self.lock:
            previous = self.cached(query)
            attempt = previous.get('attempted_at')
            if attempt and time.time() - datetime.fromisoformat(attempt).timestamp() < 30:
                return {**previous, 'deferred': True}
            attempted = datetime.now(timezone.utc).isoformat()
            try:
                candidates, limited = {}, False
                async with asyncio.timeout(35), httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=False) as client:
                    for page in range(1, 3):
                        body = bytearray()
                        async with client.stream('POST', SEARCH_URL, data={'gameId': 3, 'keyword': query.keyword,
                                'pageIndex': page, 'pageSize': 20, 'searchType': 1, 'forumType': 1}) as response:
                            response.raise_for_status()
                            async for chunk in response.aiter_bytes():
                                body.extend(chunk)
                                if len(body) > MAX_BYTES:
                                    raise ValueError('oversize')
                        raw = json.loads(body)
                        data = raw.get('data') if isinstance(raw, dict) and raw.get('code') == 200 else None
                        if not isinstance(data, dict) or not isinstance(data.get('postList'), list) or not isinstance(data.get('hasNext'), bool):
                            raise ValueError('invalid search response')
                        if len(data['postList']) > 20 or any(not isinstance(p, dict) for p in data['postList']):
                            raise ValueError('invalid posts')
                        for post in data['postList']:
                            item = parse_candidate(post, query)
                            if item:
                                candidates[item['id']] = item
                        limited = data['hasNext']
                        if not limited:
                            break
                value = {**query.model_dump(), 'candidates': sorted(candidates.values(), key=lambda p: p['published_at'] or '', reverse=True),
                         'checked_at': datetime.now(timezone.utc).isoformat(), 'attempted_at': attempted,
                         'error': None, 'limited': limited}
            except (httpx.HTTPError, ValueError, TypeError, TimeoutError):
                value = {**previous, 'attempted_at': attempted, 'error': '社区搜索暂时不可用，保留上次结果，请稍后重试。'}
            self.save(query, value)
            if not value.get('error') and self.auto_extract:
                articles = [p for p in value['candidates'] if p['kind']=='article']
                if articles:
                    # Prefer the established guide author, then the newest matching article.
                    preferred = next((p for p in articles if p['author_id']=='10525366'),articles[0])
                    await self.extractor.extract(query,preferred['id'],force=True)
            return self.with_guide(query,value)


def install_wuwa_guide_updates(app, settings):
    service = GuideUpdates(Path(settings.db_path).with_suffix('.wuwa-guides.sqlite3'))
    app.state.wuwa_guide_updates = service
    router = APIRouter(prefix='/api/wuwa/guides/updates')

    @router.get('')
    async def cached(query: Search = Depends()):
        return service.cached(query)

    @router.post('')
    async def check(query: Search):
        return await service.check(query)

    @router.post('/extract')
    async def extract(selection: Selection):
        query = Search(**selection.model_dump(exclude={'post_id'}))
        return await service.extract(query,selection.post_id)

    app.include_router(router)
