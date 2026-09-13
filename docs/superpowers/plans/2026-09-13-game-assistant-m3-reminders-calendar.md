# 个人游戏资讯助手 M3 实现计划（提醒规则引擎 + 活动日历 + 清理）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现可配置的提醒规则引擎（体力满/体力阈值/活动临期/连续拉取失败，带去重），仪表盘增加活动日历视图，并完成 M2 审查遗留的清理项。

**Architecture:** 提醒 = 规则引擎（`reminder.py`）在每次轮询后评估：规则产出 `Reminder(title, body, dedup_key)`，引擎经 SQLite 去重表过滤后交 Notifier（微信推送；未配置 key 时静默跳过——既有行为）。调度器 `poll_once` 成功/失败都喂给引擎，替代 M1 时代的 `_maybe_notify_stamina` 简化版。日历视图为纯前端组件（按开始日期分组的时间线），无新 API。

**Tech Stack:** 既有栈不变（FastAPI/APScheduler/httpx/SQLite/Vue3）。无新依赖。

**Spec:** `docs/需求文档.md` §7 M3 里程碑（提醒规则引擎、活动日历视图）+ M2 最终审查积压清单。**范围裁定**：掌盟 Cookie 渠道评估（查任意玩家）挪至 M4，本计划不含。

## Global Constraints

- 既有全部约束继续生效（离线测试、凭据治理、conventional commits、失败不覆盖快照、默认端口 8010）。
- **去重策略**（写入代码注释与 README）：体力满/阈值 → 每自然日最多一次（dedup_key 含日期）；活动临期 → 每个活动（标题+结束日）一次；连续拉取失败 → 达到阈值当日一次。
- **提醒开关默认值**（均可 config.toml 覆盖）：`notify_stamina_full=true`、`stamina_threshold_percent=90`（0=关）、`activity_remind_days=3`（0=关）、`fail_notify_threshold=3`（0=关）。
- SendKey 仍未配置——所有提醒路径的验收 = 单元测试 + 日志/状态断言；真实微信推送仍待用户提供 SendKey（README 说明，不阻塞）。
- 阈值规则与满体力规则不同时重复触发：阈值通知条件含 `current < maximum`。
- 活动临期判断用 aware UTC 的 now 与 ActivityItem.end_at 比较；`remaining_days = (end_at - now).days`（可为 0 当日到期；<0 已结束不提醒）。
- M1 既有测试 `test_poll_once_saves_snapshot_and_notifies_full` 的行为契约保留（体力满会触发通知），但断言路径改为经引擎——Task 3 会修改该测试，属计划钦定。

---

### Task 1: 配置扩展 + 提醒去重存储

**Files:**
- Modify: `src/game_assistant/config.py`, `config.example.toml`, `README.md`（配置表补 4 行）
- Create: `src/game_assistant/reminder_store.py`
- Test: `tests/test_reminder_store.py`

**Interfaces:**
- Settings 新字段（含默认值）：`notify_stamina_full: bool = True`、`stamina_threshold_percent: int = 90`、`activity_remind_days: int = 3`、`fail_notify_threshold: int = 3`。
- `ReminderDedup(db_path: str)`：独立 sqlite 连接（同 assistant.db文件，低频写无冲突），表 `notified(rule_key TEXT PRIMARY KEY, sent_at TEXT)`；`already_sent(rule_key: str) -> bool`；`mark_sent(rule_key: str) -> None`（记录 UTC now）。

- [ ] **Step 1: 写失败测试** `tests/test_reminder_store.py`：

```python
from game_assistant.config import Settings
from game_assistant.reminder_store import ReminderDedup


def test_config_defaults():
    s = Settings(notify_send_key="")
    assert s.notify_stamina_full is True
    assert s.stamina_threshold_percent == 90
    assert s.activity_remind_days == 3
    assert s.fail_notify_threshold == 3


def test_dedup_roundtrip(tmp_path):
    d = ReminderDedup(str(tmp_path / "t.db"))
    assert d.already_sent("k1") is False
    d.mark_sent("k1")
    assert d.already_sent("k1") is True
    assert d.already_sent("k2") is False


def test_dedup_persists_across_instances(tmp_path):
    db = str(tmp_path / "t.db")
    ReminderDedup(db).mark_sent("k1")
    assert ReminderDedup(db).already_sent("k1") is True
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/test_reminder_store.py -v` → FAIL

