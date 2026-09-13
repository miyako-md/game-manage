# 个人游戏资讯助手 M2 实现计划（LoL 适配器 + 框架清理）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现英雄联盟适配器（账号信息、战绩查询、版本公告、资讯四项能力），并完成 M0+M1 最终审查遗留的框架清理。

**Architecture:** 沿用既有适配器架构。LoL 的账号/战绩走 **LCU 本地客户端 API**（参考用户本地项目 C:\GPT\LOLhelper 的已验证实现）：从 `LeagueClientUx` 进程命令行或 lockfile 发现凭据，`https://127.0.0.1:{port}` + Basic `riot:{token}` 访问（本机自签证书跳过校验——仅限 LCU）。公告/资讯走 lol.qq.com 官网爬取（无需凭据）。客户端未运行时账号/战绩能力返回错误"LOL 客户端未运行"，快照保留旧数据（失效隔离）。

**Tech Stack:** 既有栈 + psutil（进程扫描）。新增 LCU/官网客户端均 httpx + respx 离线测试。

**Spec:** `docs/需求文档.md` §3.1（PC 板块四能力）、§4.1（渠道）、§7（M2 里程碑）。**路线裁定**：用户指定参考 LOLhelper（LCU 路线），账号/战绩主渠道由掌盟 Cookie 改为 LCU 本地接口；掌盟 Cookie 渠道降级为未来备选（M3+ 评估）。

## Global Constraints

- 所有 M0+M1 全局约束继续生效（离线测试、凭据治理、conventional commits、拉取失败不覆盖快照）。
- **LCU 凭据发现顺序**（来自 LOLhelper 验证）：①psutil 扫描 `LeagueClientUx` 进程命令行的 `--app-port=` / `--remoting-auth-token=`（国服 WeGame lockfile 常为 0 字节，此为主路径）；②非空 lockfile（`pid:port:token:proto`）兜底。发现失败 → `LcuUnavailableError`。
- **SSL 跳过校验仅限 127.0.0.1 的 LCU 请求**（Riot 自签证书，业界通行做法）；官网/公网请求一律正常校验——两套 client 不得共享 ssl 配置（LOLhelper lcu.py 注释原文约束）。
- 官网请求需带 `Referer: https://lol.qq.com/` 与常规 UA（腾讯接口常校验 Referer）。
- 轮询间隔：account/match → activity_seconds（3600）；announcement → announcement_seconds（3600）；news → news_seconds（14400）。
- 战绩仅自己账号（spec 决策 #5）：match 解析需要 own_puuid 定位自己的 participant。
- LCU 响应字段名以 LOLhelper 验证过的为准：game 级 `gameId/queueId/gameMode/gameCreation(毫秒)/gameDuration/gameVersion/teams[]{teamId,win:"Win"}/participantIdentities[]{participantId,player{puuid,summonerId,gameName,tagLine}}/participants[]{participantId,championId,teamId,stats{...}}`；stats 级 `kills/deaths/assists/totalDamageDealtToChampions/goldEarned/win(bool)`；summoner 级 `summonerId/puuid/gameName/name/summonerLevel/profileIconId`。历史列表取 `raw["games"]["games"]`。
- 排位信息走 `/lol-ranked/v1/ranked-stats/{puuid}` 的 `queueMap.RANKED_SOLO_5x5`（LOLhelper 未用此端点，字段名按标准 LCU，防御式解析，M2 Task 10 实测校准）。
- 官网新闻 JSON 端点未能在计划期锁定（页面 JS 渲染 + GBK）——Task 7 含**必做在线校准步骤**，模式同 M1 Task 11：候选端点逐一 WebFetch 验证，结论写入 endpoints.py 注释，测试 fixture 以真实样本为准。

---

### Task 1: 框架清理批次（M0+M1 最终审查遗留）

**Files:**
- Modify: `tests/test_api.py`, `src/game_assistant/scheduler.py`, `src/game_assistant/api.py`, `src/game_assistant/adapters/wuthering_waves/role.py`, `tests/adapters/test_role_parse.py`, `src/game_assistant/config.py`, `config.example.toml`, `src/game_assistant/registry.py`
- Test: `tests/test_config.py`（如需）

**Interfaces:**
- Produces: `scheduler.interval_for(capability: Capability, settings: Settings) -> int`（api.py 改用之，删除其本地映射）；`role.py` 的 `expected_full_at` 两个分支统一为 **aware UTC**；Settings 增加环境变量前缀 `GA_`；`lol_enabled: bool = True` 字段（Task 8 用）。

- [ ] **Step 1: 写失败测试（环境隔离 + 时区契约）**

`tests/test_api.py` 的 `_app_with` 改为显式传 `Settings(notify_send_key="")`（不再依赖 CWD config.toml/环境变量）：

```python
from game_assistant.config import Settings

def _app_with(tmp_path, snapshots=None):
    store = SnapshotStore(str(tmp_path / "t.db"))
    for gid, cap, payload in (snapshots or []):
        store.save(gid, cap, payload)
    client = TestClient(create_app(
        registry=FakeRegistry(DummyAdapter()), store=store,
        settings=Settings(notify_send_key="", db_path=str(tmp_path / "unused.db"))))
    return client, store
```

`tests/adapters/test_role_parse.py` 的 `test_stamina_eta_from_refresh_timestamp` 断言改为 aware：

```python
def test_stamina_eta_from_refresh_timestamp():
    raw = {"code": 200, "data": {"energy": {"power": 200, "max": 240,
                                            "refreshTimestamp": 1788525600000}}}
    _, st = parse_role_data(raw, NOW)
    assert st.expected_full_at == datetime.fromtimestamp(1788525600, tz=timezone.utc)
```

