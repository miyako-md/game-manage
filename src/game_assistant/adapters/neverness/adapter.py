"""异环账号数据标准化；公开公告/活动与私人角色数据隔离。"""
import logging
import json
import time
import re
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone

from game_assistant import event_calendar
from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.adapters.neverness import tajiduo
from game_assistant.adapters.neverness import parse
from game_assistant.adapters.neverness import assets
from game_assistant.adapters.neverness.endpoints import GAME_ID, GET_POST_FULL
from game_assistant.adapters.neverness.data_models import NteCalendarEvent
from game_assistant.adapters.neverness.tajiduo_client import (
    TajiduoClient, TajiduoError, TajiduoWebClient,
)
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult

logger = logging.getLogger(__name__)

# 官方公告每页条数（与参考项目一致的保守值）
OFFICIAL_POST_COUNT = 20

# 版本公告标题关键词（官方栏目帖 subject 匹配，取发布时间最新的一篇）
VERSION_TITLE_KEYS = ("更新公告", "更新优化公告", "内容说明", "维护更新公告")
VERSION_NUMBER = re.compile(r'(?<!\d)(\d+\.\d+)\s*版本')


def _parse_notice_events(post, detail, version, *, date_content=None):
    if detail.get('postId') is not None and str(detail['postId']) != str(post.get('postId') or ''):
        raise ValueError('public notice identity mismatch')
    # Date parsing may prepend a verified list heading; retain original HTML for artwork.
    # content 为 HTML 或明文：strip_html 对明文原样按行拆分
    lines = event_calendar.strip_html(str(date_content if date_content is not None else detail.get("content") or ""))
    title = str(post.get('subject') or '')
    post_id = str(post.get('postId') or '')
    declarations = [VERSION_NUMBER.search(title), VERSION_NUMBER.search('\n'.join(lines)[:4000])]
    if any(declared and declared[1] != version for declared in declarations):
        raise ValueError('public notice version mismatch')
    published = event_calendar.parse_ms_or_iso(post.get('createTime'))
    events = []
    if published is not None or any(event_calendar.CN_DATE_RANGE_RE.search(line) for line in lines):
        from game_assistant.sources.public_content import parse_post_events
        # Use the already supported NTE quote/short-date format. A source
        # publication year is required; never substitute collection time.
        source_url = GET_POST_FULL + '?' + urlencode({'postId': post_id})
        notice = {'id':post_id, 'title':title, 'body':'\n'.join(lines), 'decision':'accepted',
                  'published_at':published.isoformat() if published else None, 'url':source_url,
                  'source':'community', 'source_name':'塔吉多官方公告'}
        events = [NteCalendarEvent(**{**row, 'source':'community', 'source_name':'塔吉多官方公告',
            'source_title':title, 'published_at':published})
            for row in parse_post_events(notice, 'nte', version)]
    if not events:
        # Preserve legacy notices with bracket headings and explicit years.
        events = [NteCalendarEvent(**{**e.model_dump(), 'version':version}) for e in event_calendar.parse_events_from_lines(
            lines, source_post_id=post_id, source_title=title)]
    from game_assistant.sources.article_content import article_content, article_images
    images = article_images(detail.get('images'), post.get('images'),
                            article_content(detail.get('content'))['images'])
    return [event.model_copy(update={'image_urls': images}) for event in events]


class _UnconfiguredCredentialsError(TajiduoError):
    """Credentials absent locally, not a network or authentication failure."""


