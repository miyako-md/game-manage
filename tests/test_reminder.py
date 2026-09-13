from datetime import datetime, timedelta, timezone

from game_assistant.config import Settings
from game_assistant.models import ActivityItem, Capability, FetchResult, StaminaInfo
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
    await eng.handle_poll("lol", "英雄联盟", Capability.ACCOUNT, bad)  # 2次=阈值，推
    await eng.handle_poll("lol", "英雄联盟", Capability.ACCOUNT, bad)  # 3次，不再推
    assert len(eng.notifier.sent) == 1
    assert "连续失败" in eng.notifier.sent[0][0]


async def test_success_resets_fail_counter(tmp_path):
    eng, s = _engine(tmp_path, settings=Settings(fail_notify_threshold=2))
    ok = FetchResult(ok=True, payload=StaminaInfo(
        current=10, maximum=240, updated_at=datetime.now(timezone.utc)))
    bad = FetchResult(ok=False, error="x")
    await eng.handle_poll("g", "G", Capability.ACCOUNT, bad)
    await eng.handle_poll("g", "G", Capability.ACCOUNT, ok)   # 清零
    await eng.handle_poll("g", "G", Capability.ACCOUNT, bad)  # 重新计 1
    assert eng.notifier.sent == []


async def test_activity_expiry_within_days(tmp_path):
    eng, s = _engine(tmp_path)
    # +12h 余量：(end_at - now).days 向下取整，时钟推进不能让 remaining 掉到 1
    end = datetime.now(timezone.utc) + timedelta(days=2, hours=12)
    r = FetchResult(ok=True, payload=[ActivityItem(
        title="版本限时活动", start_at=None, end_at=end)])
    await eng.handle_poll("wuwa", "鸣潮", Capability.ACTIVITY, r)
    await eng.handle_poll("wuwa", "鸣潮", Capability.ACTIVITY, r)  # 去重
    assert len(eng.notifier.sent) == 1
    assert "版本限时活动" in eng.notifier.sent[0][1] and "还剩 2 天" in eng.notifier.sent[0][1]


async def test_activity_naive_end_at_treated_as_beijing_time(tmp_path):
    eng, s = _engine(tmp_path)
    # 鸣潮来源可能产出 naive datetime；按北京时间（UTC+8）归一化后不抛 TypeError。
    # naive_end 被当作北京时间，绝对时间比 UTC now 多 2 天 4 小时 → remaining = 2。
    naive_end = (datetime.now(timezone.utc)
                 + timedelta(days=2, hours=12)).replace(tzinfo=None)
    r = FetchResult(ok=True, payload=[ActivityItem(
        title="naive 活动计时", start_at=None, end_at=naive_end)])
    await eng.handle_poll("wuwa", "鸣潮", Capability.ACTIVITY, r)
    assert len(eng.notifier.sent) == 1
    assert "naive 活动计时" in eng.notifier.sent[0][1] and "还剩 2 天" in eng.notifier.sent[0][1]


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
