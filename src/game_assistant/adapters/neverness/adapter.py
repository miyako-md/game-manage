"""异环（NTE）适配器：塔吉多社区官方公告 + 需凭据的账号数据（Phase 1）。

结构照鸣潮/英雄联盟适配器的 _guarded_run 模式（客户端错误暴露 message，
catch-all 兜底防解析异常穿透破坏失效隔离）。

Phase 1 边界：
- 官方公告与活动日历走匿名 Web 客户端，无需凭据；活动日历为版本公告正文
  解析（event_calendar 行级扫描，真实版本公告格式待下个版本公告出现后联调
  校准——2026-09-13 官方栏目无版本更新公告在榜）；
- 角色/进度/抽卡/战绩四能力需塔吉多凭据（access_token 或 refresh_token 任一），
  当前直接透传原始 dict payload，解析器等真实响应校准后 Phase 2 补充；
- 无体力接口（参考项目同样如此），故无 STAMINA 能力。
"""
import logging

from game_assistant import event_calendar
from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.adapters.neverness import tajiduo
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


class NteAdapter(BaseGameAdapter):
    game_id = "nte"
    display_name = "异环"
    section = "mobile"
    capabilities = [Capability.ANNOUNCEMENT, Capability.EVENTS,
                    Capability.ROLES,
                    Capability.PROGRESS, Capability.GACHA, Capability.RECORD]

    def __init__(self, settings: Settings):
        self._settings = settings
        # access/refresh 任一即可（只有 access 也能查询，过期后重新抓取；
        # refresh_session 换新对属 Phase 2 联调范围）
        self.credentials_configured = bool(
            settings.nte_access_token or settings.nte_refresh_token)

    def _require_client(self) -> TajiduoClient:
        """每次拉取新建鉴权客户端（参考 LoLNewsClient 生命周期模式）。"""
        s = self._settings
        if not (s.nte_access_token or s.nte_refresh_token):
            raise TajiduoError("未配置塔吉多凭据")
        return TajiduoClient(s.nte_access_token, s.nte_refresh_token)

    async def _guarded_run(self, run) -> FetchResult:
        """run 是零参协程工厂；统一处理未配置凭据与客户端/解析错误。"""
        try:
            return await run()
        except TajiduoError as e:
            return FetchResult(ok=False, error=e.message)
        except Exception as e:
            # 解析器异常不得穿透 fetch 破坏失效隔离
            logger.exception("异环数据处理异常")
            return FetchResult(ok=False, error=f"数据处理异常: {e}")

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
                return FetchResult(
                    ok=True,
                    payload=event_calendar.parse_manual_events(
                        self._settings.nte_events))
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
                    # 官方栏目无版本公告（如版本间隙期）：优雅降级为空列表
                    return FetchResult(ok=True, payload=[])
                post_id = str(post.get("postId") or "")
                detail = await web.get_post_full(post_id)
            # content 为 HTML 或明文：strip_html 对明文原样按行拆分
            lines = event_calendar.strip_html(str(detail.get("content") or ""))
            events = event_calendar.parse_events_from_lines(
                lines, source_post_id=post_id,
                source_title=str(post.get("subject") or ""))
            return FetchResult(ok=True, payload=events)
        return await self._guarded_run(run)

    async def _first_role_id(self, client: TajiduoClient) -> str:
        """getGameRoles 取首个绑定角色 roleId（防御式提取，Phase 2 校准）。"""
        raw = await client.get_game_roles()
        role_id = tajiduo.find_first(raw, ("roleId", "role_id"))
        if not role_id:
            raise TajiduoError("未找到绑定的异环角色")
        return str(role_id)

    async def fetch_roles(self) -> FetchResult:
        async def run():
            # 角色面板：getGameRoles 取 roleId → yh/characters 角色列表
            # （原始 dict payload，Phase 2 校准解析为练度墙）
            async with self._require_client() as client:
                role_id = await self._first_role_id(client)
                raw = await client.get_role_characters(role_id)
            return FetchResult(ok=True, payload=raw)
        return await self._guarded_run(run)

    async def fetch_progress(self) -> FetchResult:
        async def run():
            # 进度：getGameRoles 取 roleId → yh/achieveProgress 成就进度
            # （ProgressCard 语义最接近；areaProgress/realestate/vehicles
            # 挂哪张卡待 Phase 2 按真实响应决定）
            async with self._require_client() as client:
                role_id = await self._first_role_id(client)
                raw = await client.get_role_achievement_progress(role_id)
            return FetchResult(ok=True, payload=raw)
        return await self._guarded_run(run)

    async def fetch_gacha(self) -> FetchResult:
        async def run():
            # 抽卡记录：yh/gacha（参考项目调用未见 roleId 参数）
            async with self._require_client() as client:
                raw = await client.get_gacha_summary()
            return FetchResult(ok=True, payload=raw)
        return await self._guarded_run(run)

    async def fetch_record(self) -> FetchResult:
        async def run():
            # 战绩卡：getUserFullInfo 取 uid → getGameRecordCard
            async with self._require_client() as client:
                info = await client.get_user_full_info()
                uid = tajiduo.find_first(info, ("uid", "gameUid", "userUid"))
                if not uid:
                    raise TajiduoError("未找到游戏 uid")
                raw = await client.get_game_record_card(str(uid))
            return FetchResult(ok=True, payload=raw)
        return await self._guarded_run(run)