（文件顶部补 `timezone` 导入。）

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py tests/adapters/test_role_parse.py -v` → 时区测试 FAIL（现在是无 tz 的 naive）

- [ ] **Step 3: 实现**

- `role.py`：`datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)`（`timezone` 导入恢复）。
- `scheduler.py`：新增函数并让 `build_jobs` 复用：

```python
def interval_for(capability: Capability, settings: Settings) -> int:
    return getattr(settings, INTERVAL_ATTRS[capability])
```

`build_jobs` 中 `secs = getattr(...)` 改为 `secs = interval_for(cap, self.settings)`。
- `api.py`：snapshot 路由的本地 interval 映射 dict 删除，改为：

```python
from game_assistant.models import Capability
from game_assistant.scheduler import interval_for
...
interval = interval_for(Capability(capability), settings) if capability in [c.value for c in Capability] else 3600
```

（更简单直接的写法：`try: interval = interval_for(Capability(capability), settings) except (KeyError, ValueError): interval = 3600`——Capability("news") 合法所以实际只有未知能力字符串走 except。）
- `config.py`：`class Settings(BaseSettings):` 增加类配置（pydantic-settings v2 写法）：

```python
    lol_enabled: bool = True

    model_config = {"env_prefix": "GA_"}
```

- `config.example.toml`：追加两行注释说明"环境变量需 GA_ 前缀（如 GA_NOTIFY_SEND_KEY）；lol_enabled 控制英雄联盟适配器开关"。
- `registry.py`：`build_default_registry` 的 `except ImportError: pass` 改为：

```python
        except ImportError:
            import logging
            logging.getLogger(__name__).warning(
                "鸣潮适配器导入失败，跳过注册（检查依赖完整性）", exc_info=True)
```

并在 wuwa 块之后添加 LOL 占位（Task 8 前不生效，模式与 wuwa 相同）：

```python
    if settings.lol_enabled:
        try:
            from game_assistant.adapters.league_of_legends.adapter import LeagueOfLegendsAdapter
        except ImportError:
            import logging
            logging.getLogger(__name__).warning(
                "英雄联盟适配器导入失败，跳过注册（Task 8 完成前属预期）", exc_info=True)
        else:
            registry.register(LeagueOfLegendsAdapter(settings))
```

- [ ] **Step 4: 运行全量确认通过** — Run: `.venv/Scripts/python.exe -m pytest -q` → 41 passed（role 时区测试转绿；test_api 不再依赖环境）

- [ ] **Step 5: 提交** — `git add -A src tests config.example.toml && git commit -m "chore: m2 framework cleanups (test isolation, interval dedup, aware timestamps, env prefix)"`

---

### Task 2: Capability.MATCH 与 MatchSummary 模型

**Files:**
- Modify: `src/game_assistant/models.py`, `src/game_assistant/scheduler.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `Capability.MATCH = "match"`；`MatchSummary(match_id: str, queue_id: int | None = None, mode: str = "", start_at: datetime | None = None, duration_seconds: int | None = None, win: bool | None = None, champion_id: int | None = None, kills: int | None = None, deaths: int | None = None, assists: int | None = None)`；`INTERVAL_ATTRS` 增加 `Capability.MATCH: "activity_seconds"`。

- [ ] **Step 1: 写失败测试** `tests/test_models.py` 追加：

```python
from game_assistant.models import MatchSummary


def test_capability_match_value():
    assert Capability.MATCH == "match"


def test_match_summary_roundtrip():
    m = MatchSummary(match_id="1234567890", queue_id=450, mode="ARAM",
                     start_at=datetime(2026, 9, 13, 20, 0, tzinfo=None),
                     duration_seconds=1234, win=True, champion_id=157,
                     kills=8, deaths=3, assists=10)
    assert MatchSummary.model_validate(m.model_dump()) == m
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -v` → FAIL（无 MATCH/MatchSummary）

- [ ] **Step 3: 实现** — models.py：Capability 加 `MATCH = "match"`；新增 MatchSummary 类（字段见 Interfaces）。scheduler.py：INTERVAL_ATTRS 加 `Capability.MATCH: "activity_seconds"`。

- [ ] **Step 4: 运行确认通过** — Run: `.venv/Scripts/python.exe -m pytest -q` → 43 passed

- [ ] **Step 5: 提交** — `git add src/game_assistant/models.py src/game_assistant/scheduler.py tests/test_models.py && git commit -m "feat: match capability and match summary model"`

---

### Task 3: LCU 凭据发现

**Files:**
- Create: `src/game_assistant/adapters/league_of_legends/__init__.py`（空）, `src/game_assistant/adapters/league_of_legends/lcu_discovery.py`
- Modify: `pyproject.toml`（dependencies 加 `"psutil>=5.9"`）
- Test: `tests/adapters/test_lcu_discovery.py`

**Interfaces:**
- Produces:
  - `LOCKFILE_CANDIDATES: list[Path]`（LOLhelper 同款候选列表）
  - `find_credentials_from(processes: Iterable[tuple[str, list[str] | None]]) -> tuple[str, str] | None` — 纯函数：扫描 (进程名, 命令行) 序列，匹配进程名含 "LeagueClientUx" 且命令行有 `--app-port=`/`--remoting-auth-token=`，返回 `(port, token)`（str）；无则 None
  - `find_lockfile_credentials(candidates: list[Path] = LOCKFILE_CANDIDATES) -> tuple[str, str] | None` — 读首个非空 lockfile，标准 Riot 格式 `PID:Port:Password:Protocol` → `(port, token) = (parts[1], parts[2])`。**注意**：LOLhelper lcu.py:132 取 `parts[2], parts[3]` 当 (port, token)，与标准格式不符（会把 Password 当 Port）——该分支在其项目极少执行（国服主路径是进程发现），本实现采用标准格式，注释记录此差异
  - `discover_lcu_credentials() -> tuple[str, str] | None` — psutil 扫描（进程名+cmdline 序列喂给 find_credentials_from）→ lockfile 兜底；psutil 缺失或未找到返回 None；psutil 导入失败返回 None 并 log.warning

