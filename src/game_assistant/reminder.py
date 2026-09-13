from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from game_assistant.config import Settings
from game_assistant.models import (
    Capability, FetchResult, GameEvent, StaminaInfo, VersionActivity,
)
from game_assistant.reminder_store import ReminderDedup


@dataclass
class Reminder:
    title: str
    body: str
    dedup_key: str


class ReminderEngine:
    """轮询后提醒规则评估。去重语义见 Global Constraints。"""

    def __init__(self, dedup: ReminderDedup, notifier,
                 settings: Settings) -> None:
        self.dedup = dedup
        self.notifier = notifier
        self._settings = settings
        self._fail_counts: dict[tuple[str, str], int] = {}

    async def deliver(self, r: Reminder) -> bool:
        if self.dedup.already_sent(r.dedup_key):
            return False
        if not await self.notifier.send(r.title, r.body):
            return False  # 未配置 SendKey 等；不 mark_sent，配置后可再发
        self.dedup.mark_sent(r.dedup_key)
        return True

    async def handle_poll(self, game_id: str, display_name: str,
                          capability: Capability, result: FetchResult) -> None:
        settings = self._settings
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # 规则 1：连续拉取失败（达到阈值后每次失败都会尝试推送，由当日去重限流；成功清零）
        key = (game_id, capability.value)
        if not result.ok:
            self._fail_counts[key] = self._fail_counts.get(key, 0) + 1
            n = settings.fail_notify_threshold
            if n > 0 and self._fail_counts[key] >= n:
                await self.deliver(Reminder(
                    f"{display_name} 数据拉取连续失败",
                    f"{capability.value}: {result.error}",
                    f"fetch_fail:{game_id}:{capability.value}:{today}"))
            return
        self._fail_counts.pop(key, None)
        # 规则 2/3：体力满 / 体力阈值
        if isinstance(result.payload, StaminaInfo):
            await self._stamina_rules(game_id, display_name, result.payload,
                                      today, settings)
        # 规则 4：版本活动临期
        if isinstance(result.payload, VersionActivity):
            await self._activity_rule(game_id, display_name, result.payload,
                                      settings)
        # 规则 5：活动日历临期（版本公告解析出的 list[GameEvent]，逐活动评估）
        if isinstance(result.payload, list) and result.payload and \
                all(isinstance(e, GameEvent) for e in result.payload):
            await self._events_rule(game_id, display_name, result.payload,
                                    settings)

    async def _stamina_rules(self, game_id: str, display_name: str,
                             s: StaminaInfo, today: str,
                             settings: Settings) -> None:
        # 规则 2：体力满
        if settings.notify_stamina_full and s.maximum > 0 and s.current >= s.maximum:
            await self.deliver(Reminder(
                f"{display_name}体力已满",
                f"当前体力 {s.current}/{s.maximum}，快去消耗吧。",
                f"stamina_full:{game_id}:{today}"))
            return
        # 规则 3：体力阈值（current < maximum 避免与体力满重复）
        p = settings.stamina_threshold_percent
        if 1 <= p <= 99 and s.maximum > 0 and s.current >= s.maximum * p / 100 \
                and s.current < s.maximum:
            await self.deliver(Reminder(
                f"{display_name}体力即将回满",
                f"当前体力 {s.current}/{s.maximum}（≥{p}%）。",
                f"stamina_thres:{game_id}:{today}"))

    async def _activity_rule(self, game_id: str, display_name: str,
                             act: VersionActivity,
                             settings: Settings) -> None:
        # 规则 4：版本活动临期（enabled + 结束前 0~N 天；key 含 title+end_at 的
        # md5 前 12 位，跨日不重复推）
        if settings.activity_remind_days <= 0:
            return
        if not act.enabled or act.end_at is None:
            return
        now = datetime.now(timezone.utc)
        # 解析层产出 aware UTC，naive 理论上不会出现；保留归一化防御防 TypeError
        end = act.end_at if act.end_at.tzinfo else act.end_at.replace(
            tzinfo=timezone(timedelta(hours=8)))
        remaining = (end - now).days
        if not (0 <= remaining <= settings.activity_remind_days):
            return
        raw = f"{act.title}|{end.isoformat()}"
        key12 = hashlib.md5(raw.encode()).hexdigest()[:12]
        await self.deliver(Reminder(
            f"{display_name}活动即将结束",
            f"「{act.title}」还剩 {remaining} 天（{end:%m-%d %H:%M} 结束）。",
            f"activity_exp:{game_id}:{key12}"))

    async def _events_rule(self, game_id: str, display_name: str,
                           events: list[GameEvent],
                           settings: Settings) -> None:
        # 规则 5：活动日历临期（与规则 4 同款窗口；逐活动评估，key 含
        # name+end_at 的 md5 前 12 位，跨日不重复推；前缀 event_exp 与
        # 版本活动的 activity_exp 区分）
        if settings.activity_remind_days <= 0:
            return
        now = datetime.now(timezone.utc)
        for ev in events:
            if ev.end_at is None:
                continue
            # 解析层产出 aware UTC+8，naive 理论上不会出现；保留归一化防御
            end = ev.end_at if ev.end_at.tzinfo else ev.end_at.replace(
                tzinfo=timezone(timedelta(hours=8)))
            remaining = (end - now).days
            if not (0 <= remaining <= settings.activity_remind_days):
                continue
            raw = f"{ev.name}|{end.isoformat()}"
            key12 = hashlib.md5(raw.encode()).hexdigest()[:12]
            await self.deliver(Reminder(
                f"{display_name}活动即将结束",
                f"「{ev.name}」还剩 {remaining} 天（{end:%m-%d %H:%M} 结束）。",
                f"event_exp:{game_id}:{key12}"))