- [ ] **Step 3: 实现** — config.py 四字段（env_prefix GA_ 已生效，无需额外处理）；config.example.toml 提醒分组注释 + 四项；README 配置表补 4 行（放 notify_send_key 之后）；reminder_store.py：

```python
import sqlite3
import threading
from datetime import datetime, timezone


class ReminderDedup:
    """提醒去重表。dedup_key 语义见 reminder.py 各规则注释。"""

    def __init__(self, db_path: str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS notified ("
            " rule_key TEXT PRIMARY KEY, sent_at TEXT NOT NULL)")
        self._conn.commit()

    def already_sent(self, rule_key: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM notified WHERE rule_key = ?", (rule_key,)).fetchone()
        return row is not None

    def mark_sent(self, rule_key: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO notified (rule_key, sent_at) VALUES (?, ?)"
                " ON CONFLICT(rule_key) DO NOTHING",
                (rule_key, datetime.now(timezone.utc).isoformat()))
            self._conn.commit()
```

- [ ] **Step 4: 全量测试** — Run: `.venv/Scripts/python.exe -m pytest -q` → 87 passed（84+3）

- [ ] **Step 5: 提交** — `git add src/game_assistant config.example.toml README.md tests/test_reminder_store.py && git commit -m "feat: reminder config fields and dedup store"`

---

### Task 2: 提醒规则引擎

**Files:**
- Create: `src/game_assistant/reminder.py`
- Test: `tests/test_reminder.py`

**Interfaces:**
- `Reminder(title: str, body: str, dedup_key: str)`（dataclass）。
- `ReminderEngine(dedup: ReminderDedup, notifier)`：
  - `async deliver(self, r: Reminder) -> bool` — already_sent → False（不发）；`await notifier.send(title, body)` 成功 → mark_sent 返回 True；失败（notifier 返回 False，如 SendKey 未配置）→ 不 mark_sent 返回 False
  - `async handle_poll(self, game_id: str, display_name: str, capability: Capability, result: FetchResult) -> None` — 规则评估入口（成功与失败都调用）
- 规则（全部在 handle_poll 内）：
  1. **连续失败**：维护内存计数 `self._fail_counts[(game_id, capability.value)]`；失败 +1，成功清零。计数恰好达到 `settings.fail_notify_threshold`（>0）时 → Reminder(f"{display_name} 数据拉取连续失败", f"{capability.value}: {result.error}", f"fetch_fail:{game_id}:{capability.value}:{today}")——恰好等于阈值才触发（避免每次失败都推）。
  2. **体力满**：payload 为 StaminaInfo 且 `settings.notify_stamina_full` 且 `0 < maximum <= current`（原文条件：maximum > 0 and current >= maximum）→ Reminder(f"{display_name}体力已满", f"当前体力 {current}/{maximum}，快去消耗吧。", f"stamina_full:{game_id}:{today}")。
  3. **体力阈值**：`settings.stamina_threshold_percent` 在 1..99 且 payload StaminaInfo 且 `current >= maximum * p / 100` 且 `current < maximum` → Reminder(f"{display_name}体力即将回满", f"当前体力 {current}/{maximum}（≥{p}%）。", f"stamina_thres:{game_id}:{today}")。
  4. **活动临期**：payload 为 list 且首元素为 ActivityItem 且 `settings.activity_remind_days > 0` → 对每个 `end_at` 非空的活动：`remaining = (end_at - now).days`，`0 <= remaining <= activity_remind_days` → Reminder(f"{display_name}活动即将结束", f"「{title}」还剩 {remaining} 天（{end_at:%m-%d %H:%M} 结束）。", f"activity_exp:{game_id}:{md5(title + '|' + end_at.isoformat())前12位}")。
  - `today = datetime.now(timezone.utc).strftime("%Y-%m-%d")`；`now = datetime.now(timezone.utc)`。
- 注意：payload 列表元素类型判断用 `isinstance(payload, list) and payload and isinstance(payload[0], ActivityItem)`（StaminaInfo 是单对象，不会混淆）。

- [ ] **Step 1: 写失败测试** `tests/test_reminder.py`：

