# 个人游戏资讯助手 M0+M1 实现计划（框架 + 鸣潮适配器）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建适配器架构的游戏资讯助手框架（调度轮询 + SQLite 缓存 + Web 仪表盘 + 微信推送接口），并实现首个适配器——鸣潮（账号/体力/活动/公告），最终仪表盘可展示鸣潮数据。

**Architecture:** 后端 Python（FastAPI）以"游戏适配器"模式组织：每款游戏一个 Adapter 声明其能力（account/stamina/activity/announcement），APScheduler 按能力配置的间隔轮询，结果以快照形式存 SQLite，路由读快照给前端。通知走 Notifier 接口，首发实现微信推送（Server酱/PushPlus），SendKey 未配置时静默跳过。前端 Vue3 SPA，分 PC/手游双板块。

**Tech Stack:** Python ≥3.11、FastAPI、httpx、APScheduler 3.x、pydantic-settings（TOML 配置）、SQLite（标准库 sqlite3）、pytest + respx（全部测试离线）、Vue3 + Vite。

**Spec:** `docs/需求文档.md`（v1.0，2026-09-12）— 本计划依据其第 2/3.2/5/6/8 节。M2（LoL）/M3（提醒规则+日历）/M4 后续另出计划。

## Global Constraints

- Python ≥ 3.11；工作目录 `C:\Zcode\game-manage`，Windows + Git Bash，路径用正斜杠。
- 轮询默认值（全局约束）：体力 300 秒、活动 3600 秒、公告 3600 秒、资讯 14400 秒，均可在 config.toml 覆盖。
- 所有 HTTP 测试用 respx mock，**任何测试不得访问真实网络**。
- 凭据只存 `config.toml`（gitignore），代码、测试、日志中不得出现真实凭据。
- 提交遵循 conventional commits（feat/test/chore/docs 前缀），每个任务至少一次提交。
- 微信推送功能实现但暂不配置：`send_key` 为空时 `send()` 直接返回 False 并记日志，不得抛异常、不得发 HTTP 请求。
- 适配器拉取失败（凭据失效/接口变更）不得覆盖已有快照，只记录错误；快照带 `fetched_at` 时间戳供前端展示新旧。
- 未安装 Python 3.11+ 时先安装再继续（`python --version` 验证）。

---

### Task 1: 项目初始化与 FastAPI 冒烟

**Files:**
- Create: `.gitignore`, `pyproject.toml`, `src/game_assistant/__init__.py`, `src/game_assistant/main.py`
- Test: `tests/test_health.py`

**Interfaces:**
- Produces: FastAPI 实例 `app`（后续 Task 8/9 会重构为 `create_app()` 工厂）；`/api/health` 返回 `{"status": "ok"}`。

- [ ] **Step 1: 初始化仓库与忽略规则**

```bash
cd /c/Zcode/game-manage
git init
```

`.gitignore` 内容：

```
__pycache__/
*.pyc
.venv/
config.toml
data/
node_modules/
dist/
.pytest_cache/
```

- [ ] **Step 2: 写 pyproject.toml**

```toml
[project]
name = "game-assistant"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.110",
  "uvicorn[standard]>=0.29",
  "httpx>=0.27",
  "apscheduler>=3.10,<4",
  "pydantic>=2.7",
  "pydantic-settings>=2.4",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "respx>=0.21"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 3: 建环境并安装**

```bash
python --version   # 需 >= 3.11
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

- [ ] **Step 4: 写失败测试** `tests/test_health.py`：

```python
from fastapi.testclient import TestClient
from game_assistant.main import app


def test_health():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 5: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_health.py -v`
Expected: FAIL（`game_assistant.main` 不存在）

- [ ] **Step 6: 最小实现**

`src/game_assistant/__init__.py` 空文件；`src/game_assistant/main.py`：

```python
from fastapi import FastAPI

app = FastAPI(title="Game Assistant")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 7: 运行确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add .gitignore pyproject.toml src tests
git commit -m "feat: init project with FastAPI smoke test"
```

---

### Task 2: 配置中心（TOML + pydantic-settings）

**Files:**
- Create: `src/game_assistant/config.py`, `config.example.toml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings` 类，字段：`app_host: str = "127.0.0.1"`、`app_port: int = 8000`、`db_path: str = "data/assistant.db"`、`stamina_seconds: int = 300`、`activity_seconds: int = 3600`、`announcement_seconds: int = 3600`、`news_seconds: int = 14400`、`notify_provider: str = "serverchan"`、`notify_send_key: str = ""`、`wuwa_enabled: bool = True`、`wuwa_token: str = ""`、`wuwa_user_id: str = ""`。类方法 `Settings.load(path: str = "config.toml") -> Settings`（文件不存在时返回全默认值）。

- [ ] **Step 1: 写失败测试** `tests/test_config.py`：

```python
from game_assistant.config import Settings


def test_defaults_when_no_file(tmp_path):
    s = Settings.load(str(tmp_path / "missing.toml"))
    assert s.stamina_seconds == 300
    assert s.activity_seconds == 3600
    assert s.news_seconds == 14400
    assert s.notify_send_key == ""
    assert s.wuwa_enabled is True


def test_load_from_toml(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'stamina_seconds = 120\n'
        'notify_send_key = "abc123"\n'
        'wuwa_token = "tok"\n',
        encoding="utf-8",
    )
    s = Settings.load(str(cfg))
    assert s.stamina_seconds == 120
    assert s.notify_send_key == "abc123"
    assert s.wuwa_token == "tok"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: FAIL（无 config 模块）

- [ ] **Step 3: 实现** `src/game_assistant/config.py`：

```python
import tomllib
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    db_path: str = "data/assistant.db"
    stamina_seconds: int = 300
    activity_seconds: int = 3600
    announcement_seconds: int = 3600
    news_seconds: int = 14400
    notify_provider: str = "serverchan"  # serverchan | pushplus
    notify_send_key: str = ""
    wuwa_enabled: bool = True
    wuwa_token: str = ""
    wuwa_user_id: str = ""

    @classmethod
    def load(cls, path: str = "config.toml") -> "Settings":
        p = Path(path)
        data = tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        return cls(**data)
```

注意：TOML 为扁平键（与测试一致），`config.example.toml` 保持同样的扁平风格，注释分组即可。

- [ ] **Step 4: 写 config.example.toml**

```toml
# 复制为 config.toml 后填写真实值；config.toml 已被 gitignore，不会入库
app_host = "127.0.0.1"
app_port = 8000
db_path = "data/assistant.db"

# 轮询间隔（秒）：体力 5 分钟 / 活动·公告 1 小时 / 资讯 4 小时
stamina_seconds = 300
activity_seconds = 3600
announcement_seconds = 3600
news_seconds = 14400

# 微信推送：provider = "serverchan" 或 "pushplus"；send_key 留空 = 功能可用但未启用
notify_provider = "serverchan"
notify_send_key = ""

# 鸣潮（库街区官服）：登录 kurobbs.com 后从请求头抓 token，uid 即库街区数字 id
wuwa_enabled = true
wuwa_token = ""
wuwa_user_id = ""
```

- [ ] **Step 5: 运行确认通过** — Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v` → PASS

- [ ] **Step 6: 提交** — `git add src/game_assistant/config.py config.example.toml tests/test_config.py && git commit -m "feat: TOML-based settings with polling and notify config"`

---

### Task 3: 数据模型