- [ ] **Step 1: 写失败测试** `tests/adapters/test_lcu_discovery.py`：

```python
from pathlib import Path

from game_assistant.adapters.league_of_legends.lcu_discovery import (
    find_credentials_from, find_lockfile_credentials,
)


def test_find_from_process_cmdline():
    procs = [("chrome.exe", ["--x"]), (
        "LeagueClientUx.exe",
        ["--app-port=54321", "--remoting-auth-token=abcTOKEN", "--install-path=D:/x"],
    )]
    assert find_credentials_from(procs) == ("54321", "abcTOKEN")


def test_find_from_process_not_running():
    assert find_credentials_from([("chrome.exe", ["--x"])]) is None


def test_find_from_process_malformed():
    procs = [("LeagueClientUx.exe", ["--app-port=54321"])]  # 缺 token
    assert find_credentials_from(procs) is None


def test_lockfile(tmp_path, monkeypatch):
    lf = tmp_path / "lockfile"
    lf.write_text("1234:54321:abcTOKEN:https", encoding="utf-8")
    assert find_lockfile_credentials([lf]) == ("54321", "abcTOKEN")


def test_lockfile_empty_and_missing(tmp_path):
    empty = tmp_path / "empty.lock"
    empty.write_text("", encoding="utf-8")
    assert find_lockfile_credentials([empty, tmp_path / "nope"]) is None
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/adapters/test_lcu_discovery.py -v` → FAIL

- [ ] **Step 3: 实现** `lcu_discovery.py`：

```python
"""LCU 凭据发现。校准来源：C:\\GPT\\LOLhelper pigeon/lcu.py（国服 WeGame 已验证）。

国服 WeGame 的 lockfile 常为 0 字节，主路径是从 LeagueClientUx 进程
命令行提取 --app-port / --remoting-auth-token（psutil）。
"""
import logging
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger(__name__)

LOCKFILE_CANDIDATES = [
    Path(r"C:\WeGameApps\英雄联盟\LeagueClient\lockfile"),
    Path(r"C:\Riot Games\英雄联盟\lockfile"),
    Path(r"C:\Riot Games\League of Legends\lockfile"),
    Path(r"D:\WeGameApps\英雄联盟\LeagueClient\lockfile"),
    Path(r"D:\Riot Games\英雄联盟\lockfile"),
    Path(r"D:\Riot Games\League of Legends\lockfile"),
]


def find_credentials_from(
    processes: Iterable[tuple[str, list[str] | None]],
) -> tuple[str, str] | None:
    port = token = None
    for name, cmd in processes:
        if "LeagueClientUx" not in (name or "") or not cmd:
            continue
        for arg in cmd:
            if arg.startswith("--app-port="):
                port = arg.split("=", 1)[1]
            elif arg.startswith("--remoting-auth-token="):
                token = arg.split("=", 1)[1]
        if port and token:
            return port, token
    return None


def find_lockfile_credentials(
    candidates: list[Path] = LOCKFILE_CANDIDATES,
) -> tuple[str, str] | None:
    # 标准 Riot lockfile 格式 PID:Port:Password:Protocol。
    # 差异记录：LOLhelper lcu.py 取 parts[2],parts[3] 当 (port,token)，与标准格式
    # 不符（其国服主路径是进程发现，此分支极少执行）；本实现按标准格式。
    for p in candidates:
        try:
            if p.exists() and p.stat().st_size > 0:
                parts = p.read_text(encoding="utf-8", errors="replace").strip().split(":")
                if len(parts) >= 4:
                    return parts[1], parts[2]
        except OSError:
            continue
    return None


def discover_lcu_credentials() -> tuple[str, str] | None:
    try:
        import psutil
    except ImportError:
        logger.warning("psutil 未安装，无法扫描 LCU 进程")
        return None
    procs = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            procs.append((proc.info.get("name") or "", proc.info.get("cmdline")))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    creds = find_credentials_from(procs)
    if creds:
        return creds
    return find_lockfile_credentials()
```

`pyproject.toml` dependencies 数组加 `"psutil>=5.9"` 并 `pip install -e ".[dev]"`。

- [ ] **Step 4: 运行确认通过** — Run: `.venv/Scripts/python.exe -m pytest tests/adapters/test_lcu_discovery.py -q` → 5 passed

- [ ] **Step 5: 提交** — `git add src/game_assistant/adapters/league_of_legends tests/adapters/test_lcu_discovery.py pyproject.toml && git commit -m "feat: LCU credential discovery (process cmdline + lockfile fallback)"`

---

### Task 4: LcuClient

**Files:**
- Create: `src/game_assistant/adapters/league_of_legends/lcu_client.py`
- Modify: `src/game_assistant/adapters/league_of_legends/endpoints.py`（新建，先只放 LCU 路径）
- Test: `tests/adapters/test_lcu_client.py`

**Interfaces:**
- Produces（endpoints.py，含来源注释）：
  ```python
  # LCU 路径（校准来源：C:\GPT\LOLhelper pigeon/lcu.py 已验证 + 标准 LCU）
  SUMMONER_CURRENT = "/lol-summoner/v1/current-summoner"          # 已验证
  GAMEFLOW_PHASE = "/lol-gameflow/v1/gameflow-phase"              # 已验证
  RANKED_STATS = "/lol-ranked/v1/ranked-stats/{puuid}"            # 未验证，Task 10 校准
  MATCH_HISTORY = "/lol-match-history/v1/products/lol/{puuid}/matches?count={count}&startIndex=0"  # 已验证
  GAME_DETAIL = "/lol-match-history/v1/games/{game_id}"           # 已验证（LOLhelper collector）
  ```
