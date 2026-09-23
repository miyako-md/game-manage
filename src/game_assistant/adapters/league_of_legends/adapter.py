"""英雄联盟适配器：LCU 账号/对局 + 官网公告/资讯。

_guarded_run 把客户端错误的 message 交给页面，并兜底捕获解析异常，
不让一个能力的失败影响其他能力。
"""
import logging

from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.adapters.league_of_legends.champions import ChampionCatalog
from game_assistant.adapters.league_of_legends.lcu_client import (
    LcuClient, LcuError, LcuUnavailableError,
)
from game_assistant.adapters.league_of_legends.lcu_discovery import (
    discover_lcu_credentials,
)
from game_assistant.adapters.league_of_legends.lol_news import (
    LoLNewsClient, LoLNewsError, parse_news_json,
)
from game_assistant.adapters.league_of_legends.matches import (
    compute_stats, parse_match_detail, parse_match_history,
)
from game_assistant.adapters.league_of_legends.summoner import parse_summoner
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult

logger = logging.getLogger(__name__)

# 官网分类（NEWS_CATEGORY_IDS）：公告=target 24 → ANNOUNCEMENT，综合=target 23 → NEWS
ANNOUNCEMENT_CATEGORY = "公告"
NEWS_CATEGORY = "综合"


class _ClientNotRunningError(LcuUnavailableError):
    """Discovery found no client; connection failures remain source errors."""


class LeagueOfLegendsAdapter(BaseGameAdapter):
    game_id = "league_of_legends"
    display_name = "英雄联盟"
    section = "pc"
    capabilities = [Capability.ACCOUNT, Capability.MATCH, Capability.STATS,
                    Capability.ANNOUNCEMENT, Capability.NEWS]

    def __init__(self, settings: Settings):
        # 凭据来自本机 LCU 进程发现（非存储凭据），credentials_configured 恒 True
        self.credentials_configured = True

    def _discover(self) -> tuple[str, str]:
        # 每次拉取重新发现：客户端重启后端口/token 都会变，psutil 扫描很轻
        creds = discover_lcu_credentials()
        if creds is None:
            raise _ClientNotRunningError("LOL 客户端未运行")
        return creds

    async def _guarded_run(self, run) -> FetchResult:
        """run 是零参协程工厂；统一处理客户端错误与解析兜底。"""
        try:
            return await run()
        except _ClientNotRunningError as e:
            return FetchResult(ok=False, error=e.message, error_kind='offline')
        except LcuError as e:
            return FetchResult(ok=False, error=e.message, error_kind='source_error')
        except LoLNewsError as e:
            return FetchResult(ok=False, error=e.message, error_kind='source_error')
        except Exception as exc:
            # 解析器异常不得穿透 fetch 破坏失效隔离。只记类型：异常文本可能带上游数据。
            logger.warning("英雄联盟数据处理异常，保留上次成功数据 (%s)", type(exc).__name__)
            return FetchResult(ok=False, error="数据处理异常，请稍后重试", error_kind='invalid_data')

    async def fetch_account(self) -> FetchResult:
        async def run():
            port, token = self._discover()
            async with LcuClient(port=port, token=token) as lcu:
                raw = await lcu.current_summoner()
                try:
                    ranked_raw = await lcu.ranked_stats(raw.get("puuid") or "")
                except LcuError:
                    ranked_raw = None  # 排位信息失败不致命，账号信息仍可用
                return FetchResult(ok=True, payload=parse_summoner(raw, ranked_raw))
        return await self._guarded_run(run)

    async def fetch_match(self) -> FetchResult:
        async def run():
            port, token = self._discover()
            async with LcuClient(port=port, token=token) as lcu:
                raw = await lcu.current_summoner()
                puuid = raw.get("puuid") or ""
                history = await lcu.match_history(puuid)
                return FetchResult(ok=True,
                                   payload=parse_match_history(history, puuid))
        return await self._guarded_run(run)

    async def fetch_stats(self) -> FetchResult:
        # 生涯统计：近 20 场口径（国服 match history 不支持翻页）；
        # 英雄目录网络失败自动降级（champions.py），不影响统计主流程
        async def run():
            port, token = self._discover()
            async with LcuClient(port=port, token=token) as lcu:
                raw = await lcu.current_summoner()
                puuid = raw.get("puuid") or ""
                history = await lcu.match_history(puuid)
                summaries = parse_match_history(history, puuid)
                catalog = await ChampionCatalog().get()
                return FetchResult(ok=True,
                                   payload=compute_stats(summaries, catalog))
        return await self._guarded_run(run)

    async def fetch_match_detail(self, match_id: str) -> FetchResult:
        # 按需拉取（非 capability 轮询），由 /api/.../detail 路由直接调用
        async def run():
            port, token = self._discover()
            async with LcuClient(port=port, token=token) as lcu:
                raw = await lcu.current_summoner()
                puuid = raw.get("puuid") or ""
                detail = await lcu.game_detail(match_id)
                catalog = await ChampionCatalog().get()
                return FetchResult(
                    ok=True,
                    payload=parse_match_detail(detail, puuid, catalog))
        return await self._guarded_run(run)

    async def _fetch_category(self, category: str) -> FetchResult:
        async def run():
            async with LoLNewsClient() as client:
                data = await client.fetch_news(category)
            return FetchResult(ok=True, payload=parse_news_json(data))
        return await self._guarded_run(run)

    async def fetch_announcement(self) -> FetchResult:
        return await self._fetch_category(ANNOUNCEMENT_CATEGORY)

    async def fetch_news(self) -> FetchResult:
        return await self._fetch_category(NEWS_CATEGORY)