**Files:**
- Create: `src/game_assistant/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces（后续所有任务依赖的精确类型）:
  - `Capability(str, Enum)`：`ACCOUNT = "account"`, `STAMINA = "stamina"`, `ACTIVITY = "activity"`, `ANNOUNCEMENT = "announcement"`, `NEWS = "news"`
  - `StaminaInfo(current: int, maximum: int, expected_full_at: datetime | None, updated_at: datetime)`
  - `AccountInfo(nickname: str | None = None, level: int | None = None, extra: dict = {})`
  - `ActivityItem(title: str, start_at: datetime | None = None, end_at: datetime | None = None, url: str | None = None)`
  - `AnnouncementItem(title: str, published_at: datetime | None = None, url: str | None = None, summary: str = "")`
  - `FetchResult(ok: bool, payload: Any = None, error: str | None = None)` — payload 为上述模型实例或其列表

- [ ] **Step 1: 写失败测试** `tests/test_models.py`：

```python
from datetime import datetime

from game_assistant.models import (
    AccountInfo, ActivityItem, AnnouncementItem, Capability, FetchResult, StaminaInfo,
)


def test_capability_values():
    assert Capability.STAMINA == "stamina"
    assert Capability("account") is Capability.ACCOUNT


def test_stamina_roundtrip():
    s = StaminaInfo(current=180, maximum=240,
                    expected_full_at=datetime(2026, 9, 12, 20, 0),
                    updated_at=datetime(2026, 9, 12, 12, 0))
    assert StaminaInfo.model_validate(s.model_dump()) == s


def test_fetch_result_error():
    r = FetchResult(ok=False, error="未配置凭据")
    assert r.ok is False and r.payload is None
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -v` → FAIL

- [ ] **Step 3: 实现** `src/game_assistant/models.py`：

```python
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class Capability(str, Enum):
    ACCOUNT = "account"
    STAMINA = "stamina"
    ACTIVITY = "activity"
    ANNOUNCEMENT = "announcement"
    NEWS = "news"


class StaminaInfo(BaseModel):
    current: int
    maximum: int
    expected_full_at: datetime | None = None
    updated_at: datetime


class AccountInfo(BaseModel):
    nickname: str | None = None
    level: int | None = None
    extra: dict = {}


class ActivityItem(BaseModel):
    title: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    url: str | None = None


class AnnouncementItem(BaseModel):
    title: str
    published_at: datetime | None = None
    url: str | None = None
    summary: str = ""


class FetchResult(BaseModel):
    ok: bool
    payload: Any = None
    error: str | None = None
```

- [ ] **Step 4: 运行确认通过** — Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -v` → PASS

- [ ] **Step 5: 提交** — `git add src/game_assistant/models.py tests/test_models.py && git commit -m "feat: capability enum and pydantic data models"`

---

### Task 4: 快照存储（SQLite）

**Files:**
- Create: `src/game_assistant/snapshots.py`
- Test: `tests/test_snapshots.py`

**Interfaces:**
- Produces: `SnapshotStore(db_path: str)`，方法：
  - `save(game_id: str, capability: str, payload_json: str) -> None`（同 game_id+capability 覆盖写，记录 fetched_at）
  - `get(game_id: str, capability: str) -> dict | None`，返回 `{"payload": <反序列化后的原字符串>, "fetched_at": "ISO8601"}`，无记录返回 None
  - `ensure_schema()` 由 `__init__` 自动调用

- [ ] **Step 1: 写失败测试** `tests/test_snapshots.py`：

```python
from game_assistant.snapshots import SnapshotStore


def test_save_and_get(tmp_path):
    store = SnapshotStore(str(tmp_path / "t.db"))
    store.save("wuwa", "stamina", '{"current": 180}')
    snap = store.get("wuwa", "stamina")
    assert snap["payload"] == '{"current": 180}'
    assert "fetched_at" in snap


def test_upsert_overwrites(tmp_path):
    store = SnapshotStore(str(tmp_path / "t.db"))
    store.save("wuwa", "stamina", '{"current": 180}')
    store.save("wuwa", "stamina", '{"current": 200}')
    assert store.get("wuwa", "stamina")["payload"] == '{"current": 200}'


def test_get_missing_returns_none(tmp_path):
    store = SnapshotStore(str(tmp_path / "t.db"))
    assert store.get("wuwa", "stamina") is None
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/test_snapshots.py -v` → FAIL

- [ ] **Step 3: 实现** `src/game_assistant/snapshots.py`：

```python
import sqlite3
import threading
from datetime import datetime, timezone


class SnapshotStore:
    def __init__(self, db_path: str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS snapshots ("
                " game_id TEXT NOT NULL, capability TEXT NOT NULL,"
                " payload TEXT NOT NULL, fetched_at TEXT NOT NULL,"
                " PRIMARY KEY (game_id, capability))"
            )
            self._conn.commit()

    def save(self, game_id: str, capability: str, payload_json: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO snapshots (game_id, capability, payload, fetched_at)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(game_id, capability) DO UPDATE SET"
                " payload = excluded.payload, fetched_at = excluded.fetched_at",
                (game_id, capability, payload_json,
                 datetime.now(timezone.utc).isoformat()),
            )
            self._conn.commit()

    def get(self, game_id: str, capability: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload, fetched_at FROM snapshots"
                " WHERE game_id = ? AND capability = ?",
                (game_id, capability),
            ).fetchone()
        return {"payload": row[0], "fetched_at": row[1]} if row else None
```

- [ ] **Step 4: 运行确认通过** — Run: `.venv/Scripts/python.exe -m pytest tests/test_snapshots.py -v` → PASS

- [ ] **Step 5: 提交** — `git add src/game_assistant/snapshots.py tests/test_snapshots.py && git commit -m "feat: sqlite snapshot store with upsert"`

---

### Task 5: 适配器基类与注册表

**Files:**
- Create: `src/game_assistant/adapters/__init__.py`, `src/game_assistant/adapters/base.py`, `src/game_assistant/registry.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Produces:
  - `BaseGameAdapter`（ABC），类属性：`game_id: str`、`display_name: str`、`section: str`（"pc"/"mobile"）、`capabilities: list[Capability]`；实例属性 `credentials_configured: bool`（默认 True）；方法：
    - `async fetch(self, capability: Capability) -> FetchResult` — 分发到 `fetch_account/fetch_stamina/fetch_activity/fetch_announcement/fetch_news`；未声明的能力返回 `FetchResult(ok=False, error="不支持该能力")`
    - 各 `fetch_xxx(self) -> FetchResult` 默认返回 `FetchResult(ok=False, error="适配器未实现该能力")`
  - `GameRegistry`：`register(adapter)`（game_id 重复抛 ValueError）、`get(game_id) -> BaseGameAdapter`（缺失抛 KeyError）、`all() -> list[BaseGameAdapter]`
  - `build_default_registry(settings: Settings) -> GameRegistry` — 本任务只处理 wuwa_enabled 分支；鸣潮适配器在 Task 14 注册（该任务完成前此函数对 wuwa 不注册任何东西，注册逻辑写为 `if settings.wuwa_enabled and WutheringWavesAdapter is not None`，Task 14 前先以占位 import 失败保护实现——见 Step 3）

- [ ] **Step 1: 写失败测试** `tests/test_registry.py`：

```python
import pytest

from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.models import Capability, FetchResult
from game_assistant.registry import GameRegistry


class DummyAdapter(BaseGameAdapter):
    game_id = "dummy"
    display_name = "测试游戏"
    section = "pc"
    capabilities = [Capability.STAMINA]

    def __init__(self):
        self.credentials_configured = True
        self.calls = []

    async def fetch_stamina(self) -> FetchResult:
        self.calls.append("stamina")
        return FetchResult(ok=True, payload=None)


def test_fetch_dispatches_and_rejects_unknown():
    a = DummyAdapter()
    import asyncio
    r = asyncio.run(a.fetch(Capability.STAMINA))
    assert r.ok is True
    r2 = asyncio.run(a.fetch(Capability.ACCOUNT))
    assert r2.ok is False and "不支持" in r2.error


