"""异环（NTE）适配器：塔吉多社区官方公告 + 需凭据的账号数据（Phase 1）。

结构照鸣潮/英雄联盟适配器的 _guarded_run 模式（客户端错误暴露 message，
catch-all 兜底防解析异常穿透破坏失效隔离）。

Phase 1 边界：
- 官方公告走匿名 Web 客户端，无需凭据；
- 角色/进度/抽卡/战绩四能力需塔吉多凭据（access_token 或 refresh_token 任一），
  当前直接透传原始 dict payload，解析器等真实响应校准后 Phase 2 补充；
- 无体力接口、无结构化活动日历（参考项目同样如此），故无 STAMINA/ACTIVITY 能力。
"""
import logging

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


class NteAdapter(BaseGameAdapter):
    game_id = "nte"
    display_name = "异环"
    section = "mobile"
    capabilities = [Capability.ANNOUNCEMENT, Capability.ROLES,
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
