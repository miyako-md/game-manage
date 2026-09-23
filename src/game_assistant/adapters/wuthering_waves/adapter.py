import json
import logging
import time
from datetime import datetime, timezone

from game_assistant import event_calendar
from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.adapters.wuthering_waves import announcements, role, rolebox, widget
from game_assistant.adapters.wuthering_waves.kuro_client import AUTH_EXPIRED_CODES, KuroClient, KuroError
from game_assistant.adapters.wuthering_waves.rolebox_client import (
    RoleBoxClient, RoleBoxError,
)
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult
from .detail_parse import normalize, parse_tower, parse_periods, parse_profile, parse_report, latest_month_period
from .data_models import SourceResult, CombatPayload, ActivitiesPayload, ResourcesPayload

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
                    Capability.CALABASH, Capability.ROLES, Capability.COMBAT,
                    Capability.ACTIVITIES, Capability.RESOURCES]

    def __init__(self, settings: Settings):
        self._client: KuroClient | None = None
        self._settings = settings
        self._combat_cache = {}
        self._resource_cache = {}
        self._rolebox_refresh_key = None
        self._rolebox_refresh_time = 0.0
        if settings.wuwa_token and settings.wuwa_user_id:
            self.credentials_configured = True
            self._client = KuroClient(settings.wuwa_token,
                                      did=settings.wuwa_did, source=settings.wuwa_token_source)
        else:
            self.credentials_configured = False

    def _get_rolebox(self) -> RoleBoxClient:
        """roleBox 三件套全非空才启用（每次拉取新建，参考 LcuClient 生命周期）。"""
        s = self._settings
        if s.wuwa_b_at and s.wuwa_dev_code and s.wuwa_did:
            return RoleBoxClient(s.wuwa_b_at, s.wuwa_dev_code, s.wuwa_did, token=s.wuwa_token)
        raise _UnconfiguredRoleBoxError("未配置 b-at，请在「社区账号」登录鸣潮以自动获取角色会话")

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
                error_source='rolebox',
                error_kind='auth_expired' if e.code in AUTH_EXPIRED_CODES else 'source_error')
        except KuroError as e:
            # The legacy client includes str(httpx_error) for network errors;
            # request URLs can contain secrets and must not enter persisted status.
            message = '网络请求失败，请稍后重试' if e.code == -1 else e.message
            return FetchResult(ok=False, error=f"库街区接口错误: {message}", error_code=e.code,
                error_kind='auth_expired' if e.code in AUTH_EXPIRED_CODES else 'source_error')
        except Exception:
            # 解析器异常不得穿透 fetch 破坏失效隔离
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
            payload = role.parse_role_list(raw)
            if self._has_rolebox():
                role_id, server_id = await self._get_role_ids()
                async with self._get_rolebox() as rb:
                    await self._refresh_rolebox(rb, role_id, server_id)
                    base = await rb.base_data(role_id, server_id)
                payload.extra.update(role_id=role_id, server_id=server_id,
                    profile=parse_profile(base), provenance=self._provenance('baseData'))
            return FetchResult(ok=True, payload=payload)
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
                rows, VERSION_TITLE_KEYS,
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
            entries = rolebox.parse_role_data(raw)
            provenance = self._provenance('roleData')
            for entry in entries:
                entry.extra['account_role_id'] = role_id
                entry.extra['server_id'] = server_id
                entry.extra['provenance'] = provenance
            return FetchResult(ok=True, payload=entries)
        return await self._guarded_run(run)

    @staticmethod
    def _provenance(endpoint):
        return {'source': 'https://api.kurobbs.com', 'endpoint': endpoint,
                'fetched_at': datetime.now(timezone.utc).isoformat()}

    def _previous_payload(self, capability, role_id, server_id):
        store = getattr(getattr(self, '_auth', None), 'snapshots', None)
        snapshot = store.get(self.game_id, capability) if store else None
        payload = snapshot.get('payload') if snapshot else None
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                return {}
        if isinstance(payload, dict) and payload.get('role_id') == role_id and payload.get('server_id') == server_id:
            return payload
        return {}

    async def fetch_combat(self) -> FetchResult:
        async def run():
            role_id, server_id = await self._get_role_ids()
            # Token is only an in-memory cache discriminator, never serialized.
            identity = (role_id, server_id, self._settings.wuwa_user_id, self._settings.wuwa_token)
            previous = self._combat_cache.get(identity, {})
            if not previous:
                saved = self._previous_payload('combat', role_id, server_id)
                for key in ('tower', 'hologram', 'slash'):
                    if isinstance(saved.get(key), dict):
                        try:
                            previous[key] = SourceResult.model_validate(saved[key])
                        except ValueError:
                            pass
            sources = {}
            async with self._get_rolebox() as rb:
                await self._refresh_rolebox(rb, role_id, server_id)
                for name, method, endpoint in [('tower', rb.tower_detail, 'towerDataDetail'),
                        ('hologram', rb.challenge_details, 'challengeDetails'),
                        ('slash', rb.slash_detail, 'slashDetail')]:
                    try:
                        raw = await method(role_id, server_id)
                        if not isinstance(raw, dict) or not raw:
                            raise ValueError('来源数据缺失')
                        now = datetime.now(timezone.utc)
                        data = parse_tower(raw, now) if name == 'tower' else normalize(raw)
                        sources[name] = SourceResult(data=data, fetched_at=now.isoformat(), source=endpoint)
                    except RoleBoxError as error:
                        if error.code in AUTH_EXPIRED_CODES:
                            raise
                        old = previous.get(name)
                        sources[name] = SourceResult(state='stale' if old and old.data is not None else 'error',
                            data=old.data if old else None, fetched_at=old.fetched_at if old else None,
                            source=endpoint, error='来源请求失败，请稍后重试')
                    except (ValueError, TypeError, KeyError):
                        old = previous.get(name)
                        sources[name] = SourceResult(state='stale' if old and old.data is not None else 'error',
                            data=old.data if old else None, fetched_at=old.fetched_at if old else None,
                            source=endpoint, error='来源数据缺失、过期或无法解析')
            self._combat_cache = {identity: sources}
            return FetchResult(ok=True, payload=CombatPayload(role_id=role_id, server_id=server_id,
                provenance=self._provenance('combat'), **sources))
        return await self._guarded_run(run)

    async def fetch_activities(self) -> FetchResult:
        async def run():
            role_id, server_id = await self._get_role_ids()
            async with self._get_rolebox() as rb:
                raw = await rb.more_activity(role_id, server_id)
                if not isinstance(raw, dict) or not raw:
                    raise ValueError('玩法数据缺失')
            return FetchResult(ok=True, payload=ActivitiesPayload(role_id=role_id, server_id=server_id,
                provenance=self._provenance('moreActivity'), sections=normalize(raw)))
        return await self._guarded_run(run)

    async def fetch_role_detail(self, character_id: str) -> FetchResult:
        async def run():
            role_id, server_id = await self._get_role_ids()
            async with self._get_rolebox() as rb:
                owned = await rb.role_data(role_id, server_id)
                if character_id not in {str(r.get('roleId')) for r in owned.get('roleList', []) if isinstance(r, dict)}:
                    return FetchResult(ok=False, error='角色不属于当前账号', error_kind='not_found')
                raw = await rb.role_detail(role_id, server_id, character_id)
                if not isinstance(raw, dict) or not raw:
                    raise ValueError('角色详情缺失')
                returned_id = (raw.get('role') or {}).get('roleId')
                if returned_id is not None and str(returned_id) != character_id:
                    raise ValueError('角色详情不匹配')
            return FetchResult(ok=True, payload={'schema_version': 1, 'role_id': role_id,
                'server_id': server_id, 'character_id': character_id, 'data': normalize(raw),
                'provenance': self._provenance('getRoleDetail')})
        return await self._guarded_run(run)

    async def fetch_resource_detail(self, kind: str, period: str) -> FetchResult:
        async def run():
            if kind not in ('week', 'month', 'version'):
                return FetchResult(ok=False, error='无效资源类型', error_kind='not_found')
            role_id, server_id = await self._get_role_ids()
            async with self._get_rolebox() as rb:
                periods = parse_periods(await rb.period_list())
                if period not in {p['period'] for p in periods[kind]}:
                    return FetchResult(ok=False, error='该账号没有此资源周期', error_kind='not_found')
                raw = await rb.resource_report(role_id, server_id, kind, period)
            return FetchResult(ok=True, payload={'schema_version': 1, 'role_id': role_id,
                'server_id': server_id, 'kind': kind, 'period': period, 'data': parse_report(raw),
                'provenance': self._provenance('resource/' + kind)})
        return await self._guarded_run(run)

    async def fetch_resources(self) -> FetchResult:
        async def run():
            role_id, server_id = await self._get_role_ids()
            identity = (role_id, server_id, self._settings.wuwa_user_id, self._settings.wuwa_token)
            async with self._get_rolebox() as rb:
                periods = parse_periods(await rb.period_list())
                current, error = None, None
                if periods['month']:
                    period = latest_month_period(periods['month'])
                    try:
                        raw = await rb.resource_report(role_id, server_id, 'month', period)
                        current = {'kind': 'month', 'period': period, 'data': parse_report(raw),
                            'state': 'ok', 'fetched_at': datetime.now(timezone.utc).isoformat()}
                    except (RoleBoxError, ValueError, TypeError) as exc:
                        if isinstance(exc, RoleBoxError) and exc.code in AUTH_EXPIRED_CODES:
                            raise
                        error = '本月资源报告暂不可用'
                        previous = self._resource_cache.get(identity)
                        if previous is None:
                            previous = self._previous_payload('resources', role_id, server_id).get('current')
                        if previous:
                            current = {**previous, 'state': 'stale'}
            if current:
                self._resource_cache = {identity: current}
            return FetchResult(ok=True, payload=ResourcesPayload(role_id=role_id, server_id=server_id,
                provenance=self._provenance('resource'), periods=periods, current=current, error=error))
        return await self._guarded_run(run)