```python
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
    return (ReminderEngine(ReminderDedup(str(tmp_path / "t.db")),
                           notifier or FakeNotify()),
            settings or Settings(notify_send_key=""))


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
    end = datetime.now(timezone.utc) + timedelta(days=2)
    r = FetchResult(ok=True, payload=[ActivityItem(
        title="版本限时活动", start_at=None, end_at=end)])
    await eng.handle_poll("wuwa", "鸣潮", Capability.ACTIVITY, r)
    await eng.handle_poll("wuwa", "鸣潮", Capability.ACTIVITY, r)  # 去重
    assert len(eng.notifier.sent) == 1
    assert "版本限时活动" in eng.notifier.sent[0][1] and "还剩 2 天" in eng.notifier.sent[0][1]


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
```

- [ ] **Step 2: 运行确认失败** → FAIL

- [ ] **Step 3: 实现** `reminder.py`（按 Interfaces 与规则注释；`import hashlib` 用于活动 key）：

```python
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from game_assistant.config import Settings
from game_assistant.models import ActivityItem, Capability, FetchResult, StaminaInfo
from game_assistant.reminder_store import ReminderDedup

logger = logging.getLogger(__name__)


@dataclass
class Reminder:
    title: str
    body: str
    dedup_key: str


class ReminderEngine:
    """轮询后提醒规则评估。去重语义见 Global Constraints。"""

    def __init__(self, dedup: ReminderDedup, notifier):
        self.dedup = dedup
        self.notifier = notifier
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
        # 规则 1：连续拉取失败
        key = (game_id, capability.value)
        if not result.ok:
            self._fail_counts[key] = self._fail_counts.get(key, 0) + 1
            n = settings.fail_notify_threshold
            if n > 0 and self._fail_counts[key] == n:
                await self.deliver(Reminder(
                    f"{display_name} 数据拉取连续失败",
                    f"{capability.value}: {result.error}",
                    f"fetch_fail:{game_id}:{capability.value}:{today}"))
            return
        self._fail_counts.pop(key, None)
        # 规则 2/3：体力
        if isinstance(result.payload, StaminaInfo):
            await self._stamina_rules(game_id, display_name, result.payload, today, settings)
        # 规则 4：活动临期
        if (isinstance(result.payload, list) and result.payload
                and isinstance(result.payload[0], ActivityItem)):
            await self._activity_rule(game_id, display_name, result.payload, settings)

    async def _stamina_rules(self, game_id, display_name, s: StaminaInfo,
                             today, settings: Settings) -> None:
        if settings.notify_stamina_full and s.maximum > 0 and s.current >= s.maximum:
            await self.deliver(Reminder(
                f"{display_name}体力已满",
                f"当前体力 {s.current}/{s.maximum}，快去消耗吧。",
                f"stamina_full:{game_id}:{today}"))
            return
        p = settings.stamina_threshold_percent
        if 1 <= p <= 99 and s.maximum > 0 and s.current >= s.maximum * p / 100 \
                and s.current < s.maximum:
            await self.deliver(Reminder(
                f"{display_name}体力即将回满",
                f"当前体力 {s.current}/{s.maximum}（≥{p}%）。",
                f"stamina_thres:{game_id}:{today}"))

    async def _activity_rule(self, game_id, display_name, items, settings: Settings) -> None:
        if settings.activity_remind_days <= 0:
            return
        now = datetime.now(timezone.utc)
        for it in items:
            if it.end_at is None:
                continue
            remaining = (it.end_at - now).days
            if not (0 <= remaining <= settings.activity_remind_days):
                continue
            raw = f"{it.title}|{it.end_at.isoformat()}"
            key12 = hashlib.md5(raw.encode()).hexdigest()[:12]
            await self.deliver(Reminder(
                f"{display_name}活动即将结束",
                f"「{it.title}」还剩 {remaining} 天（{it.end_at:%m-%d %H:%M} 结束）。",
                f"activity_exp:{game_id}:{key12}"))
```

注意：engine 需要 settings——构造签名改为 `ReminderEngine(dedup, notifier, settings: Settings)`，测试 helper 相应传入（`_engine` 里 `Settings(notify_send_key="")` 或自定义 settings 都传给构造器），`handle_poll` 用 `self._settings`。测试代码按此调整（`_engine` 返回的 eng 已带 settings）。

- [ ] **Step 4: 全量测试** → 94 passed（87+7）
- [ ] **Step 5: 提交** — `git add src/game_assistant/reminder.py tests/test_reminder.py && git commit -m "feat: reminder engine with stamina/activity/failure rules and dedup"`

---

### Task 3: 调度器/应用接线

