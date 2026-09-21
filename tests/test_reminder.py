from datetime import datetime, timedelta, timezone

from game_assistant.config import Settings
from game_assistant.event_calendar import BEIJING_TZ
from game_assistant.models import Capability, FetchResult, GameEvent, StaminaInfo
from game_assistant.reminder import ReminderEngine
from game_assistant.reminder_store import ReminderDedup


class FakeNotify:
    name = "fake"

    def __init__(self):
        self.sent = []

    async def send(self, title, body):
        self.sent.append((title, body))
        return True


class OffNotify(FakeNotify):
    async def send(self, title, body):
        return False


def _engine(tmp_path, notifier=None, settings=None):
    s = settings or Settings(notify_send_key="")
    return (ReminderEngine(ReminderDedup(str(tmp_path / "t.db")),
                           notifier or FakeNotify(), s), s)


async def test_stamina_full_notifies_once_per_day(tmp_path):
    eng, s = _engine(tmp_path)
    r = FetchResult(ok=True, payload=StaminaInfo(
        current=240, maximum=240, updated_at=datetime.now(timezone.utc)))
    await eng.handle_poll("wuwa", "鸣潮", Capability.STAMINA, r)
    await eng.handle_poll("wuwa", "鸣潮", Capability.STAMINA, r)  # 同日第二次
    assert len(eng.notifier.sent) == 1
    assert "体力已满" in eng.notifier.sent[0][0]


async def test_stamina_threshold_below_full(tmp_path):
    eng, s = _engine(tmp_path)
    r = FetchResult(ok=True, payload=StaminaInfo(
        current=220, maximum=240, updated_at=datetime.now(timezone.utc)))  # ~92%
    await eng.handle_poll("wuwa", "鸣潮", Capability.STAMINA, r)
    assert len(eng.notifier.sent) == 1
    assert "即将回满" in eng.notifier.sent[0][0]


async def test_fail_threshold_triggers_once(tmp_path):
    eng, s = _engine(tmp_path, settings=Settings(fail_notify_threshold=2))
    bad = FetchResult(ok=False, error="LOL 客户端未运行")
    await eng.handle_poll("lol", "英雄联盟", Capability.ACCOUNT, bad)  # 1次，不推
    await eng.handle_poll("lol", "英雄联盟", Capability.ACCOUNT, bad)  # 2次>=阈值，推
    await eng.handle_poll("lol", "英雄联盟", Capability.ACCOUNT, bad)  # 3次>=阈值，但同日 dedup 拦截
    assert len(eng.notifier.sent) == 1
    assert "连续失败" in eng.notifier.sent[0][0]
    # 达到阈值后每次失败都会尝试推送，但 dedup key 含日期 → 同日只发一条
    today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
    assert eng.dedup.already_sent(f"fetch_fail:lol:account:{today}") is True


async def test_success_resets_fail_counter(tmp_path):
    eng, s = _engine(tmp_path, settings=Settings(fail_notify_threshold=2))
    ok = FetchResult(ok=True, payload=StaminaInfo(
        current=10, maximum=240, updated_at=datetime.now(timezone.utc)))
    bad = FetchResult(ok=False, error="x")
    await eng.handle_poll("g", "G", Capability.ACCOUNT, bad)
    await eng.handle_poll("g", "G", Capability.ACCOUNT, ok)   # 清零
    await eng.handle_poll("g", "G", Capability.ACCOUNT, bad)  # 重新计 1
    assert eng.notifier.sent == []


async def test_event_naive_end_at_treated_as_beijing_time(tmp_path):
    eng, s = _engine(tmp_path)
    # 解析层产出 aware UTC+8，naive 理论上不出现；防御归一化后不抛 TypeError。
    # naive_end 被当作北京时间，绝对时间比 UTC now 多 2 天 4 小时 → 向上取整为 3 天。
    naive_end = (datetime.now(timezone.utc)
                 + timedelta(days=2, hours=12)).replace(tzinfo=None)
    r = FetchResult(ok=True, payload=[GameEvent(
        name="naive 活动计时", end_at=naive_end)])
    await eng.handle_poll("wuwa", "鸣潮", Capability.EVENTS, r)
    assert len(eng.notifier.sent) == 1
    assert "naive 活动计时" in eng.notifier.sent[0][1] and "还剩 3 天" in eng.notifier.sent[0][1]


