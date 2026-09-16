"""异环账号数据标准化；公开公告/活动与私人角色数据隔离。"""
import logging
import json
import time
from datetime import datetime, timezone

from game_assistant import event_calendar
from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.adapters.neverness import tajiduo
from game_assistant.adapters.neverness import parse
from game_assistant.adapters.neverness.tajiduo_client import (
    TajiduoClient, TajiduoError, TajiduoWebClient,
)
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult

logger = logging.getLogger(__name__)

# 官方公告每页条数（与参考项目一致的保守值）
OFFICIAL_POST_COUNT = 20

# 版本公告标题关键词（官方栏目帖 subject 匹配，取发布时间最新的一篇）
VERSION_TITLE_KEYS = ("版本更新公告", "版本内容说明", "维护更新公告")


class _UnconfiguredCredentialsError(TajiduoError):
    """Credentials absent locally, not a network or authentication failure."""


class NteAdapter(BaseGameAdapter):
    game_id = "nte"
    display_name = "异环"
    section = "mobile"
    capabilities = [Capability.ACCOUNT, Capability.STAMINA, Capability.ROLES,
                    Capability.PROGRESS, Capability.EXPLORATION, Capability.GACHA,
                    Capability.RECORD, Capability.EVENTS, Capability.ANNOUNCEMENT]

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
        return TajiduoClient(s.nte_access_token, s.nte_refresh_token,
                             device_id=s.nte_device_id or None)

    async def _guarded_run(self, run) -> FetchResult:
        """run 是零参协程工厂；统一处理未配置凭据与客户端/解析错误。"""
        try:
            return await run()
        except _UnconfiguredCredentialsError as e:
            return FetchResult(ok=False, error=e.message, error_kind='unconfigured')
        except TajiduoError as e:
            return FetchResult(ok=False, error=e.message, error_code=e.status_code,
                error_kind='auth_expired' if e.status_code in (401, 402, 403) else 'source_error')
        except ValueError:
            return FetchResult(ok=False, error='塔吉多数据格式已变化或角色不匹配，保留上次成功数据',
                               error_kind='invalid_data')
        except Exception:
            # 解析器异常不得穿透 fetch 破坏失效隔离
            logger.warning("异环数据处理异常，保留上次成功数据")
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
            # 主路径：config 手填（[[nte_events]]，长图 OCR 辅助人工抄写，
            # 可靠）。配置非空即走手填（即使条目全部非法也不回退，避免配置
            # 错误被自动扫描静默掩盖——坏项已 log.warning）
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
                    column_id, count=OFFICIAL_POST_COUNT)
                post = event_calendar.find_version_post(
                    tajiduo._extract_rows(raw), VERSION_TITLE_KEYS,
                    id_key="postId", title_key="subject", time_key="createTime")
                if not post:
                    return FetchResult(ok=False, error='未找到版本公告，保留上次成功日历',
                                       error_kind='source_error')
                post_id = str(post.get("postId") or "")
                detail = await web.get_post_full(post_id)
            # content 为 HTML 或明文：strip_html 对明文原样按行拆分
            lines = event_calendar.strip_html(str(detail.get("content") or ""))
            events = event_calendar.parse_events_from_lines(
                lines, source_post_id=post_id,
                source_title=str(post.get("subject") or ""))
            if not events:
                return FetchResult(ok=False, error='版本公告正文为空或无法解析活动，保留上次成功日历',
                                   error_kind='invalid_data')
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
                if not isinstance(row, dict) or str(row.get('gameId', '1289')) != '1289':
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