**Files:**
- Modify: `src/game_assistant/scheduler.py`, `src/game_assistant/api.py`, `tests/test_scheduler.py`, `tests/test_lifecycle.py`
- Test: `tests/test_scheduler.py`（修改既有）

**Interfaces:**
- `PollingScheduler(registry, store, settings, notifier, reminder=None)` — 新增可选参数；`poll_once` 成功与失败后 `if self.reminder: await self.reminder.handle_poll(game_id, adapter.display_name, capability, result)`；**删除** `_maybe_notify_stamina` 及其调用。
- `create_app`：scheduler 为 None 且 start_scheduler 时，构建顺序 notifier → engine（`ReminderEngine(ReminderDedup(settings.db_path), notifier, settings)`）→ scheduler（传入 engine）。注入 scheduler 的测试路径不受影响。
- 【计划钦定】既有测试 `test_poll_once_saves_snapshot_and_notifies_full` 改造：构造 engine（tmp dedup + FakeNotify + Settings）传入 scheduler，断言通知经引擎发出（FakeNotify.sent 有"体力已满"）且同日第二次 poll 不再发（去重生效）——比原断言更强。

- [ ] **Step 1: 修改测试（先失败）** `tests/test_scheduler.py`：

```python
# 文件顶部补充
from game_assistant.config import Settings
from game_assistant.reminder import ReminderEngine
from game_assistant.reminder_store import ReminderDedup

# _sched helper 增加 reminder 参数并传入 PollingScheduler：
def _sched(tmp_path, settings=None, reminder=None):
    reg = ...  # 原样
    store = SnapshotStore(str(tmp_path / "t.db"))
    s = settings or Settings()
    sched = PollingScheduler(reg, store, s, FakeNotify(), reminder=reminder)
    return sched, store

# 替换 test_poll_once_saves_snapshot_and_notifies_full：
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
```

（其余测试 `_sched` 不传 reminder → None → 行为不变；`test_poll_failure_keeps_old_snapshot` 照旧。）

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/test_scheduler.py -v` → 新断言 FAIL（engine 尚未接线/签名不符）

- [ ] **Step 3: 实现** — scheduler.py：构造器加 `reminder=None`（存 `self.reminder`）；`poll_once` 在 ok/else 分支后统一追加：

```python
        if self.reminder:
            await self.reminder.handle_poll(game_id, adapter.display_name,
                                            capability, result)
```

删除 `_maybe_notify_stamina` 方法与原调用点。api.py：create_app 内 scheduler 构建处改为：

```python
    if scheduler is None and start_scheduler:
        from game_assistant.reminder import ReminderEngine
        from game_assistant.reminder_store import ReminderDedup
        engine = ReminderEngine(ReminderDedup(settings.db_path), notifier, settings)
        scheduler = PollingScheduler(app.state.registry, app.state.store,
                                     settings, notifier, reminder=engine)
