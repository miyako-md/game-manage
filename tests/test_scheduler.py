import json

from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult, StaminaInfo
from game_assistant.reminder import ReminderEngine
from game_assistant.reminder_store import ReminderDedup
from game_assistant.scheduler import PollingScheduler
from game_assistant.snapshots import SnapshotStore


class FakeNotify:
    name = "fake"
    sent = []

    async def send(self, title, body):
        FakeNotify.sent.append((title, body))
        return True


class WuwaLike(BaseGameAdapter):
    game_id = "wuwa"
    display_name = "鸣潮"
    section = "mobile"
    capabilities = [Capability.STAMINA, Capability.ACTIVITY]

    def __init__(self):
        self.credentials_configured = True

    async def fetch_stamina(self) -> FetchResult:
        return FetchResult(ok=True, payload=StaminaInfo(
            current=240, maximum=240, expected_full_at=None,
            updated_at="2026-09-12T12:00:00"))

    async def fetch_activity(self) -> FetchResult:
        return FetchResult(ok=False, error="接口挂了")


def _sched(tmp_path, settings=None, reminder=None):
    reg = type("R", (), {"all": lambda self: [WuwaLike()],
                         "get": lambda self, gid: WuwaLike()})()
    store = SnapshotStore(str(tmp_path / "t.db"))
    s = settings or Settings()
    sched = PollingScheduler(reg, store, s, FakeNotify(), reminder=reminder)
    return sched, store


async def test_poll_once_saves_snapshot_and_notifies_full(tmp_path):
    eng = ReminderEngine(ReminderDedup(str(tmp_path / "r.db")),
                         FakeNotify(), Settings(notify_send_key=""))
    sched, store = _sched(tmp_path, reminder=eng)
    r = await sched.poll_once("wuwa", Capability.STAMINA)
    assert r.ok is True
    payload = json.loads(store.get("wuwa", "stamina")["payload"])
    assert payload["current"] == 240
    assert any("体力已满" in t for t, _ in eng.notifier.sent)  # 经引擎触发
    await sched.poll_once("wuwa", Capability.STAMINA)          # 同日去重
    assert len(eng.notifier.sent) == 1


async def test_poll_once_survives_reminder_engine_error(tmp_path):
    class RaisingEngine:
        async def handle_poll(self, *args, **kwargs):
            raise RuntimeError("提醒引擎炸了")

    sched, store = _sched(tmp_path, reminder=RaisingEngine())
    r = await sched.poll_once("wuwa", Capability.STAMINA)
    assert r.ok is True
    snap = store.get("wuwa", "stamina")
    assert snap is not None
    assert json.loads(snap["payload"])["current"] == 240


async def test_poll_failure_keeps_old_snapshot(tmp_path):
    sched, store = _sched(tmp_path)
    await sched.poll_once("wuwa", Capability.ACTIVITY)  # 失败
    assert store.get("wuwa", "activity") is None


def test_build_jobs_uses_intervals(tmp_path):
    sched, _ = _sched(tmp_path, Settings(stamina_seconds=0, activity_seconds=60))
    jobs = {cap: secs for _, cap, secs in sched.build_jobs()}
    assert Capability.STAMINA not in jobs      # 间隔<=0 不调度
    assert jobs[Capability.ACTIVITY] == 60