- `LcuError(Exception)`（message 属性）；`LcuUnavailableError(LcuError)`。
- `LcuClient(port: str, token: str)`：`base_url=https://127.0.0.1:{port}`、`headers={"Authorization": "Basic " + b64(f"riot:{token}")}`、`verify=False`（**仅限本机 LCU**——注释约束原文：证书为 Riot 自签且每次安装不同，业界通行做法是跳过校验，此配置不得复用于公网请求）、timeout=15。
  - `async get(path: str) -> dict`：HTTP 状态 != 200 → `LcuError(f"HTTP {resp.status_code}")`；非 JSON → `LcuError("响应非 JSON")`；返回 dict。
  - `async current_summoner() -> dict`；`async ranked_stats(puuid: str) -> dict`；`async match_history(puuid: str, count: int = 20) -> dict`（路径模板格式化）；`async game_detail(game_id: str) -> dict`。
  - httpx 网络异常 → `LcuUnavailableError(f"LCU 连接失败: {type(e).__name__}")`（客户端中途退出）。

- [ ] **Step 1: 写失败测试** `tests/adapters/test_lcu_client.py`：

```python
import base64

import httpx
import pytest
import respx

from game_assistant.adapters.league_of_legends.lcu_client import (
    LcuClient, LcuError, LcuUnavailableError,
)

BASE = "https://127.0.0.1:54321"


def _client() -> LcuClient:
    return LcuClient(port="54321", token="abcTOKEN")


@respx.mock
async def test_get_with_basic_auth():
    route = respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        return_value=httpx.Response(200, json={"puuid": "P1", "summonerLevel": 160}))
    data = await _client().current_summoner()
    assert data["puuid"] == "P1"
    req = route.calls.last.request
    expect = base64.b64encode(b"riot:abcTOKEN").decode()
    assert req.headers["Authorization"] == f"Basic {expect}"


@respx.mock
async def test_http_error_raises():
    respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        return_value=httpx.Response(404, text="nope"))
    with pytest.raises(LcuError) as ei:
        await _client().current_summoner()
    assert "404" in str(ei.value)


@respx.mock
async def test_non_json_raises():
    respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        return_value=httpx.Response(200, text="<html>gateway</html>"))
    with pytest.raises(LcuError):
        await _client().current_summoner()


@respx.mock
async def test_network_error_is_unavailable():
    respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        side_effect=httpx.ConnectError("refused"))
    with pytest.raises(LcuUnavailableError):
        await _client().current_summoner()


@respx.mock
async def test_match_history_formats_path():
    route = respx.get(f"{BASE}/lol-match-history/v1/products/lol/P1/matches").mock(
        return_value=httpx.Response(200, json={"games": {"games": []}}))
    await _client().match_history("P1", count=20)
    assert "count=20" in str(route.calls.last.request.url)
```

- [ ] **Step 2: 运行确认失败** — Run: `.venv/Scripts/python.exe -m pytest tests/adapters/test_lcu_client.py -v` → FAIL

- [ ] **Step 3: 实现** `endpoints.py` + `lcu_client.py`：

```python
"""LoL 数据端点。LCU 路径校准来源：C:\\GPT\\LOLhelper pigeon/lcu.py 与 collector.py。"""
SUMMONER_CURRENT = "/lol-summoner/v1/current-summoner"   # LOLhelper 已验证
GAMEFLOW_PHASE = "/lol-gameflow/v1/gameflow-phase"       # LOLhelper 已验证
RANKED_STATS = "/lol-ranked/v1/ranked-stats/{puuid}"     # 未验证，Task 10 校准
MATCH_HISTORY = ("/lol-match-history/v1/products/lol/{puuid}"
                 "/matches?count={count}&startIndex=0")  # LOLhelper 已验证
GAME_DETAIL = "/lol-match-history/v1/games/{game_id}"    # LOLhelper collector 已验证
```

```python
"""LCU 本机客户端。校准来源：C:\\GPT\\LOLhelper pigeon/lcu.py。

SSL 约束（LOLhelper 原文）：LCU 是 127.0.0.1 本机进程，证书为 Riot 自签且
每次安装不同，业界通行做法就是跳过校验。此上下文只能用于本机 LCU 请求，
任何公网请求一律走系统默认校验，不得复用这里的配置。
"""
import base64
import logging

import httpx

from game_assistant.adapters.league_of_legends.endpoints import (
    GAME_DETAIL, MATCH_HISTORY, RANKED_STATS, SUMMONER_CURRENT,
)

logger = logging.getLogger(__name__)


class LcuError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class LcuUnavailableError(LcuError):
    pass


class LcuClient:
    def __init__(self, port: str, token: str):
        auth = base64.b64encode(f"riot:{token}".encode()).decode()
        self._client = httpx.AsyncClient(
            base_url=f"https://127.0.0.1:{port}",
            headers={"Authorization": f"Basic {auth}"},
            verify=False,  # 仅限本机 LCU 自签证书，见模块 docstring
            timeout=15,
        )

    async def get(self, path: str) -> dict:
        try:
            resp = await self._client.get(path)
        except httpx.HTTPError as e:
            raise LcuUnavailableError(f"LCU 连接失败: {type(e).__name__}") from e
        if resp.status_code != 200:
            raise LcuError(f"HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as e:
            raise LcuError("响应非 JSON") from e
        if not isinstance(data, dict):
            raise LcuError("响应结构异常")
        return data

    async def current_summoner(self) -> dict:
        return await self.get(SUMMONER_CURRENT)

    async def ranked_stats(self, puuid: str) -> dict:
        return await self.get(RANKED_STATS.format(puuid=puuid))

    async def match_history(self, puuid: str, count: int = 20) -> dict:
        return await self.get(MATCH_HISTORY.format(puuid=puuid, count=count))

    async def game_detail(self, game_id: str) -> dict:
        return await self.get(GAME_DETAIL.format(game_id=game_id))
```