```

（import 放文件顶部，遵循仓库风格。）

- [ ] **Step 4: 全量测试** → 95 passed（改造后的 scheduler 测试 + 其余零回归；test_lifecycle 不受影响——注入 scheduler 路径 reminder=None，refresh 照旧）
- [ ] **Step 5: 提交** — `git add src/game_assistant tests && git commit -m "feat: wire reminder engine into polling scheduler"`

---

### Task 4: 活动日历视图（前端）

**Files:**
- Modify: `frontend/src/components/ActivityList.vue`

**Interfaces:**
- 卡片头部加视图切换（两个小按钮"列表/日历"，默认列表，激活态高亮）。
- 日历视图 = 按开始日期分组的时间线：`rows` 中 `start_at` 非空者按 `start_at` 的日期分组（同日多条归一组），组头显示"MM月DD日 周X"，组内条目复用列表行的标题/起止时间/剩余天数徽标；`start_at` 为空的活动归入末尾"未定日期"组。
- 排序：组按日期升序；"未定日期"最后。
- 复用既有徽标逻辑（剩余天数 <0 已结束 / ≤3 红色）与 .item-list 样式；不引入新依赖。

- [ ] **Step 1: 实现切换与时间线**（读现有 ActivityList.vue 保持风格；分组 computed：`const groups = computed(() => {...})`，日期键用本地时区 `new Date(it.start_at)`）
- [ ] **Step 2: 构建验证** — Run: `cd frontend && npm run build` → 成功
- [ ] **Step 3: 手动冒烟** — dev 起后端+前端，活动板块可见"列表/日历"切换（无鸣潮 token 时两视图均为"暂无数据"占位，切换不报错即可）
- [ ] **Step 4: 提交** — `git add frontend/src && git commit -m "feat: activity calendar timeline view with list toggle"`

---

### Task 5: 清理批次（M2 审查积压）

**Files:**
- Modify: `src/game_assistant/adapters/league_of_legends/lcu_client.py`, `adapter.py`, `lol_news.py`, `frontend/src/style.css`, `frontend/src/components/MatchList.vue`, `README.md`
- Test: `tests/adapters/test_lcu_discovery.py`（补 2 测试）, `tests/adapters/test_lol_news.py`（时区断言）, `tests/adapters/test_lol_adapter.py`（如需）

**Interfaces:**
- `LcuClient` 增加 `async aclose()` 与 `async __aenter__/__aexit__`；adapter 的 fetch_account/fetch_match 改 `async with LcuClient(...) as client:`（`_get_lcu` 拆为"发现凭据 → 返回 (port, token) 或抛错"的 `_discover()` + 调用处构造 client）。
- `lol_news.py` 时间规范化：解析出的 naive 日期时间按**北京时间（UTC+8）**补 tzinfo → aware（`sIdxTime` 为北京时间）；`parse_news_json` 类型标注 `dict | list`。
- style.css 增加 `--success/--success-bg` 变量；MatchList 徽标改用变量。
- README 配置表 account/match 行为说明一句（"复用 activity_seconds 间隔"）。
- lcu_discovery 补 2 测试：①`find_lockfile_credentials` 空字段跳过（lockfile `1234::pass:https` → None）+ 实现加校验 `if not parts[1] or not parts[2]: continue`；②`discover_lcu_credentials` 在 fake psutil（monkeypatch sys.modules 注入带 `process_iter` 的假模块，返回一个含 LCU 参数的假进程对象）下返回凭据。

- [ ] **Step 1: 写失败测试**（discovery 空 field + fake psutil；news aware 断言 `published_at.tzinfo is not None and published_at.utcoffset() == timedelta(hours=8)`）
- [ ] **Step 2: 确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/adapters/test_lcu_discovery.py tests/adapters/test_lol_news.py -v` → 新断言 FAIL
- [ ] **Step 3: 实现**（按 Interfaces；adapter 改 async with 后确认既有 LCU 测试仍过——respx mock 与 client 生命周期无关）
- [ ] **Step 4: 全量测试 + build** → 全过（约 97+）
- [ ] **Step 5: 提交** — `git add src tests frontend/src README.md && git commit -m "refactor: m2 review backlog (lifecycle close, tz normalization, success color, discovery tests)"`

---

### Task 6: E2E + README 更新 + 回归

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 启动验证** — 后端 8010 + 前端 dev：`/api/games` 两游戏照旧；POST refresh LoL → announcement/news ok=true；account/match "LOL 客户端未运行"（提醒引擎在达到阈值时会产生"连续失败"提醒——当前 SendKey 未配置，`deliver` 返回 False 不 mark_sent，日志可见"提醒渠道未启用"，这正是验收点）
- [ ] **Step 2: 日历视图冒烟** — 活动卡片切换"列表/日历"不报错（鸣潮 token 未配置，数据为空属预期）
- [ ] **Step 3: README 更新** — 新"提醒规则"小节：四规则触发条件与去重策略（体力满每日一次、阈值 90% 每日一次、活动结束前 3 天每活动一次、连续失败 3 次每日一次）、全部可 config.toml 覆盖（列 4 个键名）、SendKey 配置后即真实推送（未配置时仪表盘状态条 + 日志可见跳过）；活动日历视图说明一句
- [ ] **Step 4: 全量回归** — `.venv/Scripts/python.exe -m pytest -q` 全过 + `npm run build` 成功
- [ ] **Step 5: 提交** — `git add README.md && git commit -m "docs: m3 reminder rules and calendar view"`

---

## 后续计划（不在本计划内）

- **M4 候选**：掌盟 Cookie 渠道评估（查任意玩家战绩）、鸣潮每日签到、抽卡记录分析、英雄图标映射、中文段位映射、第二轮游戏评估。
- **用户侧待办**：LOL 客户端运行时人工验证账号/战绩（ranked 端点校准）；库街区 token接入鸣潮真实数据；Server酱 SendKey 启用真实推送。
