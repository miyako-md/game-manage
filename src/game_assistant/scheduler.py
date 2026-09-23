import asyncio
import json
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from pydantic import BaseModel

from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult

logger = logging.getLogger(__name__)

INTERVAL_ATTRS = {
    Capability.STAMINA: "stamina_seconds",
    Capability.PROGRESS: "activity_seconds",
    Capability.ANNOUNCEMENT: "announcement_seconds",
    # 活动日历（版本公告解析）：与公告同源同频
    Capability.EVENTS: "announcement_seconds",
    Capability.NEWS: "news_seconds",
    Capability.ACCOUNT: "activity_seconds",
    Capability.MATCH: "activity_seconds",
    # 生涯统计（近 20 场口径）：慢变化数据，与对局同为 1 小时
    Capability.STATS: "activity_seconds",
    # 探索度/数据坞（roleBox）：慢变化数据，与资讯同为 4 小时
    Capability.EXPLORATION: "news_seconds",
    Capability.CALABASH: "news_seconds",
    # 角色练度墙（roleBox）：抽到新角色能较快反映，与进度同为 1 小时
    Capability.ROLES: "activity_seconds",
    Capability.COMBAT: "activity_seconds",
    Capability.ACTIVITIES: "activity_seconds",
    Capability.RESOURCES: "news_seconds",
    # 异环（塔吉多）抽卡记录/战绩卡：慢变化数据，与资讯同为 4 小时
    Capability.GACHA: "news_seconds",
    Capability.RECORD: "news_seconds",
    Capability.REALESTATE: "news_seconds",
    Capability.VEHICLES: "news_seconds",
    Capability.TEAMS: "news_seconds",
}


def interval_for(capability: Capability, settings: Settings) -> int:
    return getattr(settings, INTERVAL_ATTRS[capability])


def _serialize(payload: Any) -> str:
    if isinstance(payload, list):
        return json.dumps([p.model_dump(mode="json") if isinstance(p, BaseModel)
                           else p for p in payload], ensure_ascii=False)
    if isinstance(payload, BaseModel):
        return payload.model_dump_json()
    return json.dumps(payload, ensure_ascii=False)


class PollingScheduler:
    def __init__(self, registry, store, settings: Settings, reminder=None):
        self.registry = registry
        self.store = store
        self.settings = settings
        self.reminder = reminder
        self._scheduler: AsyncIOScheduler | None = None
        self._poll_locks: dict[tuple[str, Capability], asyncio.Lock] = {}

    def build_jobs(self) -> list[tuple[str, Capability, int]]:
        jobs = []
        for adapter in self.registry.all():
            for cap in adapter.capabilities:
                secs = interval_for(cap, self.settings)
                if secs > 0:
                    jobs.append((adapter.game_id, cap, secs))
        return jobs

    async def poll_once(self, game_id: str, capability: Capability) -> FetchResult:
        lock = self._poll_locks.setdefault((game_id, capability), asyncio.Lock())
        async with lock:
            return await self._poll_once_locked(game_id, capability)

    async def _poll_once_locked(self, game_id: str, capability: Capability) -> FetchResult:
        adapter = self.registry.get(game_id)
        auth = getattr(adapter, '_auth', None)
        generation = getattr(auth, 'account_generation', lambda _: None)
        original_generation = generation(game_id)
        try:
            result = await adapter.fetch(capability)
        except Exception as exc:
            logger.warning("拉取失败 %s/%s (%s)", game_id, capability.value, type(exc).__name__)
            result = FetchResult(ok=False, error='数据源请求失败，请稍后重试', error_kind='source_error')
        if original_generation != generation(game_id):
            return FetchResult(ok=False, error='账号已切换，请重新刷新', error_kind='account_changed')
        if auth and result.credential_version is not None and result.credential_version != auth.version(game_id):
            return FetchResult(ok=False, error='账号已切换，请重新刷新', error_kind='account_changed')
        if result.error_kind == 'account_changed':
            return result
        if result.ok:
            self.store.save(game_id, capability.value, _serialize(result.payload))
        elif result.error_kind not in ('offline', 'unconfigured'):
            logger.warning("拉取失败 %s/%s: %s（保留旧快照）",
                           game_id, capability.value, result.error)
        status = self.store.record_poll(game_id, capability.value, result)
        if self.reminder:
            # 提醒引擎异常不得影响轮询与快照保存
            try:
                await self.reminder.handle_poll(game_id, adapter.display_name,
                                                capability, result,
                                                failure_count=status['consecutive_failures'])
            except Exception:
                logger.warning("提醒规则评估失败", exc_info=True)
        return result

    def start(self) -> None:
        # misfire_grace_time：错过触发点的任务在 1 小时内仍补跑一次，避免
        # 休眠/挂起恢复后整轮轮询被静默跳过
        self._scheduler = AsyncIOScheduler(job_defaults={"misfire_grace_time": 3600})
        for game_id, cap, secs in self.build_jobs():
            self._scheduler.add_job(
                self.poll_once, IntervalTrigger(seconds=secs),
                args=[game_id, cap], id=f"{game_id}:{cap.value}",
                max_instances=1, coalesce=True)
        self._scheduler.start()

    async def shutdown(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
