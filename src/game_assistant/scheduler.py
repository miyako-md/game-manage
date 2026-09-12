import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult, StaminaInfo

logger = logging.getLogger(__name__)

INTERVAL_ATTRS = {
    Capability.STAMINA: "stamina_seconds",
    Capability.ACTIVITY: "activity_seconds",
    Capability.ANNOUNCEMENT: "announcement_seconds",
    Capability.NEWS: "news_seconds",
    Capability.ACCOUNT: "activity_seconds",
}


def _serialize(payload: Any) -> str:
    if isinstance(payload, list):
        import json
        return json.dumps([p.model_dump(mode="json") if hasattr(p, "model_dump")
                           else p for p in payload], ensure_ascii=False)
    if hasattr(payload, "model_dump_json"):
        return payload.model_dump_json()
    import json
    return json.dumps(payload, ensure_ascii=False)


class PollingScheduler:
    def __init__(self, registry, store, settings: Settings, notifier):
        self.registry = registry
        self.store = store
        self.settings = settings
        self.notifier = notifier
        self._scheduler: AsyncIOScheduler | None = None

    def build_jobs(self) -> list[tuple[str, Capability, int]]:
        jobs = []
        for adapter in self.registry.all():
            for cap in adapter.capabilities:
                secs = getattr(self.settings, INTERVAL_ATTRS[cap])
                if secs > 0:
                    jobs.append((adapter.game_id, cap, secs))
        return jobs

    async def poll_once(self, game_id: str, capability: Capability) -> FetchResult:
        adapter = self.registry.get(game_id)
        result = await adapter.fetch(capability)
        if result.ok:
            self.store.save(game_id, capability.value, _serialize(result.payload))
            if isinstance(result.payload, StaminaInfo):
                await self._maybe_notify_stamina(adapter, result.payload)
        else:
            logger.warning("拉取失败 %s/%s: %s（保留旧快照）",
                           game_id, capability.value, result.error)
        return result

    async def _maybe_notify_stamina(self, adapter: BaseGameAdapter,
                                    s: StaminaInfo) -> None:
        if s.maximum > 0 and s.current >= s.maximum:
            await self.notifier.send(
                f"{adapter.display_name}体力已满",
                f"当前体力 {s.current}/{s.maximum}，快去消耗吧。")

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