async def test_event_expiry_within_days_notifies_once(tmp_path):
    eng, s = _engine(tmp_path)
    # 2.5 天在 3 天窗口内；展示向上取整为 3 天。
    end = datetime.now(timezone.utc) + timedelta(days=2, hours=12)
    r = FetchResult(ok=True, payload=[GameEvent(
        name="群声共振模拟域", category="战斗活动", end_at=end,
        source_post_id="9001", source_title="3.6版本内容说明")])
    await eng.handle_poll("wuwa", "鸣潮", Capability.EVENTS, r)
    await eng.handle_poll("wuwa", "鸣潮", Capability.EVENTS, r)  # 同 key 去重
    assert len(eng.notifier.sent) == 1
    title, body = eng.notifier.sent[0]
    assert title == "鸣潮活动即将结束"
    assert "群声共振模拟域" in body and "还剩 3 天" in body


async def test_event_dedup_key_is_per_event(tmp_path):
    # 同批多个活动各自独立 key：一次轮询各推一条，去重互不吞并
    eng, s = _engine(tmp_path)
    end = datetime.now(timezone.utc) + timedelta(days=1, hours=12)
    r = FetchResult(ok=True, payload=[
        GameEvent(name="活动甲", end_at=end),
        GameEvent(name="活动乙", end_at=end),
    ])
    await eng.handle_poll("wuwa", "鸣潮", Capability.EVENTS, r)
    assert len(eng.notifier.sent) == 2
    await eng.handle_poll("wuwa", "鸣潮", Capability.EVENTS, r)  # 各自去重
    assert len(eng.notifier.sent) == 2


async def test_event_skipped_when_expired_far_or_undated(tmp_path):
    eng, s = _engine(tmp_path)
    r = FetchResult(ok=True, payload=[
        GameEvent(name="已结束", end_at=datetime.now(timezone.utc) - timedelta(days=1)),
        GameEvent(name="远期", end_at=datetime.now(timezone.utc) + timedelta(days=30)),
        GameEvent(name="无截止", end_at=None),
    ])
    await eng.handle_poll("wuwa", "鸣潮", Capability.EVENTS, r)
    assert eng.notifier.sent == []


async def test_event_remind_disabled_by_zero_window(tmp_path):
    eng, _ = _engine(tmp_path, settings=Settings(activity_remind_days=0,
                                                 notify_send_key=""))
    end = datetime.now(timezone.utc) + timedelta(days=1, hours=2)
    r = FetchResult(ok=True, payload=[GameEvent(name="临期活动", end_at=end)])
    await eng.handle_poll("nte", "异环", Capability.EVENTS, r)
    assert eng.notifier.sent == []


async def test_notifier_off_does_not_mark_sent(tmp_path):
    eng, s = _engine(tmp_path, notifier=OffNotify())
    r = FetchResult(ok=True, payload=StaminaInfo(
        current=240, maximum=240, updated_at=datetime.now(timezone.utc)))
    await eng.handle_poll("wuwa", "鸣潮", Capability.STAMINA, r)
    assert eng.notifier.sent == []
    # SendKey 未配置（send 返回 False）→ 不 mark_sent，配置后同 key 可再发
    assert eng.dedup.already_sent(
        f"stamina_full:wuwa:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}") is False


async def test_deliver_dedup(tmp_path):
    eng, _ = _engine(tmp_path)
    from game_assistant.reminder import Reminder
    assert await eng.deliver(Reminder("t", "b", "k1")) is True
    assert await eng.deliver(Reminder("t", "b", "k1")) is False