- [ ] **Step 4: 运行确认通过** — Run: `.venv/Scripts/python.exe -m pytest tests/adapters/test_lcu_client.py -q` → 5 passed

- [ ] **Step 5: 提交** — `git add src/game_assistant/adapters/league_of_legends tests/adapters/test_lcu_client.py && git commit -m "feat: local LCU client with riot basic auth and error contract"`

---

### Task 5: summoner/ranked 解析

**Files:**
- Create: `src/game_assistant/adapters/league_of_legends/summoner.py`
- Test: `tests/adapters/test_summoner_parse.py`

**Interfaces:**
- Produces: `parse_summoner(raw: dict, ranked_raw: dict | None) -> AccountInfo`
  - `nickname = raw.get("gameName") or raw.get("name")`；`level = raw.get("summonerLevel")`
  - `extra = {"puuid": raw.get("puuid"), "profile_icon_id": raw.get("profileIconId"), "ranked_solo": None | {"tier": str, "division": str, "league_points": int, "wins": int, "losses": int}}`
  - ranked：`ranked_raw["queueMap"]["RANKED_SOLO_5x5"]` 的 `tier/division/leaguePoints/wins/losses`，缺失或空 dict → `ranked_solo=None`（defensive，Task 10 校准）

- [ ] **Step 1: 写失败测试** `tests/adapters/test_summoner_parse.py`：

```python
from game_assistant.adapters.league_of_legends.summoner import parse_summoner

RAW = {"summonerId": 123, "puuid": "P1", "gameName": "峡谷小毕",
       "name": "旧名", "summonerLevel": 160, "profileIconId": 5553}
RANKED = {"queueMap": {"RANKED_SOLO_5x5": {
    "tier": "EMERALD", "division": "II", "leaguePoints": 33,
    "wins": 120, "losses": 110}}}


def test_parse_summoner_basic():
    acc = parse_summoner(RAW, None)
    assert acc.nickname == "峡谷小毕" and acc.level == 160
    assert acc.extra["puuid"] == "P1"
    assert acc.extra["ranked_solo"] is None


def test_parse_summoner_ranked():
    acc = parse_summoner(RAW, RANKED)
    rs = acc.extra["ranked_solo"]
    assert rs["tier"] == "EMERALD" and rs["league_points"] == 33


def test_parse_summoner_ranked_missing_queue():
    acc = parse_summoner(RAW, {"queueMap": {}})
    assert acc.extra["ranked_solo"] is None
```

- [ ] **Step 2: 运行确认失败** → FAIL

- [ ] **Step 3: 实现**：

```python
from game_assistant.models import AccountInfo


def parse_summoner(raw: dict, ranked_raw: dict | None) -> AccountInfo:
    ranked = None
    qm = (ranked_raw or {}).get("queueMap") or {}
    solo = qm.get("RANKED_SOLO_5x5") or {}
    if solo:
        ranked = {
            "tier": solo.get("tier"), "division": solo.get("division"),
            "league_points": solo.get("leaguePoints"),
            "wins": solo.get("wins"), "losses": solo.get("losses"),
        }
    return AccountInfo(
        nickname=raw.get("gameName") or raw.get("name"),
        level=raw.get("summonerLevel"),
        extra={"puuid": raw.get("puuid"), "profile_icon_id": raw.get("profileIconId"),
               "ranked_solo": ranked},
    )
```

- [ ] **Step 4: 运行确认通过** → 3 passed
- [ ] **Step 5: 提交** — `git add src/game_assistant/adapters/league_of_legends/summoner.py tests/adapters/test_summoner_parse.py && git commit -m "feat: parse LCU summoner and ranked stats into account model"`

---

### Task 6: matches 解析

**Files:**
- Create: `src/game_assistant/adapters/league_of_legends/matches.py`
- Test: `tests/adapters/test_matches_parse.py`

**Interfaces:**
- Produces: `parse_match_history(raw: dict, own_puuid: str) -> list[MatchSummary]`
  - 遍历 `raw["games"]["games"]`（缺失 → []）；每场：
    - `match_id = str(game.get("gameId"))`（缺失跳过）
    - `start_at = datetime.fromtimestamp(game["gameCreation"]/1000, tz=timezone.utc)`（gameCreation 缺失 → None）
    - `duration_seconds = game.get("gameDuration")`、`mode = game.get("gameMode")`、`queue_id = game.get("queueId")`
    - 定位自己：`participantIdentities[].player.puuid == own_puuid` → participantId → `participants[]` 中同 participantId 的项；stats 取 `kills/deaths/assists/championId`（participant 级）；`win = stats.get("win")`（bool，直接用）
    - 找不到自己 → 该场 MatchSummary 的 win/kda/champion 为 None（保 match_id/时间/模式）
    - 胜负兜底（stats.win 缺失时）：`teams[]` 中 `win == "Win"` 的 teamId 与自己 `teamId` 比较（LOLhelper 验证的口径）

- [ ] **Step 1: 写失败测试** `tests/adapters/test_matches_parse.py`：