class NteAdapter(BaseGameAdapter):
    game_id = "nte"
    display_name = "异环"
    section = "mobile"
    capabilities = [Capability.ACCOUNT, Capability.STAMINA, Capability.ROLES,
                    Capability.PROGRESS, Capability.EXPLORATION, Capability.GACHA,
                    Capability.RECORD, Capability.EVENTS, Capability.ANNOUNCEMENT,
                    Capability.REALESTATE, Capability.VEHICLES, Capability.TEAMS]

    def __init__(self, settings: Settings):
        self._settings = settings
        self._home_cache = None
        self._characters_cache = None
        self._cache_generation = 0
        # access/refresh 任一即可；登录服务负责令牌续期和原请求单次重试。
        self.credentials_configured = bool(
            settings.nte_access_token or settings.nte_refresh_token)

    def prepare_refresh(self) -> None:
        self._cache_generation += 1
        self._home_cache = None
        self._characters_cache = None

    def _require_client(self) -> TajiduoClient:
        """每次拉取新建鉴权客户端（参考 LoLNewsClient 生命周期模式）。"""
        s = self._settings
        if not (s.nte_access_token or s.nte_refresh_token):
            raise _UnconfiguredCredentialsError("未配置塔吉多凭据")
        return TajiduoClient(s.nte_access_token,
                             device_id=s.nte_device_id or None)

    async def _guarded_run(self, run) -> FetchResult:
        """run 是零参协程工厂；统一处理未配置凭据与客户端/解析错误。"""
        try:
            return await run()
        except _UnconfiguredCredentialsError as e:
            return FetchResult(ok=False, error=e.message, error_kind='unconfigured')
        except TajiduoError as e:
            return FetchResult(ok=False, error=e.message, error_code=e.status_code,
                error_kind='auth_expired' if e.expired else 'source_error')
        except ValueError:
            return FetchResult(ok=False, error='塔吉多数据格式已变化或角色不匹配，保留上次成功数据',
                               error_kind='invalid_data')
        except Exception as exc:
            # 解析器异常不得穿透 fetch 破坏失效隔离。只记类型：异常文本可能带上游数据。
            logger.warning("异环数据处理异常，保留上次成功数据 (%s)", type(exc).__name__)
            return FetchResult(ok=False, error="数据处理异常，请稍后重试", error_kind='invalid_data')

    async def fetch_announcement(self) -> FetchResult:
        async def run():
            # 公告链路：社区列表定位异环"官方资讯"栏目 → 栏目帖列表
            # （TajiduoWebClient 每次新建 + async with，匿名无凭据）
            async with TajiduoWebClient() as web:
                communities = await web.get_all_communities()
                column_id = tajiduo.resolve_official_column_id(communities)
                if not column_id:
                    raise TajiduoError("未能在社区数据中定位官方资讯栏目")
                raw = await web.get_official_post_list(
                    column_id, count=OFFICIAL_POST_COUNT)
            return FetchResult(ok=True,
                               payload=tajiduo.parse_official_posts(raw))
        return await self._guarded_run(run)

    async def fetch_events(self) -> FetchResult:
        async def run():
            # config 手填的 [[nte_events]] 非空时优先于下面的公告扫描；API 层
            # 再以 B站为主来源合并。配置非空即走手填（即使条目全部非法也不
            # 回退，避免配置错误被自动扫描静默掩盖——坏项已 log.warning）
            if self._settings.nte_events:
                events = event_calendar.parse_manual_events(self._settings.nte_events)
                if not events:
                    return FetchResult(ok=False, error='手动配置的活动全部无效，保留上次成功日历',
                                       error_kind='invalid_data')
                return FetchResult(ok=True, payload=events)
            # 兜底：塔吉多版本公告扫描（官方栏目帖列表找版本公告 → 帖子
            # 详情正文 → 行级解析）。匿名 Web 客户端，一次拉取内复用同一连接
            async with TajiduoWebClient() as web:
                communities = await web.get_all_communities()
                column_id = tajiduo.resolve_official_column_id(communities)
                if not column_id:
                    raise TajiduoError("未能在社区数据中定位官方资讯栏目")
                raw = await web.get_official_post_list(
                    column_id, count=OFFICIAL_POST_COUNT, official_type=3)
                from game_assistant.version_calendar import maintenance
                bases = [row for row in tajiduo._extract_rows(raw) if isinstance(row, dict)
                         and VERSION_NUMBER.search(str(row.get('subject') or ''))
                         and any(k in str(row.get('subject') or '') for k in VERSION_TITLE_KEYS)]
                bases.sort(key=lambda r: event_calendar.parse_ms_or_iso(r.get('createTime'))
                           or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
                notices = []
                post = None
                for candidate in bases[:3]:
                    published = event_calendar.parse_ms_or_iso(candidate.get('createTime'))
                    if published and published > datetime.now(timezone.utc):
                        continue
                    candidate_id = str(candidate.get('postId') or '')
                    candidate_detail = await web.get_post_full(candidate_id)
                    body = '\n'.join(event_calendar.strip_html(str(candidate_detail.get('content') or '')))
                    candidate_notice = dict(id=candidate_id, title=candidate.get('subject'), body=body,
                        published_at=published.isoformat() if published else None,
                        url=GET_POST_FULL+'?'+urlencode({'postId':candidate_id}), source_name='塔吉多官方公告')
                    notices.append(candidate_notice)
                    release, _ = maintenance(candidate_notice)
                    if release and release > datetime.now(timezone.utc):
                        continue
                    post, detail = candidate, candidate_detail
                    break
                if not post:
                    return FetchResult(ok=False, error='未找到版本公告，保留上次成功日历',
                                       error_kind='source_error')
                post_id = str(post.get("postId") or "")
                base_detail = dict(detail)
                version = VERSION_NUMBER.search(str(post.get('subject') or '')).group(1)
                events = _parse_notice_events(post, detail, version)
                if not events:
                    return FetchResult(ok=False, error='版本公告正文为空或无法解析活动，保留上次成功日历',
                                       error_kind='invalid_data')
                # Reuse the same bounded NOTICE page. Failure of a selected
                # independent notice must retain the previous full snapshot.
                from game_assistant.sources.public_content import _same_event
                base_stamp = event_calendar.parse_ms_or_iso(post.get('createTime'))
                from game_assistant.version_calendar import select_unversioned_events, version_metadata
                meta = version_metadata('nte', dict(id=post_id, title=post.get('subject'),
                    body='\n'.join(event_calendar.strip_html(str(base_detail.get('content') or ''))),
                    published_at=base_stamp.isoformat() if base_stamp else None, fetched_at=datetime.now(timezone.utc).isoformat(),
                    url=GET_POST_FULL+'?'+urlencode({'postId':post_id}), source_name='塔吉多官方公告'), notices)
                candidates = []
                for row in tajiduo._extract_rows(raw):
                    if not isinstance(row, dict) or str(row.get('postId')) == post_id:
                        continue
                    title = str(row.get('subject') or '')
                    if not re.search(r'限定棋盘|弧盘研募|限时活动|活动(?:公告|开启|时间)', title):
                        continue
                    declared = VERSION_NUMBER.search(title)
                    stamp = event_calendar.parse_ms_or_iso(row.get('createTime'))
                    if declared and declared[1] != version:
                        continue
                    if not declared and (not stamp or not base_stamp or stamp < base_stamp - timedelta(days=7)):
                        continue
                    if stamp and stamp > datetime.now(timezone.utc):
                        continue
                    candidates.append(row)
                candidates.sort(key=lambda r: event_calendar.parse_ms_or_iso(r.get('createTime'))
                                or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
                seen = {post_id}
                independent = []
                for row in candidates:
                    ident = str(row.get('postId') or '')
                    if ident in seen:
                        continue
                    if len(seen) >= 7:
                        break
                    seen.add(ident)
                    detail = await web.get_post_full(ident)
                    if detail.get('postId') is not None and str(detail['postId']) != ident:
                        raise ValueError('public notice identity mismatch')
                    body = '\n'.join(event_calendar.strip_html(str(detail.get('content') or '')))
                    declarations = [VERSION_NUMBER.search(str(row.get('subject') or '')), VERSION_NUMBER.search(body[:4000])]
                    declared = next((d for d in declarations if d), None)
                    stamp = event_calendar.parse_ms_or_iso(row.get('createTime'))
                    if any(d and d[1] != version for d in declarations):
                        continue
                    if not declared and stamp and base_stamp and stamp < base_stamp:
                        continue
                    parsed = _parse_notice_events(row, detail, version,
                        date_content='● '+str(row.get('subject') or '')+'\n'+body)
                    if not parsed:
                        raise ValueError('independent public notice has no dated events')
                    if not declared:
                        parsed = [NteCalendarEvent(**row) for row in select_unversioned_events(
                            [e.model_dump(mode='json') for e in parsed], meta)]
                    independent.extend(parsed)
                if independent:
                    merged = []
                    for event in sorted(independent + events, key=lambda e: getattr(e, 'published_at', None)
                                        or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
                        if not any(_same_event(old.model_dump(mode='json'), event.model_dump(mode='json')) for old in merged):
                            merged.append(event)
                    events = merged
            if not events:
                return FetchResult(ok=False, error='版本公告正文为空或无法解析活动，保留上次成功日历',
                                   error_kind='invalid_data')
            events = [event.model_copy(update={'version_metadata':meta}) for event in events]
            return FetchResult(ok=True, payload=events)
        return await self._guarded_run(run)

    async def _first_role_id(self, client: TajiduoClient) -> str:
        """使用登录选中的角色；旧配置仅在绑定角色列表范围内查找。"""
        if self._settings.nte_role_id:
            return self._settings.nte_role_id
        raw = await client.get_game_roles()
        data = self._data(raw)
        rows = data.get('roles', data.get('list', [])) if isinstance(data, dict) else data
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict) or str(row.get('gameId', GAME_ID)) != GAME_ID:
                    continue
                role_id = str(row.get('roleId') or '')
                if role_id and role_id != '0':
                    return role_id
        raise TajiduoError("未找到绑定的异环角色")

    @staticmethod
    def _data(raw):
        data = raw.get('data')
        return json.loads(data) if isinstance(data, str) else data

    async def _home(self, client, role_id):
        generation = self._cache_generation
        key = (self._settings.nte_access_token, role_id)
        if self._home_cache and self._home_cache[0] == key and self._home_cache[1] > time.monotonic():
            return self._home_cache[2], self._home_cache[3]
        raw = await client.get_role_home(role_id)
        parse.parse_account(raw, expected_role_id=role_id)
        fetched = datetime.now(timezone.utc)
        if generation == self._cache_generation:
            self._home_cache = (key, time.monotonic() + 30, raw, fetched)
        return raw, fetched

    async def _characters(self, client, role_id):
        generation = self._cache_generation
        key = (self._settings.nte_access_token, role_id)
        if self._characters_cache and self._characters_cache[0] == key and self._characters_cache[1] > time.monotonic():
            return self._characters_cache[2]
        raw = await client.get_role_characters(role_id)
        parse.parse_roles(raw)
        if generation == self._cache_generation:
            self._characters_cache = (key, time.monotonic() + 30, raw)
        return raw

    async def fetch_account(self) -> FetchResult:
        async def run():
            async with self._require_client() as client:
                role_id = await self._first_role_id(client)
                raw, _ = await self._home(client, role_id)
            return FetchResult(ok=True, payload=parse.parse_account(raw, expected_role_id=role_id))
        return await self._guarded_run(run)

    async def fetch_stamina(self) -> FetchResult:
        async def run():
            async with self._require_client() as client:
                role_id = await self._first_role_id(client)
                raw, fetched = await self._home(client, role_id)
            return FetchResult(ok=True, payload=parse.parse_stamina(raw, fetched, expected_role_id=role_id))
        return await self._guarded_run(run)

    async def fetch_exploration(self) -> FetchResult:
        async def run():
            async with self._require_client() as client:
                role_id = await self._first_role_id(client)
                raw = await client.get_role_area_progress(role_id)
            return FetchResult(ok=True, payload=parse.parse_exploration(raw))
        return await self._guarded_run(run)

    async def fetch_realestate(self) -> FetchResult:
        async def run():
            async with self._require_client() as client:
                role_id = await self._first_role_id(client)
                raw = await client.get_role_realestate(role_id)
            return FetchResult(ok=True, payload=assets.parse_realestate(raw))
        return await self._guarded_run(run)

    async def fetch_vehicles(self) -> FetchResult:
        async def run():
            async with self._require_client() as client:
                role_id = await self._first_role_id(client)
                raw = await client.get_role_vehicles(role_id)
            return FetchResult(ok=True, payload=assets.parse_vehicles(raw))
        return await self._guarded_run(run)

    async def fetch_teams(self) -> FetchResult:
        async def run():
            async with TajiduoWebClient() as client:
                raw = await client.get_teams()
            return FetchResult(ok=True, payload=assets.parse_teams(raw))
        return await self._guarded_run(run)

    async def fetch_roles(self) -> FetchResult:
        async def run():
            async with self._require_client() as client:
                role_id = await self._first_role_id(client)
                raw = await self._characters(client, role_id)
            return FetchResult(ok=True, payload=parse.parse_roles(raw))
        return await self._guarded_run(run)

    async def fetch_progress(self) -> FetchResult:
        async def run():
            async with self._require_client() as client:
                role_id = await self._first_role_id(client)
                raw = await client.get_role_achievement_progress(role_id)
            return FetchResult(ok=True, payload=parse.parse_progress(raw))
        return await self._guarded_run(run)

    async def fetch_gacha(self) -> FetchResult:
        async def run():
            async with self._require_client() as client:
                role_id = await self._first_role_id(client)
                raw = await client.get_gacha_summary()
                names = {}
                try:
                    characters = self._data(await self._characters(client, role_id))
                    for character in characters:
                        if character['name']:  # null 名称不进映射，由解析器给 id 标签
                            names[str(character['id'])] = str(character['name'])
                        weapon = character.get('fork')
                        if isinstance(weapon, dict) and weapon.get('id') and weapon.get('name'):
                            names[str(weapon['id'])] = str(weapon['name'])
                except TajiduoError as error:
                    if error.status_code in (401, 402, 403):
                        raise  # 交给登录生命周期刷新并重试，不能把失效标成成功。
                    logger.info('异环抽卡物品名称暂不可用，使用物品 ID')
                except (ValueError, KeyError, TypeError):
                    # 名称不可用不影响抽卡统计；以原始 ID 明确标识未命中的物品。
                    logger.info('异环抽卡物品名称暂不可用，使用物品 ID')
            return FetchResult(ok=True, payload=parse.parse_gacha(raw, names=names, expected_role_id=role_id))
        return await self._guarded_run(run)

    async def fetch_record(self) -> FetchResult:
        async def run():
            # 社区名片：用户中心 UID 与游戏 roleId 不同；只读取已知 user 字段。
            async with self._require_client() as client:
                role_id = await self._first_role_id(client)
                info = await client.get_user_full_info()
                data = self._data(info)
                user = data.get('user', data) if isinstance(data, dict) else {}
                uid = user.get('uid') if isinstance(user, dict) else None
                if not uid:
                    raise TajiduoError("未找到游戏 uid")
                raw = await client.get_game_record_card(str(uid))
            return FetchResult(ok=True, payload=parse.parse_record(raw, expected_role_id=role_id))
        return await self._guarded_run(run)
