"""Read-only, source-backed Endfield public information.

The official news page exposes Next.js flight data. The official Skland map
uses the same anonymous endpoints as its browser client. No account material
is sent or stored here.
"""
import asyncio
import json
import re
import sqlite3
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import httpx

from .sources.endfield_notice import calendar_from_posts

NEWS_URL = 'https://endfield.hypergryph.com/news'
MAP_URL = 'https://game.skland.com/map/endfield'
WIKI_URL = 'https://wiki.skland.com/endfield'
MAP_API = 'https://zonai.skland.com/web/v1/game/endfield/map/'
FLIGHT = re.compile(r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)')
NEWS_ID = re.compile(r'^\d{1,12}$')
SAFE_ID = re.compile(r'^[\w-]{1,80}$')


class PublicSourceError(Exception):
    """Safe message for a failed public source."""


class _Article(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines = []
        self.current = []

    def handle_starttag(self, tag, attrs):
        if tag == 'br':
            self._line()

    def handle_endtag(self, tag):
        if tag in {'p', 'h1', 'h2', 'h3', 'h4', 'li', 'div'}:
            self._line()

    def handle_data(self, data):
        self.current.append(data)

    def _line(self):
        text = ''.join(self.current).strip()
        if text:
            self.lines.append(text)
        self.current = []

    def text(self):
        self._line()
        return '\n'.join(self.lines)


def _flight(html):
    for raw in FLIGHT.findall(html):
        try:
            yield json.loads(raw)
        except ValueError:
            continue


def _flight_value(html, key):
    needle = json.dumps(key) + ':'
    for chunk in _flight(html):
        start = chunk.find(needle)
        if start >= 0:
            try:
                return json.JSONDecoder().raw_decode(chunk[start + len(needle):])[0]
            except ValueError:
                continue
    raise PublicSourceError('官网资讯格式发生变化')


def _news_list(html):
    values = _flight_value(html, 'bulletins')
    if not isinstance(values, list) or not values:
        raise PublicSourceError('官网资讯列表为空或格式发生变化')
    posts = []
    for value in values:
        if not isinstance(value, dict) or not NEWS_ID.fullmatch(str(value.get('cid', ''))):
            raise PublicSourceError('官网资讯编号格式发生变化')
        if not isinstance(value.get('title'), str) or not isinstance(value.get('displayTime'), int):
            raise PublicSourceError('官网资讯字段格式发生变化')
        cid = str(value['cid'])
        posts.append({'id': cid, 'title': value['title'], 'source': 'official',
                      'source_name': '终末地官网',
                      'published_at': datetime.fromtimestamp(value['displayTime'], timezone.utc).isoformat(),
                      'url': f'{NEWS_URL}/{cid}', 'category': value.get('tab', ''),
                      'summary': str(value.get('brief') or '')[:300]})
    return posts


def _detail(html):
    bulletin = _flight_value(html, 'bulletin')
    if not isinstance(bulletin, dict) or not NEWS_ID.fullmatch(str(bulletin.get('cid', ''))):
        raise PublicSourceError('官网公告格式发生变化')
    # The HTML article is a separate Flight segment; rendered page text has
    # duplicated navigation and is unsuitable for the line-oriented parser.
    candidates = [chunk for chunk in _flight(html) if
                  ('<p>' in chunk or '<h2>' in chunk or '<p ' in chunk)]
    if not candidates:
        raise PublicSourceError('官网公告正文不可读取')
    parser = _Article()
    parser.feed(max(candidates, key=len))
    body = parser.text()
    if len(body) < 30:
        raise PublicSourceError('官网公告正文为空')
    return body


def _checked(data, key):
    if not isinstance(data, dict) or data.get('code') != 0 or not isinstance(data.get('data'), dict):
        raise PublicSourceError('官方地图暂时无法读取')
    value = data['data'].get(key)
    if not isinstance(value, list):
        raise PublicSourceError('官方地图数据格式发生变化')
    return value


class EndfieldPublicService:
    TTL = 4 * 3600

    def __init__(self, db_path):
        path = Path(db_path).with_suffix('.endfield-public.sqlite3')
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute('CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, fetched_at TEXT NOT NULL)')
        self.conn.commit()
        self.lock = asyncio.Lock()

    def close(self):
        self.conn.close()

    def _get(self, key):
        row = self.conn.execute('SELECT value,fetched_at FROM cache WHERE key=?', (key,)).fetchone()
        return (json.loads(row[0]), row[1]) if row else (None, None)

    def _put(self, key, value):
        at = datetime.now(timezone.utc).isoformat()
        self.conn.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)',
                          (key, json.dumps(value, ensure_ascii=False), at))
        self.conn.commit()
        return at

    def _fresh(self, at):
        return bool(at and (datetime.now(timezone.utc) - datetime.fromisoformat(at)).total_seconds() < self.TTL)

    async def _request(self, url, params=None):
        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=True,
                                         headers={'User-Agent': 'Mozilla/5.0',
                                                  'Referer': 'https://game.skland.com/'}) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                if len(response.content) > 3_000_000:
                    raise PublicSourceError('官方页面大小超出预期')
                return response
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise PublicSourceError('官方公开页面暂时无法访问') from exc

    async def _refresh_news(self):
        page = await self._request(NEWS_URL)
        items = _news_list(page.text)
        posts = []
        for item in items:
            if item['category'] != 'notices':
                continue
            detail = await self._request(item['url'])
            body = _detail(detail.text)
            posts.append({**item, 'body': item['title'] + '\n' + body, 'decision': 'accepted',
                          'source': 'official', 'source_name': '终末地官网'})
        if not posts:
            raise PublicSourceError('官网没有可解析的公告')
        calendar = calendar_from_posts(posts)
        if not calendar.get('version'):
            raise PublicSourceError('官网列表中没有可确认的当前版本，保留上次成功数据')
        # A list of ordinary announcements may legitimately have no events,
        # but an identified version announcement must produce some.
        if any('版本更新说明' in p['title'] for p in posts) and not calendar.get('events'):
            raise PublicSourceError('官网公告日历格式发生变化')
        self._put('news', items)
        self._put('calendar', calendar)

    async def public(self, force=False):
        async with self.lock:
            news, news_at = self._get('news')
            cal, cal_at = self._get('calendar')
            state, attempted_at = self._get('news_status')
            error = (state or {}).get('error')
            # A failed explicit refresh must stay visible on the next read, even
            # when the last successful cache entry is still within its TTL.
            retry_due = not attempted_at or (datetime.now(timezone.utc) - datetime.fromisoformat(attempted_at)).total_seconds() >= 60
            if force or (retry_due and (error or not self._fresh(news_at) or not self._fresh(cal_at))):
                try:
                    await self._refresh_news()
                    news, news_at = self._get('news')
                    cal, cal_at = self._get('calendar')
                    error = None
                except PublicSourceError as exc:
                    error = str(exc)
                self._put('news_status', {'error': error})
            return {
                'news': {'items': news or [], 'fetched_at': news_at, 'stale': bool(error), 'error': error},
                'calendar': {'events': (cal or {}).get('events', []),
                             'version': (cal or {}).get('version'), 'fetched_at': cal_at,
                             'stale': bool(error), 'error': error},
                'tools': TOOLS,
            }

    async def news(self, force=False):
        result = await self.public(force=force)
        if result['news']['error']:
            raise PublicSourceError(result['news']['error'])
        return result['news']['items']

    async def events(self, force=False):
        result = await self.public(force=force)
        if result['calendar']['error']:
            raise PublicSourceError(result['calendar']['error'])
        return result['calendar']['events']

    async def _map_json(self, path, params=None):
        response = await self._request(MAP_API + path, params)
        try:
            return response.json()
        except ValueError as exc:
            raise PublicSourceError('官方地图返回格式发生变化') from exc

    async def map_mark_info(self, map_id, mark_id):
        if not SAFE_ID.fullmatch(map_id) or not SAFE_ID.fullmatch(mark_id):
            raise ValueError('点位参数不正确')
        key = f'mark-info:{map_id}:{mark_id}'
        value, at = self._get(key)
        error = None
        if not self._fresh(at):
            try:
                data = await self._map_json('mark/info', {'mapId': map_id, 'markId': mark_id})
                payload = data.get('data') if isinstance(data, dict) else None
                info = payload.get('info') if isinstance(payload, dict) else None
                if not isinstance(data, dict) or data.get('code') != 0 or not isinstance(info, dict) or info.get('id') != mark_id:
                    raise PublicSourceError('官方地图点位详情不可读取')
                value = {field: info.get(field) for field in
                         ('id', 'templateId', 'mapId', 'levelId', 'pos', 'desc',
                          'wikiItemId', 'link', 'linkText', 'typeMain', 'typeSub')}
                at = self._put(key, value)
            except PublicSourceError as exc:
                error = str(exc)
        return {'info': value, 'fetched_at': at, 'stale': bool(error), 'error': error}

    async def map(self, map_id=None, level_id=None, type_id=None, q='', offset=0, limit=100):
        if any(value and not SAFE_ID.fullmatch(value) for value in (map_id, level_id, type_id)):
            raise ValueError('地图筛选参数不正确')
        if len(q) > 80 or not 0 <= offset <= 100_000 or not 1 <= limit <= 200:
            raise ValueError('地图筛选参数不正确')
        async with self.lock:
            stale = False
            error = None
            try:
                tree, tree_error = await self._cache_map('tree', 'tree', 'maps')
                catalog, catalog_error = await self._cache_map('catalog', 'catalog', 'mainTypes')
                error = tree_error or catalog_error
                stale = bool(error)
                maps = [{'id': m['id'], 'name': m['name'],
                         'levels': [{'id': l['id'], 'name': l['name']} for l in m.get('levels', [])]}
                        for m in tree if isinstance(m, dict) and 'id' in m and 'name' in m]
                categories = [{'id': sub['id'], 'name': sub['name'], 'main_id': main['id'],
                               'main_name': main['name']}
                              for main in catalog for sub in main.get('subTypes', [])
                              if isinstance(sub, dict) and 'id' in sub and 'name' in sub]
                if map_id and map_id not in {m['id'] for m in maps}:
                    raise ValueError('地图编号不存在')
                chosen = next((m for m in maps if m['id'] == map_id), None)
                if chosen and not level_id and chosen['levels']:
                    level_id = chosen['levels'][0]['id']
                if level_id and (not chosen or level_id not in {l['id'] for l in chosen['levels']}):
                    raise ValueError('地图层级编号不存在')
                if type_id and type_id not in {c['id'] for c in categories}:
                    raise ValueError('点位类型编号不存在')
                marks = []
                at = self._get('tree')[1]
                if map_id:
                    key = f'marks:{map_id}:{level_id or ""}'
                    raw, at = self._get(key)
                    if not self._fresh(at):
                        try:
                            data = await self._map_json('mark/list', {'mapId': map_id, 'levelId': level_id})
                            updated = {part: _checked(data, part) for part in ('marks', 'markTemplates')}
                            if not updated['markTemplates']:
                                raise PublicSourceError('官方地图点位模板为空')
                            raw = updated
                            at = self._put(key, raw)
                        except PublicSourceError as exc:
                            if raw is None:
                                raise
                            error, stale = str(exc), True
                    templates = {t['id']: t for t in raw['markTemplates'] if isinstance(t, dict) and 'id' in t}
                    # Use the catalog's subtype-to-template mapping.
                    types = {tid: sub for main in catalog for sub in main.get('subTypes', [])
                             for tid in sub.get('templateIds', [])}
                    for mark in raw['marks']:
                        if not isinstance(mark, dict) or mark.get('fromMark') or mark.get('toMark'):
                            continue
                        template = templates.get(mark.get('templateId'), {})
                        subtype = types.get(mark.get('templateId'), {})
                        name = template.get('name') or subtype.get('name')
                        if not name or not isinstance(mark.get('pos'), dict):
                            continue
                        if type_id and subtype.get('id') != type_id:
                            continue
                        if q and q.casefold() not in (name + ' ' + str(template.get('desc') or '')).casefold():
                            continue
                        pos = mark['pos']
                        marks.append({'id': mark.get('id'), 'name': name,
                                      'x': pos.get('x'), 'y': pos.get('y'), 'z': pos.get('z'),
                                      'type_id': subtype.get('id'), 'description': template.get('desc') or '',
                                      'level_id': mark.get('levelId'), 'url': MAP_URL})
                return {'maps': maps, 'categories': categories, 'marks': marks[offset:offset + limit],
                        'total': len(marks), 'offset': offset, 'limit': limit, 'level_id': level_id,
                        'fetched_at': at, 'stale': stale, 'error': error}
            except PublicSourceError as exc:
                error, stale = str(exc), True
                tree, at = self._get('tree')
                catalog, _ = self._get('catalog')
                maps = [{'id': m['id'], 'name': m['name'],
                         'levels': [{'id': l['id'], 'name': l['name']} for l in m.get('levels', [])]}
                        for m in tree or [] if isinstance(m, dict) and 'id' in m and 'name' in m]
                categories = [{'id': sub['id'], 'name': sub['name'], 'main_id': main['id'],
                               'main_name': main['name']} for main in catalog or []
                              for sub in main.get('subTypes', []) if 'id' in sub and 'name' in sub]
                # Never label cached point data as fresh after a network failure.
                return {'maps': maps, 'categories': categories, 'marks': [], 'total': 0,
                        'offset': offset, 'limit': limit, 'level_id': level_id,
                        'fetched_at': at, 'stale': stale, 'error': error}

    async def _cache_map(self, key, path, field):
        value, at = self._get(key)
        if not self._fresh(at):
            try:
                updated = _checked(await self._map_json(path), field)
                if not updated:
                    raise PublicSourceError('官方地图目录为空')
                value = updated
                self._put(key, value)
            except PublicSourceError as exc:
                if value is None:
                    raise
                return value, str(exc)
        return value, None


TOOLS = [
    {'id': 'map', 'name': '官方互动地图', 'description': '查看地区、资源与探索点位',
     'url': MAP_URL},
    {'id': 'wiki_operators', 'name': '干员资料', 'description': '从森空岛百科首页查找；公开目录暂不可读取',
     'url': WIKI_URL, 'status': 'unavailable'},
    {'id': 'wiki_weapons', 'name': '武器资料', 'description': '从森空岛百科首页查找；公开目录暂不可读取',
     'url': WIKI_URL, 'status': 'unavailable'},
    {'id': 'wiki_equipment', 'name': '装备资料', 'description': '从森空岛百科首页查找；公开目录暂不可读取',
     'url': WIKI_URL, 'status': 'unavailable'},
    {'id': 'wiki_items', 'name': '物品资料', 'description': '从森空岛百科首页查找；公开目录暂不可读取',
     'url': WIKI_URL, 'status': 'unavailable'},
    {'id': 'team_guides', 'name': '配队与养成', 'description': '进入森空岛官方工具页；公开目录暂不可读取',
     'url': 'https://game.skland.com/endfield', 'status': 'unavailable'},
]