```python
from datetime import datetime, timezone

from game_assistant.adapters.league_of_legends.matches import parse_match_history

# fixture 形状校准来源：C:\GPT\LOLhelper pigeon/collector.py _payload_from_lcu（真实数据验证）
GAME = {
    "gameId": 1234567890, "queueId": 450, "gameMode": "ARAM",
    "gameCreation": 1788525600000, "gameDuration": 1234,
    "teams": [{"teamId": 100, "win": "Win"}, {"teamId": 200, "win": "Fail"}],
    "participantIdentities": [
        {"participantId": 1, "player": {"puuid": "ME", "summonerId": 9}},
        {"participantId": 2, "player": {"puuid": "OTHER"}},
    ],
    "participants": [
        {"participantId": 1, "championId": 157, "teamId": 100,
         "stats": {"kills": 8, "deaths": 3, "assists": 10, "win": True}},
        {"participantId": 2, "championId": 22, "teamId": 200,
         "stats": {"kills": 2, "deaths": 8, "assists": 4, "win": False}},
    ],
}


def test_parse_own_summary():
    items = parse_match_history({"games": {"games": [GAME]}}, "ME")
    assert len(items) == 1
    m = items[0]
    assert m.match_id == "1234567890" and m.queue_id == 450 and m.mode == "ARAM"
    assert m.start_at == datetime.fromtimestamp(1788525600, tz=timezone.utc)
    assert m.duration_seconds == 1234
    assert m.win is True and m.champion_id == 157
    assert (m.kills, m.deaths, m.assists) == (8, 3, 10)


def test_parse_other_puuid_skipped():
    items = parse_match_history({"games": {"games": [GAME]}}, "NOT-ME")
    assert items[0].kills is None and items[0].win is None


def test_win_fallback_from_teams():
    game = {**GAME, "participants": [
        {**GAME["participants"][0],
         "stats": {"kills": 1, "deaths": 2, "assists": 3}}]}
    items = parse_match_history({"games": {"games": [game]}}, "ME")
    assert items[0].win is True  # teams[0].win == "Win" 且自己 teamId=100


def test_empty_history():
    assert parse_match_history({}, "ME") == []
```

- [ ] **Step 2: 运行确认失败** → FAIL

- [ ] **Step 3: 实现**：

```python
from datetime import datetime, timezone

from game_assistant.models import MatchSummary


def _own_summary(game: dict, own_puuid: str) -> MatchSummary:
    creation = game.get("gameCreation")
    start_at = (datetime.fromtimestamp(creation / 1000, tz=timezone.utc)
                if creation else None)
    ident_pid = None
    for ident in game.get("participantIdentities") or []:
        if (ident.get("player") or {}).get("puuid") == own_puuid:
            ident_pid = ident.get("participantId")
            break
    champion = kills = deaths = assists = team = win = None
    for p in game.get("participants") or []:
        if p.get("participantId") != ident_pid:
            continue
        stats = p.get("stats") or {}
        champion, team = p.get("championId"), p.get("teamId")
        kills, deaths, assists = (stats.get("kills"), stats.get("deaths"),
                                  stats.get("assists"))
        win = stats.get("win") if isinstance(stats.get("win"), bool) else None
        break
    if win is None and team is not None:
        for t in game.get("teams") or []:
            if t.get("win") == "Win" and t.get("teamId") == team:
                win = True
            elif t.get("teamId") == team:
                win = False
    return MatchSummary(
        match_id=str(game.get("gameId")), queue_id=game.get("queueId"),
        mode=game.get("gameMode") or "", start_at=start_at,
        duration_seconds=game.get("gameDuration"),
        win=win, champion_id=champion,
        kills=kills, deaths=deaths, assists=assists,
    )


def parse_match_history(raw: dict, own_puuid: str) -> list[MatchSummary]:
    games = ((raw or {}).get("games") or {}).get("games") or []
    out = []
    for game in games:
        if not game.get("gameId"):
            continue
        out.append(_own_summary(game, own_puuid))
    return out
```

- [ ] **Step 4: 运行确认通过** → 4 passed
- [ ] **Step 5: 提交** — `git add src/game_assistant/adapters/league_of_legends/matches.py tests/adapters/test_matches_parse.py && git commit -m "feat: parse LCU match history into own-side match summaries"`

---

### Task 7: 官网公告/资讯客户端与解析（含必做在线校准）

**Files:**
- Create: `src/game_assistant/adapters/league_of_legends/lol_news.py`
- Modify: `src/game_assistant/adapters/league_of_legends/endpoints.py`（追加官网新闻候选常量）
- Test: `tests/adapters/test_lol_news.py`

**Interfaces:**
- endpoints.py 追加（初值，校准后以结论为准）：
  ```python
  # 官网新闻（未在计划期锁定——Task 7 Step 5 在线校准，结论写回此处注释）
  NEWS_PAGE = "https://lol.qq.com/news/index.shtml"   # 分类：综合新闻/官方公告/赛事新闻
  NEWS_JSON_CANDIDATES = [
      "https://lol.qq.com/act/lbcp/json/news_list.json",
  ]
  ```
- `LoLNewsClient()`：普通 httpx（正常 SSL 校验），headers 含 `Referer: https://lol.qq.com/` 与 UA；`async fetch_json(url) -> dict`；`async fetch_page(url) -> str`（GBK 解码：`resp.content.decode("gbk", errors="replace")`）。
- `parse_news_json(data: dict, category: str) -> list[AnnouncementItem]` — category 为校准确认的分类标识（如 "公告"/"官方公告"）；键名防御式（title/summary/createDate/sDate/time、url/sUrl/link，data 与 data.list 两种形状都试，模式同 events.py）。
- `parse_news_html(html: str, category: str) -> list[AnnouncementItem]` — 备选：按校准得到的真实 DOM 结构实现（Step 5 必须带回真实样本）。校准若确认 JSON 端点可用，本函数可只写骨架返回 [] 并注明"JSON 路径已足够"？——**不行**：无 placeholder 规则。裁定：校准若确认 JSON 可用，则 parse_news_html 不实现、不建（Files 相应缩减，测试只覆盖 JSON 路径）；校准若只能走 HTML，则按真实 DOM 实现并配 fixture。**Step 5 的校准结论决定本任务最终形态，两种结局都算合规。**

