import logging
from datetime import datetime, timezone

from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.adapters.wuthering_waves import announcements, events, role
from game_assistant.adapters.wuthering_waves.kuro_client import KuroClient, KuroError
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult

logger = logging.getLogger(__name__)


class WutheringWavesAdapter(BaseGameAdapter):
    game_id = "wuthering_waves"
    display_name = "鸣潮"
    section = "mobile"
    capabilities = [Capability.ACCOUNT, Capability.STAMINA,
                    Capability.ACTIVITY, Capability.ANNOUNCEMENT]

    def __init__(self, settings: Settings):
        self._client: KuroClient | None = None
        if settings.wuwa_token and settings.wuwa_user_id:
            self.credentials_configured = True
            self._client = KuroClient(settings.wuwa_token, settings.wuwa_user_id)
        else:
            self.credentials_configured = False

    async def _guarded_run(self, run) -> FetchResult:
        """run 是零参协程工厂；统一处理未配置凭据与 KuroError。"""
        if self._client is None:
            return FetchResult(ok=False, error="未配置凭据")
        try:
            return await run()
        except KuroError as e:
            return FetchResult(ok=False, error=f"库街区接口错误: {e.message}")
        except Exception as e:
            # 解析器异常不得穿透 fetch 破坏失效隔离（spec §6）
            logger.exception("鸣潮数据处理异常")
            return FetchResult(ok=False, error=f"数据解析异常: {e}")

    async def fetch_account(self) -> FetchResult:
        async def run():
            raw = await self._client.role_list()
            return FetchResult(ok=True, payload=role.parse_role_list(raw))
        return await self._guarded_run(run)

    async def fetch_stamina(self) -> FetchResult:
        async def run():
            # 两段调用（都在 _guarded_run 内）：先 role/list 取默认角色
            # roleId/serverId（从 raw dict 直取，不经 AccountInfo），再查 widget 体力
            roles_raw = await self._client.role_list()
            rows = (roles_raw or {}).get("data") or []
            first = rows[0] if rows else {}
            raw = await self._client.widget_data(
                first.get("roleId") or "", first.get("serverId") or "")
            st = role.parse_widget_energy(raw, datetime.now(timezone.utc))
            return FetchResult(ok=True, payload=st)
        return await self._guarded_run(run)

    async def fetch_activity(self) -> FetchResult:
        async def run():
            raw = await self._client.find_event_list(1)  # eventType 1=活动
            return FetchResult(ok=True, payload=events.parse_activity_list(raw))
        return await self._guarded_run(run)

    async def fetch_announcement(self) -> FetchResult:
        async def run():
            raw = await self._client.find_event_list(3)  # eventType 3=公告
            return FetchResult(ok=True, payload=announcements.parse_announcement_list(raw))
        return await self._guarded_run(run)
