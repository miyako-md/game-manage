import logging
import time
from datetime import datetime, timezone

from game_assistant import event_calendar
from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.adapters.wuthering_waves import announcements, role, rolebox, widget
from game_assistant.adapters.wuthering_waves.kuro_client import KuroClient, KuroError
from game_assistant.adapters.wuthering_waves.rolebox_client import (
    RoleBoxClient, RoleBoxError,
)
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult

logger = logging.getLogger(__name__)

# 版本公告标题关键词（findEventList 列表内筛选用，取发布时间最新的一篇；
# 2026-09-13 实测 3.6 版本公告标题为「蜃云灯影，凡尘剑心」3.6版本内容说明）
VERSION_TITLE_KEYS = ("版本内容说明", "版本更新公告", "版本维护更新")


class _UnconfiguredRoleBoxError(RoleBoxError):
    """Local missing configuration, distinct from a failed upstream request."""


class WutheringWavesAdapter(BaseGameAdapter):
    game_id = "wuthering_waves"
    display_name = "鸣潮"
    section = "mobile"
    capabilities = [Capability.ACCOUNT, Capability.STAMINA,
                    Capability.EVENTS, Capability.PROGRESS,
                    Capability.ANNOUNCEMENT, Capability.EXPLORATION,
                    Capability.CALABASH, Capability.ROLES]

    def __init__(self, settings: Settings):
        self._client: KuroClient | None = None
        self._settings = settings
        self._rolebox_refresh_key = None
        self._rolebox_refresh_time = 0.0
        if settings.wuwa_token and settings.wuwa_user_id:
            self.credentials_configured = True
            self._client = KuroClient(settings.wuwa_token, settings.wuwa_user_id,
                                      did=settings.wuwa_did, source=settings.wuwa_token_source)
        else:
            self.credentials_configured = False

    def _get_rolebox(self) -> RoleBoxClient:
        """roleBox 三件套全非空才启用（每次拉取新建，参考 LcuClient 生命周期）。"""
        s = self._settings
        if s.wuwa_b_at and s.wuwa_dev_code and s.wuwa_did:
            return RoleBoxClient(s.wuwa_b_at, s.wuwa_dev_code, s.wuwa_did)
        raise _UnconfiguredRoleBoxError("未配置 b-at（见 README APP 抓包教程）")

    def _has_rolebox(self) -> bool:
        s = self._settings
        return bool(s.wuwa_b_at and s.wuwa_dev_code and s.wuwa_did)

    async def _refresh_rolebox(self, client, role_id, server_id):
        # A manual refresh collects stamina and progress together. Share only the
        # refresh acknowledgement for ten seconds, never the fetched payload.
        key = (role_id, server_id, self._settings.wuwa_b_at, self._settings.wuwa_did, self._settings.wuwa_dev_code)
        if key == self._rolebox_refresh_key and time.monotonic() - self._rolebox_refresh_time < 10:
            return
        await client.refresh_data(role_id, server_id)
        self._rolebox_refresh_key, self._rolebox_refresh_time = key, time.monotonic()

    async def _guarded_run(self, run) -> FetchResult:
        """run 是零参协程工厂；统一处理未配置凭据与客户端错误。"""
        if self._client is None:
            return FetchResult(ok=False, error="未配置凭据", error_kind='unconfigured')
        try:
            return await run()
        except _UnconfiguredRoleBoxError as e:
            return FetchResult(ok=False, error=e.message, error_kind='unconfigured')
        except RoleBoxError as e:
            return FetchResult(ok=False, error=e.message, error_code=e.code,
                error_kind='auth_expired' if e.code in (220, 401, 402, 403, 10900, 10901, 10903) else 'source_error')
        except KuroError as e:
            # The legacy client includes str(httpx_error) for network errors;
            # request URLs can contain secrets and must not enter persisted status.
            message = '网络请求失败，请稍后重试' if e.code == -1 else e.message
            return FetchResult(ok=False, error=f"库街区接口错误: {message}", error_code=e.code,
                error_kind='auth_expired' if e.code in (220, 401, 402, 403, 10900, 10901, 10903) else 'source_error')
        except Exception:
            # 解析器异常不得穿透 fetch 破坏失效隔离（spec §6）
            logger.warning("鸣潮数据处理异常，保留上次成功数据")
            return FetchResult(ok=False, error="数据解析异常，请稍后重试", error_kind='invalid_data')

    async def _get_role_ids(self) -> tuple[str, str]:
        """role_list 取默认角色 roleId/serverId（roleBox 与 widget 共用）。"""
        if self._settings.wuwa_role_id and self._settings.wuwa_server_id:
            return self._settings.wuwa_role_id, self._settings.wuwa_server_id
        raw_role = await self._client.role_list()
        role_row = ((raw_role.get("data") or [{}])[0]) or {}
        role_id = role_row.get("roleId")
        server_id = role_row.get("serverId")
        if not role_id or not server_id:
            raise KuroError(-3, "未找到绑定的鸣潮角色")
        return str(role_id), str(server_id)

    async def _fetch_widget(self, refresh: bool = False):
        """role_list 取 roleId/serverId → widget_data。返回 (widget_raw, now)。

        Only token-only legacy accounts use widget refresh for stamina. Logged-in
        accounts refresh roleBox first; widget supplies remaining summary fields.
        """
        role_id, server_id = await self._get_role_ids()
        raw_widget = await self._client.widget_data(role_id, server_id,
                                                    refresh=refresh)
        return raw_widget, datetime.now(timezone.utc)

    async def fetch_account(self) -> FetchResult:
        async def run():
            raw = await self._client.role_list()
            if self._settings.wuwa_role_id:
                rows = [r for r in raw.get('data', []) if str(r.get('roleId')) == self._settings.wuwa_role_id]
                if not rows:
                    raise KuroError(-3, '已登录角色不再绑定，请重新登录')
                raw = {**raw, 'data': rows}
            return FetchResult(ok=True, payload=role.parse_role_list(raw))
        return await self._guarded_run(run)

    async def fetch_stamina(self) -> FetchResult:
        async def run():
            if self._has_rolebox():
                role_id, server_id = await self._get_role_ids()
                async with self._get_rolebox() as rb:
                    await self._refresh_rolebox(rb, role_id, server_id)
                    data = await rb.base_data(role_id, server_id)
                return FetchResult(ok=True, payload=role.parse_base_energy(data, datetime.now(timezone.utc)))
            # Legacy token-only accounts retain widget support. Never fall back
            # after a configured roleBox request fails and publish an older value.
            raw, now = await self._fetch_widget(refresh=True)
            st = role.parse_widget_energy(raw, now)
            return FetchResult(ok=True, payload=st)
        return await self._guarded_run(run)

    async def fetch_progress(self) -> FetchResult:
        async def run():
            if self._has_rolebox():
                role_id, server_id = await self._get_role_ids()
                async with self._get_rolebox() as rb:
                    await self._refresh_rolebox(rb, role_id, server_id)
                    detail = await rb.tower_detail(role_id, server_id)
                    tower_fetched_at = datetime.now(timezone.utc)
                    base = await rb.base_data(role_id, server_id)
                try:
                    tower = widget.parse_periodic_tower(detail, tower_fetched_at)
                    base_progress = widget.parse_base_progress(base)
                except ValueError as e:
                    return FetchResult(ok=False, error=str(e), error_kind='invalid_data')
                raw, _now = await self._fetch_widget()
                return FetchResult(ok=True, payload=[tower, *widget.parse_progress(raw, include_tower=False, overrides=base_progress)])
            raw, _now = await self._fetch_widget()
            return FetchResult(ok=True, payload=widget.parse_progress(raw))
        return await self._guarded_run(run)

    async def fetch_announcement(self) -> FetchResult:
        async def run():
            raw = await self._client.find_event_list(3)  # eventType 3=公告
            return FetchResult(ok=True, payload=announcements.parse_announcement_list(raw))
        return await self._guarded_run(run)

    async def fetch_events(self) -> FetchResult:
        async def run():
            # 活动日历：公告列表找版本公告 → 帖子详情 H5 正文 → 行级解析活动
            # （起止时间/名称/类型，event_calendar 共用解析器，服务器时间=UTC+8）
            raw = await self._client.find_event_list(3)  # eventType 3=公告
            data = raw.get("data") or {}
            rows = data.get("list") if isinstance(data, dict) else data
            post = event_calendar.find_version_post(
                rows, VERSION_TITLE_KEYS, id_key="postId",
                title_key="postTitle", time_key="publishTime")
            if not post:
                return FetchResult(ok=False, error='未找到版本公告，保留上次成功日历',
                                   error_kind='source_error')
            post_id = str(post.get("postId") or "")
            detail = await self._client.get_post_detail(post_id)
            lines = event_calendar.strip_html(str(detail.get("postH5Content") or ""))
            events = event_calendar.parse_events_from_lines(
                lines, source_post_id=post_id,
                source_title=str(detail.get("postTitle") or ""))
            if not events:
                return FetchResult(ok=False, error='版本公告正文为空或无法解析活动，保留上次成功日历',
                                   error_kind='invalid_data')
            return FetchResult(ok=True, payload=events)
        return await self._guarded_run(run)

    async def fetch_exploration(self) -> FetchResult:
        async def run():
            role_id, server_id = await self._get_role_ids()
            async with self._get_rolebox() as rb:
                raw = await rb.explore_index(role_id, server_id)
            return FetchResult(ok=True, payload=rolebox.parse_explore_index(raw))
        return await self._guarded_run(run)

    async def fetch_calabash(self) -> FetchResult:
        async def run():
            role_id, server_id = await self._get_role_ids()
            async with self._get_rolebox() as rb:
                raw = await rb.calabash_data(role_id, server_id)
            return FetchResult(ok=True, payload=rolebox.parse_calabash_data(raw))
        return await self._guarded_run(run)

    async def fetch_roles(self) -> FetchResult:
        async def run():
            role_id, server_id = await self._get_role_ids()
            async with self._get_rolebox() as rb:
                raw = await rb.role_data(role_id, server_id)
            return FetchResult(ok=True, payload=rolebox.parse_role_data(raw))
        return await self._guarded_run(run)