- [ ] **Step 1: 写失败测试**（先按 JSON 形状假设写，Step 5 校准后以真实样本修正 fixture）：

```python
from game_assistant.adapters.league_of_legends.lol_news import parse_news_json

RAW = {"newsList": [
    {"title": "26.18版本更新公告", "sDate": "2026-09-11",
     "sUrl": "https://lol.qq.com/news/detail.shtml?nid=1"},
    {"title": "峡谷之巅2026第二赛段奖励公告", "sDate": "2026-09-11",
     "sUrl": "https://lol.qq.com/news/detail.shtml?nid=2"},
]}


def test_parse_news_json():
    items = parse_news_json(RAW, "官方公告")
    assert len(items) == 2
    assert items[0].title == "26.18版本更新公告"
    assert items[0].url == RAW["newsList"][0]["sUrl"]
    assert items[0].published_at is not None
```

- [ ] **Step 2: 运行确认失败** → FAIL
- [ ] **Step 3: 实现 parse_news_json + LoLNewsClient**（键名防御式：title、日期键依次 `sDate/createDate/date/time`、链接键依次 `sUrl/url/jumpUrl/link`；形状试 `data["newsList"]`、`data["list"]`、data 本身是 list；日期 `datetime.fromisoformat` 失败→None）
- [ ] **Step 4: 运行确认通过** → 1 passed
- [ ] **Step 5: 在线校准（必做，模式同 M1 Task 11）**：WebFetch 逐一验证 `NEWS_JSON_CANDIDATES`；再 WebFetch `https://lol.qq.com/v2/` 与 `NEWS_PAGE`（提示词要求列出 XHR 接口与新闻 DOM 结构）。结论三种：①JSON 端点可用 → 端点与真实样本写入 endpoints.py 注释，parse_news_json 键名/分类标识对齐真实样本，fixture 改为真实样本；②只有 HTML 可用 → 保存真实 DOM 结构描述，实现 parse_news_html（真实样本进 fixture），fetch 逻辑走 fetch_page；③均不可行 → 实现保留 JSON 解析（以假设形状测试），endpoints.py 注释如实标注"未校准，需浏览器 DevTools 人工确认"，报告 BLOCKED_NOTES 记录。无论哪种，把分类标识（公告 vs 新闻如何区分）一并校准——ANNOUNCEMENT 与 NEWS 两能力共用端点、按分类过滤。
- [ ] **Step 6: 重跑测试** → 通过
- [ ] **Step 7: 提交** — `git add src/game_assistant/adapters/league_of_legends tests/adapters/test_lol_news.py && git commit -m "feat: lol.qq.com news client with calibrated parse"`

---

### Task 8: LeagueOfLegendsAdapter 组装与注册

**Files:**
- Create: `src/game_assistant/adapters/league_of_legends/adapter.py`
- Test: `tests/adapters/test_lol_adapter.py`

**Interfaces:**
- `LeagueOfLegendsAdapter(settings)`：`game_id="league_of_legends"`、`display_name="英雄联盟"`、`section="pc"`、`capabilities=[ACCOUNT, MATCH, ANNOUNCEMENT, NEWS]`；**无存储凭据** → `credentials_configured=True` 恒定。
- `_get_lcu(self) -> LcuClient`：每次 fetch 时 `discover_lcu_credentials()`（psutil 扫描很轻）→ `LcuClient(port, token)`；None → `raise LcuUnavailableError("LOL 客户端未运行")`。
- `_guarded_run(run)`：模式同鸣潮适配器；捕获 `LcuError` → `FetchResult(ok=False, error=e.message)`；`except Exception` → `FetchResult(ok=False, error=f"数据处理异常: {e}")`（M1 最终审查裁定的 catch-all 兜底）。
- `fetch_account`：`_get_lcu()` → `current_summoner()` → puuid → `ranked_stats(puuid)`（ranked 失败不致命：`try/except LcuError` 后传 None，账号信息仍可用）→ `parse_summoner` → AccountInfo。
- `fetch_match`：`_get_lcu()` → summoner 拿 puuid → `match_history(puuid)` → `parse_match_history(raw, puuid)` → list[MatchSummary]。
- `fetch_announcement` / `fetch_news`：`LoLNewsClient` 按校准结论 fetch + parse（按分类过滤），payload 为 list[AnnouncementItem]。
- registry.py：Task 1 已放 LOL 注册占位，本任务后自动生效，无需再改。

- [ ] **Step 1: 写失败测试** `tests/adapters/test_lol_adapter.py`（monkeypatch `discover_lcu_credentials` 为受控值 + respx mock LCU 127.0.0.1）：