def test_registry_register_get_all():
    reg = GameRegistry()
    a = DummyAdapter()
    reg.register(a)
    assert reg.get("dummy") is a
    assert reg.all() == [a]
    with pytest.raises(ValueError):
        reg.register(DummyAdapter())
    with pytest.raises(KeyError):
        reg.get("nope")
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/test_registry.py -v` → FAIL

- [ ] **Step 3: 实现 base.py**

`src/game_assistant/adapters/base.py`：

```python
from abc import ABC

from game_assistant.models import Capability, FetchResult


class BaseGameAdapter(ABC):
    game_id: str = ""
    display_name: str = ""
    section: str = "pc"  # "pc" | "mobile"
    capabilities: list[Capability] = []
    credentials_configured: bool = True

    async def fetch(self, capability: Capability) -> FetchResult:
        if capability not in self.capabilities:
            return FetchResult(ok=False, error="不支持该能力")
        method = {
            Capability.ACCOUNT: self.fetch_account,
            Capability.STAMINA: self.fetch_stamina,
            Capability.ACTIVITY: self.fetch_activity,
            Capability.ANNOUNCEMENT: self.fetch_announcement,
            Capability.NEWS: self.fetch_news,
        }[capability]
        return await method()

    async def fetch_account(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_stamina(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_activity(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_announcement(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_news(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")
```

`src/game_assistant/adapters/__init__.py` 空文件。

- [ ] **Step 4: 实现 registry.py**

```python
from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.config import Settings


class GameRegistry:
    def __init__(self):
        self._adapters: dict[str, BaseGameAdapter] = {}

    def register(self, adapter: BaseGameAdapter) -> None:
        if adapter.game_id in self._adapters:
            raise ValueError(f"重复注册: {adapter.game_id}")
        self._adapters[adapter.game_id] = adapter

    def get(self, game_id: str) -> BaseGameAdapter:
        if game_id not in self._adapters:
            raise KeyError(f"未注册的游戏: {game_id}")
        return self._adapters[game_id]

    def all(self) -> list[BaseGameAdapter]:
        return list(self._adapters.values())


def build_default_registry(settings: Settings) -> GameRegistry:
    registry = GameRegistry()
    if settings.wuwa_enabled:
        try:
            from game_assistant.adapters.wuthering_waves.adapter import WutheringWavesAdapter
        except ImportError:
            pass  # Task 14 完成前尚不存在，届时自动生效
        else:
            registry.register(WutheringWavesAdapter(settings))
    return registry
```

- [ ] **Step 5: 运行确认通过** — Run: `.venv/Scripts/python.exe -m pytest tests/test_registry.py -v` → PASS

- [ ] **Step 6: 提交** — `git add src/game_assistant/adapters src/game_assistant/registry.py tests/test_registry.py && git commit -m "feat: adapter base class and game registry"`

---

### Task 6: 通知接口与微信推送（实现但默认未配置）

**Files:**
- Create: `src/game_assistant/notify/__init__.py`, `src/game_assistant/notify/base.py`, `src/game_assistant/notify/wechat_push.py`
- Test: `tests/test_notify.py`

**Interfaces:**
- Produces:
  - `Notifier`（Protocol）：`name: str`；`async def send(self, title: str, body: str) -> bool`
  - `WeChatPushNotifier(provider: str = "serverchan", send_key: str = "")`：
    - `send_key` 为空 → `send()` 记 log.info("提醒渠道未启用") 并返回 False，**不发 HTTP**
    - provider="serverchan" → `POST https://sctapi.ftqq.com/{send_key}.send`，表单 `{"title": title, "desp": body}`，响应 `code == 0` 视为成功
    - provider="pushplus" → `POST https://www.pushplus.plus/send`，JSON `{"token": send_key, "title": title, "content": body, "template": "txt"}`，响应 `code == 200` 视为成功
    - HTTP 异常/非预期响应 → log.warning 并返回 False（不抛出）
  - `build_notifier(settings: Settings) -> WeChatPushNotifier`

- [ ] **Step 1: 写失败测试** `tests/test_notify.py`：

```python
import httpx
import respx


def test_send_skipped_when_key_empty():
    from game_assistant.notify.wechat_push import WeChatPushNotifier
    n = WeChatPushNotifier(provider="serverchan", send_key="")
    import asyncio
    assert asyncio.run(n.send("t", "b")) is False


@respx.mock
async def test_serverchan_send():
    from game_assistant.notify.wechat_push import WeChatPushNotifier
    route = respx.post("https://sctapi.ftqq.com/KEY.send").mock(
        return_value=httpx.Response(200, json={"code": 0}))
    n = WeChatPushNotifier(provider="serverchan", send_key="KEY")
    assert await n.send("标题", "内容") is True
    assert route.called


@respx.mock
async def test_pushplus_send():
    from game_assistant.notify.wechat_push import WeChatPushNotifier
    respx.post("https://www.pushplus.plus/send").mock(
        return_value=httpx.Response(200, json={"code": 200}))
    n = WeChatPushNotifier(provider="pushplus", send_key="K")
    assert await n.send("t", "b") is True


@respx.mock
async def test_http_error_returns_false():
    from game_assistant.notify.wechat_push import WeChatPushNotifier
    respx.post("https://sctapi.ftqq.com/KEY.send").mock(
        return_value=httpx.Response(500))
    n = WeChatPushNotifier(provider="serverchan", send_key="KEY")
    assert await n.send("t", "b") is False
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/test_notify.py -v` → FAIL

- [ ] **Step 3: 实现**

`src/game_assistant/notify/wechat_push.py`：

```python
import logging

import httpx

logger = logging.getLogger(__name__)


class WeChatPushNotifier:
    name = "wechat_push"

    def __init__(self, provider: str = "serverchan", send_key: str = ""):
        self.provider = provider
        self.send_key = send_key

    async def send(self, title: str, body: str) -> bool:
        if not self.send_key:
            logger.info("提醒渠道未启用（send_key 未配置），跳过推送: %s", title)
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                if self.provider == "serverchan":
                    resp = await client.post(
                        f"https://sctapi.ftqq.com/{self.send_key}.send",
                        data={"title": title, "desp": body},
                    )
                    ok = resp.json().get("code") == 0
                elif self.provider == "pushplus":
                    resp = await client.post(
                        "https://www.pushplus.plus/send",
                        json={"token": self.send_key, "title": title,
                              "content": body, "template": "txt"},
                    )
                    ok = resp.json().get("code") == 200
                else:
                    logger.warning("未知推送 provider: %s", self.provider)
                    return False
            if not ok:
                logger.warning("微信推送响应异常: %s", resp.text[:200])
            return ok
        except Exception:
            logger.warning("微信推送失败", exc_info=True)
            return False
```

`src/game_assistant/notify/base.py`：

```python
from typing import Protocol

from game_assistant.config import Settings
from game_assistant.notify.wechat_push import WeChatPushNotifier


class Notifier(Protocol):
    name: str

    async def send(self, title: str, body: str) -> bool: ...


def build_notifier(settings: Settings) -> Notifier:
    return WeChatPushNotifier(provider=settings.notify_provider,
                              send_key=settings.notify_send_key)
```

`src/game_assistant/notify/__init__.py` 空文件。

- [ ] **Step 4: 运行确认通过** — Run: `.venv/Scripts/python.exe -m pytest tests/test_notify.py -v` → PASS

- [ ] **Step 5: 提交** — `git add src/game_assistant/notify tests/test_notify.py && git commit -m "feat: notifier interface with ServerChan/PushPlus implementation"`

---

### Task 7: 轮询调度器

**Files:**
- Create: `src/game_assistant/scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `GameRegistry`、`SnapshotStore`、`BaseGameAdapter.fetch`、`Settings`（间隔字段）、`Notifier`
- Produces: `PollingScheduler(registry, store, settings, notifier)`：
  - `build_jobs() -> list[tuple[str, Capability, int]]` — 每个适配器 × 每个声明能力，间隔按能力映射（stamina→settings.stamina_seconds，activity→activity_seconds，announcement→announcement_seconds，news→news_seconds，account→activity_seconds）；间隔 ≤0 的能力不入列
  - `async poll_once(game_id: str, capability: Capability) -> FetchResult` — 调 adapter.fetch；ok 时将 payload 用 `model_dump_json`（列表则先逐个转 dict 序列化为 JSON 数组）存入快照；失败时只 log.warning，不动快照；拉取成功且 payload 含 StaminaInfo 时，若体力已满或达到阈值则调用 notifier.send（本计划仅在 `current >= maximum` 时推送，标题 `"鸣潮体力已满"`，M3 再扩展规则引擎）
  - `start()` / `shutdown()` — `AsyncIOScheduler`（interval 触发器）注册所有 job

- [ ] **Step 1: 写失败测试** `tests/test_scheduler.py`：

```python
import json

from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult, StaminaInfo
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


def _sched(tmp_path, settings=None):
    reg = type("R", (), {"all": lambda self: [WuwaLike()],
                         "get": lambda self, gid: WuwaLike()})()
    store = SnapshotStore(str(tmp_path / "t.db"))
    s = settings or Settings()
    return PollingScheduler(reg, store, s, FakeNotify()), store


async def test_poll_once_saves_snapshot_and_notifies_full(tmp_path):
    sched, store = _sched(tmp_path)
    r = await sched.poll_once("wuwa", Capability.STAMINA)
    assert r.ok is True
    snap = store.get("wuwa", "stamina")
    payload = json.loads(snap["payload"])
    assert payload["current"] == 240
    assert any("体力已满" in t for t, _ in FakeNotify.sent)


async def test_poll_failure_keeps_old_snapshot(tmp_path):
    sched, store = _sched(tmp_path)
    await sched.poll_once("wuwa", Capability.ACTIVITY)  # 失败
    assert store.get("wuwa", "activity") is None


def test_build_jobs_uses_intervals(tmp_path):
    sched, _ = _sched(tmp_path, Settings(stamina_seconds=0, activity_seconds=60))
    jobs = {cap: secs for _, cap, secs in sched.build_jobs()}
    assert Capability.STAMINA not in jobs      # 间隔<=0 不调度
    assert jobs[Capability.ACTIVITY] == 60
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/test_scheduler.py -v` → FAIL

- [ ] **Step 3: 实现** `src/game_assistant/scheduler.py`：

```python
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
        self._scheduler = AsyncIOScheduler()
        for game_id, cap, secs in self.build_jobs():
            self._scheduler.add_job(
                self.poll_once, IntervalTrigger(seconds=secs),
                args=[game_id, cap], id=f"{game_id}:{cap.value}",
                max_instances=1, coalesce=True)
        self._scheduler.start()

    async def shutdown(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
```

- [ ] **Step 4: 运行确认通过** — Run: `.venv/Scripts/python.exe -m pytest tests/test_scheduler.py -v` → PASS

- [ ] **Step 5: 提交** — `git add src/game_assistant/scheduler.py tests/test_scheduler.py && git commit -m "feat: polling scheduler persisting snapshots with stamina-full notify"`

---

### Task 8: API 路由（游戏列表 / 快照读取 / 状态）

**Files:**
- Create: `src/game_assistant/api.py`
- Modify: `src/game_assistant/main.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `GameRegistry`、`SnapshotStore`、Task 5 的适配器属性
- Produces: `create_app(registry=None, store=None, scheduler=None, notifier=None) -> FastAPI`（默认参数走 `build_default_registry(Settings.load())` + 真实 store/scheduler/notifier，Task 9 完成接线）。路由：
  - `GET /api/games` → `[{game_id, display_name, section, capabilities: [str], credentials_configured}]`
  - `GET /api/games/{game_id}/snapshot/{capability}` → 200 `{"game_id", "capability", "fetched_at", "payload"(对象或数组), "stale"(bool, fetched_at 距今>2×轮询间隔)}`；无快照 200 `{"payload": null, ...}`（前端据此显示"暂无数据"）；game_id 未知 404
  - `GET /api/status` → `{"notify": {"enabled": bool, "provider": str | null}}`

- [ ] **Step 1: 写失败测试** `tests/test_api.py`（同时创建空文件 `tests/__init__.py`，使 tests 成为可导入包）：

```python
from fastapi.testclient import TestClient

from game_assistant.api import create_app
from game_assistant.models import StaminaInfo
from game_assistant.snapshots import SnapshotStore
from tests.test_registry import DummyAdapter


class FakeRegistry:
    def __init__(self, adapter):
        self._adapter = adapter

    def all(self):
        return [self._adapter]

    def get(self, game_id):
        if game_id != self._adapter.game_id:
            raise KeyError(game_id)
        return self._adapter


def _app_with(tmp_path, snapshots=None):
    store = SnapshotStore(str(tmp_path / "t.db"))
    for gid, cap, payload in (snapshots or []):
        store.save(gid, cap, payload)
    client = TestClient(create_app(registry=FakeRegistry(DummyAdapter()), store=store))
    return client, store


def test_list_games(tmp_path):
    client, _ = _app_with(tmp_path)
    resp = client.get("/api/games")
    assert resp.status_code == 200
    g = resp.json()[0]
    assert g["game_id"] == "dummy" and g["section"] == "pc"
    assert g["capabilities"] == ["stamina"]


def test_snapshot_roundtrip(tmp_path):
    client, store = _app_with(tmp_path)
    store.save("dummy", "stamina", StaminaInfo(
        current=100, maximum=240, expected_full_at=None,
        updated_at="2026-09-12T12:00:00").model_dump_json())
    resp = client.get("/api/games/dummy/snapshot/stamina")
    assert resp.status_code == 200
    body = resp.json()
    assert body["payload"]["current"] == 100
    assert body["stale"] is False


def test_snapshot_missing_and_unknown_game(tmp_path):
    client, _ = _app_with(tmp_path)
    assert client.get("/api/games/dummy/snapshot/stamina").json()["payload"] is None
    assert client.get("/api/games/nope/snapshot/stamina").status_code == 404


def test_status_notify_disabled(tmp_path):
    client, _ = _app_with(tmp_path)
    assert client.get("/api/status").json()["notify"]["enabled"] is False
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py -v` → FAIL

- [ ] **Step 3: 实现 api.py 并改造 main.py**

`src/game_assistant/api.py`：

```python
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request

from game_assistant.config import Settings
from game_assistant.registry import build_default_registry
from game_assistant.snapshots import SnapshotStore


def _stale(fetched_at: str, interval_seconds: int) -> bool:
    dt = datetime.fromisoformat(fetched_at)
    age = (datetime.now(timezone.utc) - dt).total_seconds()
    return age > 2 * max(interval_seconds, 60)


def create_app(registry=None, store=None, scheduler=None, notifier=None,
               settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    app = FastAPI(title="Game Assistant")
    app.state.settings = settings
    app.state.registry = registry if registry is not None else build_default_registry(settings)
    app.state.store = store if store is not None else SnapshotStore(settings.db_path)
    app.state.scheduler = scheduler
    app.state.notifier = notifier

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/games")
    async def games() -> list[dict]:
        return [{
            "game_id": a.game_id, "display_name": a.display_name,
            "section": a.section,
            "capabilities": [c.value for c in a.capabilities],
            "credentials_configured": a.credentials_configured,
        } for a in app.state.registry.all()]

    @app.get("/api/games/{game_id}/snapshot/{capability}")
    async def snapshot(game_id: str, capability: str) -> dict:
        try:
            adapter = app.state.registry.get(game_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="未注册的游戏")
        snap = app.state.store.get(game_id, capability)
        if snap is None:
            return {"game_id": game_id, "capability": capability,
                    "payload": None, "fetched_at": None, "stale": False}
        interval = {
            "stamina": settings.stamina_seconds,
            "activity": settings.activity_seconds,
            "announcement": settings.announcement_seconds,
            "news": settings.news_seconds,
            "account": settings.activity_seconds,
        }.get(capability, 3600)
        import json
        return {"game_id": game_id, "capability": capability,
                "payload": json.loads(snap["payload"]),
                "fetched_at": snap["fetched_at"],
                "stale": _stale(snap["fetched_at"], interval)}

    @app.get("/api/status")
    async def status() -> dict:
        notifier = app.state.notifier
        enabled = bool(notifier and getattr(notifier, "send_key", "") )
        provider = getattr(notifier, "provider", None)
        return {"notify": {"enabled": enabled, "provider": provider}}

    return app
```

`src/game_assistant/main.py` 改为：

```python
from game_assistant.api import create_app

app = create_app()
```

- [ ] **Step 4: 运行全部测试** — Run: `.venv/Scripts/python.exe -m pytest -v` → 全部 PASS（test_health 仍需通过；若 DummyAdapter 无 credentials_configured 属性，确认 Task 5 中默认 True 已继承）

- [ ] **Step 5: 提交** — `git add src/game_assistant/api.py src/game_assistant/main.py tests && git commit -m "feat: REST API for games list, snapshots and notify status"`

---

### Task 9: 生命周期接线（调度器启动 + 手动刷新 + 通知发送测试）

**Files:**
- Modify: `src/game_assistant/api.py`（lifespan + refresh 路由）
- Test: `tests/test_lifecycle.py`

**Interfaces:**
- Consumes: Task 7 `PollingScheduler`（`start/shutdown/poll_once`）、Task 6 `build_notifier`
- Produces: `create_app` 完整版：
  - FastAPI lifespan：启动时 `PollingScheduler(...).start()`、关闭时 `shutdown()`
  - `POST /api/games/{game_id}/refresh` → 对该游戏全部能力逐个 `poll_once`，返回 `{"results": {cap: {"ok": bool, "error": str | None}}}`（未知游戏 404）

- [ ] **Step 1: 写失败测试** `tests/test_lifecycle.py`：

```python
from fastapi.testclient import TestClient

from game_assistant.api import create_app
from game_assistant.config import Settings
from game_assistant.scheduler import PollingScheduler
from game_assistant.snapshots import SnapshotStore


def test_refresh_endpoint(tmp_path):
    store = SnapshotStore(str(tmp_path / "t.db"))
    registry = build_dummy_registry()
    sched = PollingScheduler(registry, store, Settings(), FakeNotify())
    client = TestClient(create_app(registry=registry, store=store,
                                   scheduler=sched, notifier=FakeNotify()))
    resp = client.post("/api/games/dummy/refresh")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results["stamina"]["ok"] is True
    assert client.get("/api/games/dummy/snapshot/stamina").json()["payload"] is not None


def test_refresh_unknown_game(tmp_path):
    store = SnapshotStore(str(tmp_path / "t.db"))
    client = TestClient(create_app(registry=build_dummy_registry(), store=store,
                                   scheduler=None, notifier=None))
    assert client.post("/api/games/nope/refresh").status_code == 404


def build_dummy_registry():
    from tests.test_registry import DummyAdapter
    from game_assistant.registry import GameRegistry
    reg = GameRegistry()
    reg.register(DummyAdapter())
    return reg


class FakeNotify:
    name = "fake"

    async def send(self, title, body):
        return True
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/test_lifecycle.py -v` → FAIL（无 refresh 路由）

- [ ] **Step 3: 实现** — 修改 `api.py`：

```python
# 文件顶部补充 import
from contextlib import asynccontextmanager
from game_assistant.scheduler import PollingScheduler
from game_assistant.notify.base import build_notifier

# create_app 签名改为（settings 注解保持 Settings | None）：
def create_app(registry=None, store=None, scheduler=None, notifier=None,
               settings: Settings | None = None,
               start_scheduler: bool = True) -> FastAPI:
```

在 `create_app` 内、`return app` 前：

```python
    if scheduler is None and start_scheduler:
        scheduler = PollingScheduler(app.state.registry, app.state.store,
                                     settings, notifier or build_notifier(settings))
    app.state.scheduler = scheduler

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if app.state.scheduler:
            app.state.scheduler.start()
        yield
        if app.state.scheduler:
            await app.state.scheduler.shutdown()

    @app.post("/api/games/{game_id}/refresh")
    async def refresh(game_id: str) -> dict:
        try:
            adapter = app.state.registry.get(game_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="未注册的游戏")
        results = {}
        for cap in adapter.capabilities:
            if app.state.scheduler:
                r = await app.state.scheduler.poll_once(game_id, cap)
            else:
                r = await adapter.fetch(cap)
            results[cap.value] = {"ok": r.ok, "error": r.error}
        return {"results": results}

    app.router.lifespan_context = lifespan
```

注意：`test_refresh_unknown_game` 传入 `scheduler=None` 时，refresh 对未注册游戏先 404，不会触达 fetch 兜底分支；`FakeNotify` 与注册表在各测试中显式传入。

- [ ] **Step 4: 运行全部测试** — Run: `.venv/Scripts/python.exe -m pytest -v` → 全部 PASS

- [ ] **Step 5: 提交** — `git add src/game_assistant/api.py tests/test_lifecycle.py && git commit -m "feat: lifespan scheduler wiring and manual refresh endpoint"`

---

### Task 10: 前端骨架（Vue3 + Vite，双板块仪表盘）

**Files:**
- Create: `frontend/`（Vite 脚手架）、`frontend/vite.config.js`、`frontend/src/api.js`、`frontend/src/App.vue`、`frontend/src/components/{SectionTabs,GameCard,StaminaCard,AccountCard,ActivityList,AnnouncementList,StatusChip}.vue`

**Interfaces:**
- Consumes: Task 8/9 的三个 GET 路由 + POST refresh
- Produces: 浏览器仪表盘：顶部状态条（提醒渠道未启用提示）、PC/手游板块切换、每游戏一卡、卡内按能力渲染子组件、60 秒自动刷新、手动刷新按钮、"更新于 xx（数据可能过期）"陈旧标记、未配置凭据提示

- [ ] **Step 1: 脚手架**

```bash
cd /c/Zcode/game-manage
npm create vite@latest frontend -- --template vue
cd frontend && npm install
```

- [ ] **Step 2: vite.config.js 加代理**（覆盖生成内容）：

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
```

- [ ] **Step 3: api.js**

```javascript
async function j(resp) {
  if (!resp.ok) throw new Error(`${resp.status}`)
  return resp.json()
}

export const getGames = () => fetch('/api/games').then(j)
export const getStatus = () => fetch('/api/status').then(j)
export const getSnapshot = (gameId, cap) =>
  fetch(`/api/games/${gameId}/snapshot/${cap}`).then(j)
export const refreshGame = (gameId) =>
  fetch(`/api/games/${gameId}/refresh`, { method: 'POST' }).then(j)
```

- [ ] **Step 4: 组件实现**（组件文件均为标准 SFC；此处为行为规格，实现时用同一份 API 契约）：
  - `App.vue`：onMounted 并行拉 `getGames/getStatus`；`games` 按 `section` 分 "pc"/"mobile" 两组渲染 `<SectionTabs>` + `<GameCard v-for>`；60s `setInterval` 重拉所有快照；顶部 `<StatusChip>`（notify.enabled=false 时显示"微信推送未配置（功能已就绪）"）
  - `SectionTabs.vue`：props `{ sections: string[] }`，切换激活板块（"PC 游戏" / "手游"）
  - `GameCard.vue`：props `{ game }`；头部游戏名 + `credentials_configured=false` 时红色角标"未配置凭据" + 刷新按钮（调 `refreshGame`，若 results 中任一能力 `ok=false`，在卡片顶部显示红色错误条"刷新失败：{error}"并保留 10 秒，随后重拉快照）；body 遍历 `game.capabilities` 映射到子组件（stamina→StaminaCard、account→AccountCard、activity→ActivityList、announcement→AnnouncementList，其余显示"敬请期待"）
  - `StaminaCard.vue`：props `{ snap }`；payload null → "暂无数据"；否则大字 `{{ payload.current }}/{{ payload.maximum }}`，`expected_full_at` 存在时显示"预计 xx 恢复满"，底部"更新于 {{ fetched_at 本地化 }}"，`stale=true` 加黄色"数据可能过期"
  - `AccountCard.vue`：显示 nickname/level；`ActivityList.vue`/`AnnouncementList.vue`：列表渲染 title、`end_at` 计算剩余天数徽标（`Math.ceil((end_at - now)/86400000)`，<0 显示"已结束"，≤3 红色）、published_at 日期；null payload 显示"暂无数据"

- [ ] **Step 5: 构建与手动验证**

```bash
npm run build   # 必须成功
cd .. && .venv/Scripts/python.exe -m uvicorn game_assistant.main:app --port 8000
# 新终端: cd frontend && npm run dev → 打开 http://localhost:5173
```

验证点：页面显示"手游"板块与"鸣潮"卡片；角标"未配置凭据"；各能力区显示"暂无数据"；顶部出现"微信推送未配置（功能已就绪）"；POST refresh 后仍无数据但无报错。

- [ ] **Step 6: 提交** — `git add frontend && git commit -m "feat: Vue3 dashboard shell with section tabs and capability cards"`

---

### Task 11: 库街区客户端（端点常量 + getRoleData）

**Files:**
- Create: `src/game_assistant/adapters/wuthering_waves/__init__.py`, `src/game_assistant/adapters/wuthering_waves/endpoints.py`, `src/game_assistant/adapters/wuthering_waves/kuro_client.py`
- Test: `tests/adapters/test_kuro_client.py`（建 `tests/adapters/__init__.py`）

**Interfaces:**
- Produces:
  - `endpoints.py`：`BASE = "https://api.kurobbs.com"`、`ROLE_DATA = "/gamer/aki/api/getRoleData"`、`ACTIVITY_LIST`、`ANNOUNCEMENT_LIST`（后两者初值见 Step 3，须在 Step 5 对照 Kuro-API-Collection 校准）
  - `KuroClient(token: str, user_id: str)`：`async get_role_data() -> dict`、`async get_activity_list() -> dict`、`async get_announcement_list() -> dict`；响应 `code != 200` 时抛 `KuroError(code, msg)`；`code` 为 token 失效类错误（msg 含"登录"或 code in (220, 400) 不确定——按非 200 统一处理）时同样抛 `KuroError`，由上层把"凭据失效"与"接口错误"统一按 error 信息呈现
  - 异常类型 `KuroError(Exception)`：属性 `code: int, message: str`

- [ ] **Step 1: 写失败测试** `tests/adapters/test_kuro_client.py`：

```python
import httpx
import pytest
import respx

from game_assistant.adapters.wuthering_waves.kuro_client import KuroClient, KuroError

ROLE_RAW = {"code": 200, "msg": "success",
            "data": {"name": "漂泊者", "level": 80,
                     "energy": {"power": 180, "max": 240,
                                "refreshTimestamp": 1726000000000}}}


@respx.mock
async def test_get_role_data_ok():
    route = respx.post("https://api.kurobbs.com/gamer/aki/api/getRoleData").mock(
        return_value=httpx.Response(200, json=ROLE_RAW))
    client = KuroClient(token="tok", user_id="123456")
    data = await client.get_role_data()
    assert data["data"]["energy"]["power"] == 180
    req = route.calls.last.request
    assert req.headers["token"] == "tok"
    assert b"123456" in req.content


@respx.mock
async def test_error_raises_kuro_error():
    respx.post("https://api.kurobbs.com/gamer/aki/api/getRoleData").mock(
        return_value=httpx.Response(200, json={"code": 220, "msg": "登录失效"}))
    client = KuroClient(token="bad", user_id="1")
    with pytest.raises(KuroError) as ei:
        await client.get_role_data()
    assert ei.value.code == 220
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/adapters/test_kuro_client.py -v` → FAIL

- [ ] **Step 3: 实现**

`endpoints.py`：

```python
# 库街区 APP 端接口。来源与校准基准：
#   https://github.com/TomyJan/Kuro-API-Collection （README 与 PARAMS.md）
# 若上游调整路径/参数，只改本文件。
BASE = "https://api.kurobbs.com"
ROLE_DATA = f"{BASE}/gamer/aki/api/getRoleData"
ACTIVITY_LIST = f"{BASE}/gamer/aki/api/getActivityList"  # 校准点：Task 11 Step 5
ANNOUNCEMENT_LIST = f"{BASE}/forum/list"                 # 校准点：Task 11 Step 5
```

`kuro_client.py`：

```python
import json
import logging

import httpx

from game_assistant.adapters.wuthering_waves.endpoints import (
    ACTIVITY_LIST, ANNOUNCEMENT_LIST, ROLE_DATA,
)

logger = logging.getLogger(__name__)


class KuroError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"库街区接口错误 code={code}: {message}")


class KuroClient:
    def __init__(self, token: str, user_id: str):
        self.token = token
        self.user_id = user_id

    def _headers(self) -> dict:
        return {
            "token": self.token,
            "devCode": "9asdpjhjklgfhjko90876532134",  # 库街区 APP 固定 devCode 样例
            "version": "3.0.0",
            "countryCode": "CN",
            "source": "h5",
            "Content-Type": "application/json",
        }

    async def _post(self, url: str, body: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, headers=self._headers(),
                                         content=json.dumps(body))
        except httpx.HTTPError as e:
            raise KuroError(-1, f"网络错误: {e}") from e
        data = resp.json()
        if data.get("code") != 200:
            raise KuroError(data.get("code", -2), data.get("msg", "未知错误"))
        return data

    async def get_role_data(self) -> dict:
        return await self._post(ROLE_DATA,
                                {"gameId": 3, "userId": self.user_id, "serverId": ""})

    async def get_activity_list(self) -> dict:
        return await self._post(ACTIVITY_LIST, {"gameId": 3})

    async def get_announcement_list(self) -> dict:
        return await self._post(ANNOUNCEMENT_LIST,
                                {"forumId": 1602, "gameId": 3, "page": 1, "limit": 20})
```

`tests/adapters/__init__.py`、`src/game_assistant/adapters/wuthering_waves/__init__.py` 均为空文件。

- [ ] **Step 4: 运行确认通过** — Run: `.venv/Scripts/python.exe -m pytest tests/adapters/test_kuro_client.py -v` → PASS

- [ ] **Step 5: 端点与参数校准（一次性，在线操作）**

用 WebFetch 读取 `https://github.com/TomyJan/Kuro-API-Collection` 的 README 与 `PARAMS.md`，核对三件事并把结论写回 `endpoints.py` 注释：①getRoleData 的实际路径、body 字段（gameId=3 指鸣潮？）与必填请求头（token/devCode/version）；②活动列表端点真实路径与参数；③公告列表端点真实路径与参数（forum/list 的 forumId 对应鸣潮公告分区）。若与初值不符，同步修改测试中的 URL 常量后重跑测试。

- [ ] **Step 6: 提交** — `git add src/game_assistant/adapters/wuthering_waves tests/adapters && git commit -m "feat: kurobbs API client with role data fetch"`

---

### Task 12: 角色数据解析（账号 + 体力）

**Files:**
- Create: `src/game_assistant/adapters/wuthering_waves/role.py`
- Test: `tests/adapters/test_role_parse.py`

**Interfaces:**
- Produces: `parse_role_data(raw: dict, now: datetime) -> tuple[AccountInfo, StaminaInfo]`
  - 账号：`data.name`→nickname、`data.level`→level
  - 体力：`data.energy.power`→current、`data.energy.max`→maximum；`expected_full_at`：有 `energy.refreshTimestamp`（毫秒）用之，否则 `now + (maximum-current)*6分钟`；`updated_at=now`

- [ ] **Step 1: 写失败测试** `tests/adapters/test_role_parse.py`：

```python
from datetime import datetime

from game_assistant.adapters.wuthering_waves.role import parse_role_data

RAW = {"code": 200, "data": {"name": "漂泊者", "level": 80,
                             "energy": {"power": 180, "max": 240}}}
NOW = datetime(2026, 9, 12, 12, 0, 0)


def test_account_fields():
    acc, _ = parse_role_data(RAW, NOW)
    assert acc.nickname == "漂泊者" and acc.level == 80


def test_stamina_eta_fallback_6min_per_point():
    _, st = parse_role_data(RAW, NOW)
    assert st.current == 180 and st.maximum == 240
    assert st.expected_full_at == datetime(2026, 9, 12, 20, 0)  # 60点×6分钟


def test_stamina_eta_from_refresh_timestamp():
    raw = {"code": 200, "data": {"energy": {"power": 200, "max": 240,
                                            "refreshTimestamp": 1788525600000}}}
    _, st = parse_role_data(raw, NOW)
    assert st.expected_full_at == datetime.fromtimestamp(1788525600)
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/adapters/test_role_parse.py -v` → FAIL

- [ ] **Step 3: 实现** `role.py`：

```python
from datetime import datetime, timedelta, timezone

from game_assistant.models import AccountInfo, StaminaInfo

REGEN_MINUTES_PER_POINT = 6


def parse_role_data(raw: dict, now: datetime) -> tuple[AccountInfo, StaminaInfo]:
    data = raw.get("data") or {}
    acc = AccountInfo(nickname=data.get("name"), level=data.get("level"))

    energy = data.get("energy") or {}
    current = int(energy.get("power") or 0)
    maximum = int(energy.get("max") or 0)
    expected_full_at = None
    ts = energy.get("refreshTimestamp")
    if ts:
        expected_full_at = datetime.fromtimestamp(int(ts) / 1000)
    elif maximum > current:
        expected_full_at = now + timedelta(
            minutes=REGEN_MINUTES_PER_POINT * (maximum - current))
    stamina = StaminaInfo(current=current, maximum=maximum,
                          expected_full_at=expected_full_at, updated_at=now)
    return acc, stamina
```

- [ ] **Step 4: 运行确认通过** — Run: `.venv/Scripts/python.exe -m pytest tests/adapters/test_role_parse.py -v` → PASS
  （若真实响应字段与 fixture 不符——例如体力叫 `waveStamina`——在 Step 5 校准中同步修正 fixture 与解析键。）

- [ ] **Step 5: 提交** — `git add src/game_assistant/adapters/wuthering_waves/role.py tests/adapters/test_role_parse.py && git commit -m "feat: parse kurobbs role data into account and stamina models"`

---

### Task 13: 活动与公告抓取解析

**Files:**
- Create: `src/game_assistant/adapters/wuthering_waves/events.py`, `src/game_assistant/adapters/wuthering_waves/announcements.py`
- Test: `tests/adapters/test_events_parse.py`, `tests/adapters/test_announcements_parse.py`

**Interfaces:**
- Consumes: Task 11 `KuroClient.get_activity_list/get_announcement_list`
- Produces:
  - `parse_activity_list(raw: dict) -> list[ActivityItem]` — 遍历 `raw["data"]`（或 `data.list`），`title`；起止时间键依次尝试 `startTime/beginTime`、`endTime/overTime`，`datetime.fromisoformat` 失败则为 None；`url` 取 `url/postUrl`
  - `parse_announcement_list(raw: dict) -> list[AnnouncementItem]` — 遍历 `raw["data"]["list"]`，`title`、`createTime`、url=`https://www.kurobbs.com/forum/post/{postId}`

- [ ] **Step 1: 写失败测试** `tests/adapters/test_events_parse.py`：

```python
from datetime import datetime

from game_assistant.adapters.wuthering_waves.events import parse_activity_list

RAW = {"code": 200, "data": [
    {"title": "版本限时活动", "startTime": "2026-09-01 10:00:00",
     "endTime": "2026-09-30 23:59:59", "url": "https://www.kurobbs.com/event/1"},
    {"title": "无时间条目"},
]}


def test_parse_activities():
    items = parse_activity_list(RAW)
    assert len(items) == 2
    assert items[0].title == "版本限时活动"
    assert items[0].end_at == datetime(2026, 9, 30, 23, 59, 59)
    assert items[1].end_at is None
```

`tests/adapters/test_announcements_parse.py`：

```python
from game_assistant.adapters.wuthering_waves.announcements import parse_announcement_list

RAW = {"code": 200, "data": {"list": [
    {"postId": "123", "title": "2.6版本更新公告", "createTime": "2026-09-10 12:00:00"},
    {"postId": "456", "title": "维护完成公告"},
]}}


def test_parse_announcements():
    items = parse_announcement_list(RAW)
    assert len(items) == 2
    assert items[0].url == "https://www.kurobbs.com/forum/post/123"
    assert items[0].published_at is not None
    assert items[1].published_at is None
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/adapters -v` → FAIL

- [ ] **Step 3: 实现**

`events.py`：

```python
from datetime import datetime

from game_assistant.models import ActivityItem


def _dt(*vals):
    for v in vals:
        if v:
            try:
                return datetime.fromisoformat(str(v))
            except ValueError:
                continue
    return None


def parse_activity_list(raw: dict) -> list[ActivityItem]:
    data = raw.get("data") or []
    if isinstance(data, dict):
        data = data.get("list") or []
    items = []
    for it in data:
        items.append(ActivityItem(
            title=it.get("title") or "",
            start_at=_dt(it.get("startTime"), it.get("beginTime")),
            end_at=_dt(it.get("endTime"), it.get("overTime")),
            url=it.get("url") or it.get("postUrl"),
        ))
    return items
```

`announcements.py`：

```python
from datetime import datetime

from game_assistant.models import AnnouncementItem


def parse_announcement_list(raw: dict) -> list[AnnouncementItem]:
    data = raw.get("data") or {}
    rows = data.get("list") if isinstance(data, dict) else data
    items = []
    for it in rows or []:
        published = None
        if it.get("createTime"):
            try:
                published = datetime.fromisoformat(str(it["createTime"]))
            except ValueError:
                pass
        items.append(AnnouncementItem(
            title=it.get("title") or "",
            published_at=published,
            url=f"https://www.kurobbs.com/forum/post/{it.get('postId')}"
            if it.get("postId") else None,
        ))
    return items
```

- [ ] **Step 4: 运行确认通过** — Run: `.venv/Scripts/python.exe -m pytest tests/adapters -v` → PASS

- [ ] **Step 5: 提交** — `git add src/game_assistant/adapters/wuthering_waves tests/adapters && git commit -m "feat: parse kurobbs activity list and announcements"`

---

### Task 14: 鸣潮适配器组装与注册

**Files:**
- Create: `src/game_assistant/adapters/wuthering_waves/adapter.py`
- Modify: `src/game_assistant/config.py`（无需改动，复用 wuwa_* 字段）
- Test: `tests/adapters/test_wuwa_adapter.py`

**Interfaces:**
- Consumes: Task 5 `BaseGameAdapter`、Task 11 client、Task 12/13 解析
- Produces: `WutheringWavesAdapter(settings: Settings)`：
  - 类属性：`game_id="wuthering_waves"`、`display_name="鸣潮"`、`section="mobile"`、`capabilities=[ACCOUNT, STAMINA, ACTIVITY, ANNOUNCEMENT]`
  - `settings.wuwa_token` 与 `wuwa_user_id` 均非空 → `credentials_configured=True` 并持有 `KuroClient`；否则 `credentials_configured=False`，所有 fetch 返回 `FetchResult(ok=False, error="未配置凭据")`
  - `fetch_account/fetch_stamina` → `get_role_data` + `parse_role_data`（payload：account→AccountInfo，stamina→StaminaInfo）；`KuroError` → `FetchResult(ok=False, error=f"库街区接口错误: {e.message}")`
  - `fetch_activity` / `fetch_announcement` → 对应 client 方法 + 解析器（payload 为列表）
  - Task 5 `build_default_registry` 的 `try/except ImportError` 在本任务后自然生效，无需再改

- [ ] **Step 1: 写失败测试** `tests/adapters/test_wuwa_adapter.py`：

```python
import httpx
import respx

from game_assistant.adapters.wuthering_waves.adapter import WutheringWavesAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability

ROLE_RAW = {"code": 200, "msg": "success",
            "data": {"name": "漂泊者", "level": 80,
                     "energy": {"power": 180, "max": 240}}}


def _unconfigured():
    return WutheringWavesAdapter(Settings(wuwa_enabled=True))


async def test_unconfigured_reports_error():
    a = _unconfigured()
    assert a.credentials_configured is False
    for cap in a.capabilities:
        r = await a.fetch(cap)
        assert r.ok is False and "未配置凭据" in r.error


@respx.mock
async def test_fetch_stamina_ok():
    respx.post("https://api.kurobbs.com/gamer/aki/api/getRoleData").mock(
        return_value=httpx.Response(200, json=ROLE_RAW))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.STAMINA)
    assert r.ok is True and r.payload.current == 180


@respx.mock
async def test_fetch_account_ok():
    respx.post("https://api.kurobbs.com/gamer/aki/api/getRoleData").mock(
        return_value=httpx.Response(200, json=ROLE_RAW))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.ACCOUNT)
    assert r.ok is True and r.payload.nickname == "漂泊者"


@respx.mock
async def test_kuro_error_wrapped():
    respx.post("https://api.kurobbs.com/gamer/aki/api/getRoleData").mock(
        return_value=httpx.Response(200, json={"code": 220, "msg": "登录失效"}))
    a = WutheringWavesAdapter(Settings(wuwa_token="bad", wuwa_user_id="1"))
    r = await a.fetch(Capability.STAMINA)
    assert r.ok is False and "登录失效" in r.error
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/adapters/test_wuwa_adapter.py -v` → FAIL

- [ ] **Step 3: 实现** `adapter.py`：

```python
from datetime import datetime, timezone

from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.adapters.wuthering_waves import announcements, events, role
from game_assistant.adapters.wuthering_waves.kuro_client import KuroClient, KuroError
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult


class WutheringWavesAdapter(BaseGameAdapter):
    game_id = "wuthering_waves"
    display_name = "鸣潮"
    section = "mobile"
    capabilities = [Capability.ACCOUNT, Capability.STAMINA,
                    Capability.ACTIVITY, Capability.ANNOUNCEMENT]

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

    async def fetch_account(self) -> FetchResult:
        async def run():
            raw = await self._client.get_role_data()
            acc, _ = role.parse_role_data(raw, datetime.now(timezone.utc))
            return FetchResult(ok=True, payload=acc)
        return await self._guarded_run(run)

    async def fetch_stamina(self) -> FetchResult:
        async def run():
            raw = await self._client.get_role_data()
            _, st = role.parse_role_data(raw, datetime.now(timezone.utc))
            return FetchResult(ok=True, payload=st)
        return await self._guarded_run(run)

    async def fetch_activity(self) -> FetchResult:
        async def run():
            raw = await self._client.get_activity_list()
            return FetchResult(ok=True, payload=events.parse_activity_list(raw))
        return await self._guarded_run(run)

    async def fetch_announcement(self) -> FetchResult:
        async def run():
            raw = await self._client.get_announcement_list()
            return FetchResult(ok=True, payload=announcements.parse_announcement_list(raw))
        return await self._guarded_run(run)
```

- [ ] **Step 4: 运行全部测试** — Run: `.venv/Scripts/python.exe -m pytest -v` → 全部 PASS（build_default_registry 现在会注册鸣潮，test_api 的 create_app 默认路径不受影响，因为测试均显式注入 registry）

- [ ] **Step 5: 提交** — `git add src/game_assistant/adapters/wuthering_waves tests/adapters && git commit -m "feat: wuthering waves adapter with credential-aware fetching"`

---

### Task 15: 端到端联调验证与 README

**Files:**
- Create: `README.md`
- Modify: 无代码改动，仅验证与文档

- [ ] **Step 1: 启动后端**

```bash
.venv/Scripts/python.exe -m uvicorn game_assistant.main:app --port 8000
```

确认：`GET http://127.0.0.1:8000/api/games` 返回 wuthering_waves 且 `credentials_configured=false`；启动日志显示 4 个轮询 job 注册（account/stamina/activity/announcement）。

- [ ] **Step 2: 启动前端并人工过一遍**

`cd frontend && npm run dev` → 打开 http://localhost:5173，核对 Task 10 验证点 + 卡片能力区块齐全（账号/体力/活动/公告）。

- [ ] **Step 3: 真实凭据验证（可选，需用户提供 token）**

指导用户：浏览器登录 kurobbs.com → F12 → Network → 任选请求复制 `token` 请求头与数字 `userId` → 填入 `config.toml` 的 `wuwa_token/wuwa_user_id` → 重启后端 → 手动 refresh → 页面应显示真实体力/等级/活动/公告。若某接口报"接口错误"，回 Task 11 Step 5 校准流程。

- [ ] **Step 4: 写 README.md**

内容必须包含：项目简介（指向 docs/需求文档.md）；启动步骤（后端 uvicorn、前端 vite dev、生产 `npm run build` + FastAPI StaticFiles 托管说明）；config.toml 配置项说明（照 config.example.toml 注释）；鸣潮 token 抓取步骤（Task 15 Step 3 原文）；微信推送启用步骤（Server酱/PushPlus 注册 → send_key 填入 config.toml → 重启即生效，未配置时显示"提醒渠道未启用"属预期）；已知限制（非官方接口可能随上游变动，失效时按 endpoints.py 校准流程修复）。

- [ ] **Step 5: 全量回归 + 提交**

Run: `.venv/Scripts/python.exe -m pytest -v` → 全部 PASS

```bash
git add README.md docs
git commit -m "docs: README with setup, credential capture and notify guide"
```

---

## 后续计划（不在本计划内）

- **M2 计划**：LoL 适配器（官网公告/资讯爬取 + 掌盟 Cookie 账号/战绩），需要用户提供 Cookie。
- **M3 计划**：提醒规则引擎（体力满阈值可配、活动临期 N 天提醒、凭据失效提醒）、活动日历视图、微信推送真实联调（用户届时提供 SendKey）。
- **M4 计划**：签到、资讯聚合、第二轮游戏评估。
