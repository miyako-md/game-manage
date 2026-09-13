import logging
from datetime import datetime, timezone

from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.adapters.wuthering_waves import announcements, role, widget
from game_assistant.adapters.wuthering_waves.kuro_client import KuroClient, KuroError
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult

logger = logging.getLogger(__name__)


class WutheringWavesAdapter(BaseGameAdapter):
    game_id = "wuthering_waves"
    display_name = "鸣潮"
    section = "mobile"
    capabilities = [Capability.ACCOUNT, Capability.STAMINA,
                    Capability.ACTIVITY, Capability.PROGRESS,
                    Capability.ANNOUNCEMENT]

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

    async def _fetch_widget(self):
        """role_list 取 roleId/serverId → widget_data。返回 (widget_raw, now)。"""
        raw_role = await self._client.role_list()
        role_row = ((raw_role.get("data") or [{}])[0]) or {}
        role_id = role_row.get("roleId")
        server_id = role_row.get("serverId")
        if not role_id or not server_id:
            raise KuroError(-3, "未找到绑定的鸣潮角色")
        raw_widget = await self._client.widget_data(str(role_id), str(server_id))
        return raw_widget, datetime.now(timezone.utc)

    async def fetch_account(self) -> FetchResult:
        async def run():
            raw = await self._client.role_list()
            return FetchResult(ok=True, payload=role.parse_role_list(raw))
        return await self._guarded_run(run)

    async def fetch_stamina(self) -> FetchResult:
        async def run():
            raw, now = await self._fetch_widget()
            st = role.parse_widget_energy(raw, now)
            return FetchResult(ok=True, payload=st)
        return await self._guarded_run(run)

    async def fetch_activity(self) -> FetchResult:
        async def run():
            # 版本活动来自 widget activityData（社区活动列表 findEventList 已退役）
            raw, _now = await self._fetch_widget()
            act = widget.parse_version_activity(raw)
            # act 可能为 None（widget 未返回活动）→ payload=None，前端显示暂无数据
            return FetchResult(ok=True, payload=act)
        return await self._guarded_run(run)

    async def fetch_progress(self) -> FetchResult:
        async def run():
            raw, _now = await self._fetch_widget()
            return FetchResult(ok=True, payload=widget.parse_progress(raw))
        return await self._guarded_run(run)

    async def fetch_announcement(self) -> FetchResult:
        async def run():
            raw = await self._client.find_event_list(3)  # eventType 3=公告
            return FetchResult(ok=True, payload=announcements.parse_announcement_list(raw))
        return await self._guarded_run(run)