```python
import httpx
import respx

import game_assistant.adapters.league_of_legends.adapter as adapter_mod
from game_assistant.adapters.league_of_legends.adapter import LeagueOfLegendsAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability

BASE = "https://127.0.0.1:54321"
SUMMONER = {"puuid": "P1", "gameName": "峡谷小毕", "summonerLevel": 160}


async def test_client_not_running(monkeypatch):
    monkeypatch.setattr(adapter_mod, "discover_lcu_credentials", lambda: None)
    a = LeagueOfLegendsAdapter(Settings())
    assert a.credentials_configured is True  # 无存储凭据，恒 True
    r = await a.fetch(Capability.ACCOUNT)
    assert r.ok is False and "LOL 客户端未运行" in r.error


@respx.mock
async def test_fetch_account_ok(monkeypatch):
    monkeypatch.setattr(adapter_mod, "discover_lcu_credentials",
                        lambda: ("54321", "tok"))
    respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        return_value=httpx.Response(200, json=SUMMONER))
    respx.get(f"{BASE}/lol-ranked/v1/ranked-stats/P1").mock(
        return_value=httpx.Response(200, json={"queueMap": {}}))
    a = LeagueOfLegendsAdapter(Settings())
    r = await a.fetch(Capability.ACCOUNT)
    assert r.ok is True and r.payload.nickname == "峡谷小毕"


@respx.mock
async def test_fetch_match_ok(monkeypatch):
    monkeypatch.setattr(adapter_mod, "discover_lcu_credentials",
                        lambda: ("54321", "tok"))
    respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        return_value=httpx.Response(200, json=SUMMONER))
    respx.get(f"{BASE}/lol-match-history/v1/products/lol/P1/matches").mock(
        return_value=httpx.Response(200, json={"games": {"games": []}}))
    a = LeagueOfLegendsAdapter(Settings())
    r = await a.fetch(Capability.MATCH)
    assert r.ok is True and r.payload == []
```

（fetch_announcement/fetch_news 的测试在 Step 5 校准结论定形后补：mock 校准后的端点，断言 parse 输出。）

- [ ] **Step 2: 运行确认失败** → FAIL
- [ ] **Step 3: 实现 adapter.py**（结构照鸣潮 adapter.py 的 _guarded_run 模式；news 两方法按 Task 7 校准后的实际形态实现）
- [ ] **Step 4: 运行全量** → 全部通过（build_default_registry 现在会注册两个游戏）
- [ ] **Step 5: 提交** — `git add src/game_assistant/adapters/league_of_legends tests/adapters/test_lol_adapter.py && git commit -m "feat: league of legends adapter with LCU and news capabilities"`

---

### Task 9: 前端 MatchList 组件 + AccountCard 段位

**Files:**
- Create: `frontend/src/components/MatchList.vue`
- Modify: `frontend/src/components/GameCard.vue`（能力映射加 `match → MatchList`）、`frontend/src/components/AccountCard.vue`（渲染 `extra.ranked_solo`）

**Interfaces:**
- Consumes: snapshot payload = `list[MatchSummary.model_dump()]`（match_id/queue_id/mode/start_at/duration_seconds/win/champion_id/kills/deaths/assists）
- `MatchList.vue`：props `{ snap }`；payload null → "暂无数据"；每行：`mode`（ARAM/CLASSIC 等原文显示）、日期（start_at 本地化，仅月-日）、时长（duration_seconds → "xx分钟"）、胜负徽标（win===true 绿"胜"/win===false 红"负"/null 灰"-"）、KDA（kills/deaths/assists 为 null 时整行 KDA 显示 "-"）
- `AccountCard.vue`：`extra.ranked_solo` 非空时显示 `{tier} {division} · {league_points}LP`（tier 是英文段位缩写原文，M3 可加中文映射）；null/缺失不显示该行
- 英雄图标不做（需 champion_id→别名映射，M3 评估）

- [ ] **Step 1: 实现组件**（行为规格如上；样式沿用既有 .item-list/.item 体系）
- [ ] **Step 2: 构建验证** — Run: `cd frontend && npm run build` → 成功
- [ ] **Step 3: 手动冒烟** — 启动后端+前端，PC 板块出现"英雄联盟"卡片，四能力区可见；LOL 客户端未运行时 refresh 后错误条显示"LOL 客户端未运行"，公告/资讯若校准成功应有真实数据
- [ ] **Step 4: 提交** — `git add frontend/src && git commit -m "feat: match list card and ranked display in dashboard"`

---

### Task 10: E2E 联调 + README 更新

**Files:**
- Modify: `README.md`
- 验证任务，无新代码（校准遗留项在此收尾）

- [ ] **Step 1: 启动验证** — 后端 8010 + 前端 dev；`GET /api/games` 返回两个游戏（league_of_legends: section=pc、4 能力、credentials_configured=true；wuthering_waves 照旧）
- [ ] **Step 2: 真实数据验证（按可用性分层）**
  - 公告/资讯（无需凭据）：POST refresh → announcement/news 的 results.ok 视校准结论——校准成功应 ok=true 且快照有真实数据；校准失败（未锁定端点）则 ok=false + 校准记录在案
  - 账号/战绩（需 LOL 客户端运行）：先检测 `psutil` 能否发现 LeagueClientUx（`python -c "from game_assistant.adapters.league_of_legends.lcu_discovery import discover_lcu_credentials; print(discover_lcu_credentials())"`）——运行中：refresh 后核对账号/战绩真实数据、ranked_stats 字段名校准（endpoints.py 注释更新"已验证"）；未运行：标注"待客户端运行后人工验证"，README 记录步骤
- [ ] **Step 3: README 更新** — LoL 小节：LCU 原理（客户端运行时采集、无凭据管理、lockfile/进程发现说明）、公告/资讯来源与校准结论、已知限制（ranked 端点未验证则如实标注；JSON 新闻端点状态；掌盟 Cookie 渠道为未来备选）
- [ ] **Step 4: 全量回归** — `.venv/Scripts/python.exe -m pytest -q` 全过 + `npm run build` 成功
- [ ] **Step 5: 提交** — `git add README.md && git commit -m "docs: M2 LoL adapter setup, LCU notes and calibration results"`

---

## 后续计划（不在本计划内）

- **M3 计划**：提醒规则引擎（体力满去重/阈值、活动临期 N 天、凭据失效提醒）、活动日历视图、掌盟 Cookie 渠道评估（战绩查询任意玩家等 LCU 覆盖不到的场景）、英雄图标映射。
- **M4 计划**：签到（鸣潮）、资讯聚合完善、第二轮游戏评估。
