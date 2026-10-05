# LOL Esports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 用户已选择连续执行、只遇重要阻塞再询问；本计划整体审核后开始，完成后独立审查。

**Goal:** 在 LOL 模块提供仅使用腾讯公开资料的当前年度职业赛程赛果、战队与选手联动浏览，正确显示缺失、过期和部分更新。

**Architecture:** 腾讯客户端和纯解析层输出有稳定源 ID 的职业实体，由 LOL 专属编排层按分组保留有效缓存；复用现有公开 capability、SQLite 快照与调度。Vue 职业赛事组件独立于个人 LCU 页面状态，三个视图共享浏览上下文。所有测试与构建先在包含当前未提交补丁的隔离副本完成，部署只应用本功能差异。

**Tech Stack:** Python >=3.11、现有 FastAPI／HTTPX／Pydantic／SQLite／APScheduler >=3.10,<4、pytest／pytest-asyncio／respx；Vue 3、Node 原生 test、现有 happy-dom／Vite。不新增、安装或升级依赖，不修改锁文件。

**Spec:** [2026-10-04-lol-esports-design.md](../specs/2026-10-04-lol-esports-design.md)。用户已在手机审核设计要点并回复“可以，开始吧”，随后要求“不用确认了，直接执行”。执行方式据此确定为连续执行；按主对话当前阶段约束，本轮先交付计划供一次整体审核，尚未开始产品实现。执行者必须先读完整设计与本计划。

## Global Constraints

- 腾讯是首版唯一数据来源；不注册外部服务，不引入 API 密钥，不自动启用 LoL Esports／GRID。
- 当前北京时间年度的 LPL、全球先锋赛、MSI、全球总决赛、电竞世界杯英雄联盟项目、亚运会英雄联盟项目；不纳入其他地区联赛、德杯、全明星、次级邀请赛、娱乐赛和 TFT。
- 不做开赛提醒、任何赛事通知、活动日历写入、收藏、个性化推荐、深度选手统计、跨年历史查询或全量历史回补。
- 当前阵容不作为历史或单场出场名单；未知位置、资料、比分、赛季和对手不猜填；源 ID 保持字符串。
- 赛程默认每 15 分钟更新；目录和战队／选手资料默认每 24 小时更新；赛程 30 分钟、资料 48 小时无成功采集标记缓存过期。
- 源阵容更新时间超过 7 天额外提示可能滞后；源时间缺失显示未知，不能用本机采集时间代替。
- 手动更新至少间隔 60 秒、同一刷新最多一个在途、上游并发最多 3、单请求超时 15 秒；遵从 Retry-After，不绕过访问限制。
- GET 只读缓存；职业赛事无需 LCU 或 B 站登录；赛事更新不能调用个人战绩采集。
- 正式目录为 C:/Users/73602/Documents/Codex/2026-10-01/task/game-manage，服务 127.0.0.1:8010。实现／测试阶段不得刷新或重启正式服务。
- 必须继承现有未提交 B 站登录、四游戏统一资讯补丁，以及配置、数据、凭据；不得 reset、clean、stash 后遗漏恢复，或从 HEAD 整文件覆盖当前补丁。
- 不修改 Git 身份、不推送。当前作者身份不可用，各任务保存差异与验证记录即可，不以提交为执行前提；若后续已有合法身份且允许提交，也只能提交本功能选定差异，不能顺带提交原有修改。
- 本计划阶段只新增计划文档。部署阶段仅在本计划获批、执行方式选定、实现验证和审查完成后执行，属于届时执行范围；当前不停止服务或创建实施环境。

## Review Focus

1. 北京时间跨年时旧年度缓存不能冒充新年度；新年失败不清空旧快照（Task 3：test_rollover_does_not_relabel_old_payload）。
2. 阵容 HTTP 200 但源时间陈旧／未来／缺失，不能显示为现役资料刚更新（Task 1、5：test_roster_source_time_is_not_fetch_time）。
3. 不完整列表漏掉一场旧比赛或只坏一条记录，不能删除旧比赛／整组清空（Task 3：test_partial_match_group_preserves_missing_records）。
4. 自动轮询与两个页面手动更新交错，不重复访问，迟到响应不能覆盖新界面选择（Task 3、4、5：test_refresh_coalesces_and_cools_down、late refresh test）。
5. 账号切换触发上层组件重新挂载时，公开赛事缓存和返回筛选上下文仍保留，且采集错误不会发通知（Task 4、5：test_esports_public_and_silent、account remount test）。

---

## 文件布局与共用契约

后端新增文件均在 `src/game_assistant/adapters/league_of_legends/`，按职责命名：

- `esports_models.py`：职业实体、解析结果、快照和分组元信息；不修改个人对局模型。
- `esports_parse.py`：JSON 数据包装解码、范围选择、时间／状态／位置解析与身份关联。
- `esports_client.py`：TencentEsportsClient、固定网址与有界网络读取，不存数据。
- `esports_service.py`：LolEsportsService、分组更新、缓存合并、时效与冷却。
- 新增 `src/game_assistant/lol_esports_routes.py`：独立更新路由和只读快照响应适配。

后端定点修改：`models.py`、`adapters/base.py`、`adapters/league_of_legends/adapter.py`、`snapshots.py`、`scheduler.py`、`config.py`、`api.py`、`config.example.toml`。不改正式 `config.toml`，不新增数据库表或迁移。

前端新增：`frontend/src/lol-esports-api.js`、`frontend/src/esports.js`、`frontend/src/components/LolEsportsPanel.vue`、`EsportsSchedule.vue`、`EsportsTeams.vue`、`EsportsPlayers.vue` 及同名测试。定点修改 `LolDashboard.vue/.test.js`、`dashboard.js/.test.js`、必要的 `GameCard.vue` 集成测试。若组件重新挂载导致本地状态丢失，按 Task 5 的公共浏览状态契约处理，不重构全站路由。

测试新增：`tests/adapters/test_lol_esports_parse.py`、`test_lol_esports_client.py`、`tests/test_lol_esports_service.py`、`tests/test_lol_esports_routes.py`；公开样本置于 `tests/fixtures/lol_esports/`，附 `README.md` 记录来源、抓取日期和局限；新增 `docs/lol-esports.md` 记录使用与来源限制。

统一模型约定（本计划提出，尚无实现）：

- EsportsTournament：id、source_id、family、season_year、name、source_url；family 取 lpl/first_stand/msi/worlds/ewc/asian_games。
- EsportsMatch：id、source_id、tournament_id、team_a_id、team_b_id、team_a_name、team_b_name、start_at、status、score_a、score_b、best_of、stage、round_name、winner_team_id、source_url、live_url、vod_url；未知值为 null，status 取 scheduled/live/completed/postponed/cancelled/unknown。
- EsportsTeam：id、source_id、name、short_name、logo_url、description、kind、tournament_ids；kind 取 club/national/unknown，不推断缺失类型。
- EsportsPlayer：id、source_id、nickname、image_url；位置和队伍归属放入关系，避免转会／兼任导致全局字段相互覆盖。
- RosterMembership：team_id、player_id、scope、position、tournament_id、match_id、valid_from、valid_to；scope 取 source_current/season_registered/match_played。现有样本只有 source_current 时，其他关系保持缺失。
- GroupMeta：group_key、last_attempt_at、last_success_at、source_updated_at、attempt_state、coverage、issues；attempt_state 取 never/ok/error/cooldown，coverage 取 unknown/partial/complete/missing。
- ParseMeta：source_updated_at、coverage、issues。CatalogParse(meta, tournaments, missing_families)、MatchParse(meta, matches)、RosterParse(meta, team, players, roster_memberships) 使用上述实体类型。
- EsportsSnapshot：schema_version 固定 1、season_year、catalog（GroupMeta）、tournaments、matches、teams、players、roster_memberships、coverage（其余 group_key 到 GroupMeta 的映射）、refresh_state（ok/partial/missing）。实体集合均为列表，前端按 id 构建索引。
- 时间值在 Python 内为 aware datetime／None，JSON 为带时区 ISO 文本／null。group_key 使用 catalog、matches:<tournament_id>、roster:<team_id>；元信息放在所属分组，避免一个队更新时间覆盖整个页面。

## Task 1: 隔离基线、公开样本与纯解析模型

**Files:** Create esports_models.py、esports_parse.py、tests/adapters/test_lol_esports_parse.py、tests/fixtures/lol_esports/README.md 及最小 JSON／包装样本。此任务不改正式产品文件。

**Interfaces:** Produces `decode_public_payload(text: str) -> dict`、`parse_catalog(raw: dict, season_year: int) -> CatalogParse`、`parse_matches(raw: dict, tournament: EsportsTournament) -> MatchParse`、`parse_team(raw: dict, tournament_ids: list[str]) -> RosterParse`。无网络／数据库／当前时钟依赖。

- [ ] **Step 1: 建立并验证隔离基线。** 执行时使用 using-git-worktrees 流程建立隔离目录；当前作者缺失或工作树方案不适合时使用独立文件副本。副本必须覆盖原工作树的已跟踪文件实际内容及相关未跟踪源码／测试／文档，不能只复制 HEAD。排除 .git、config.toml、data、凭据、日志、原 dist；记录原有修改清单与 SHA256，核对 B 站和统一资讯新增文件均存在。基线测试需使用临时配置与数据库。
- [ ] **Step 2: 确认可用测试环境和真实代码位置。** 不安装依赖；使用现有 Python 解释器，以副本 src 为 PYTHONPATH、`-B` 禁止写字节码，检查 `game_assistant.__file__` 指向隔离副本。前端复制现有 node_modules 至隔离目录供测试／构建，不执行 npm ci。缺少必需依赖时停止相关执行并报告，不改原环境。记录已有基线测试失败，不能把其当作本功能成功。
- [ ] **Step 3: 保存最小公开样本并固定映射。** 正常 GET 官网已引用的目录、分赛季赛程、LPL 阵容和国际参赛队阵容；不整库下载。对照页面脚本核实状态、位置、系列赛／赛季／家族 ID。已观察家族 ID 为 LPL=5、Worlds=1、MSI=8、全球先锋赛=220、EWC=227；亚运会映射尚无实测证据，必须核实后才接入，否则该卡片保持资料暂缺，不能猜 ID。年度赛季 ID 从目录解析，不硬编码 237 等实例编号。样本剔除无关长简介、图片目录全库和非必需个人资料。
- [ ] **Step 4: 写并运行失败测试。** 测试名称固定为 test_catalog_current_year_and_scope、test_worlds_missing_and_lpl_date_conflict、test_ids_remain_strings_and_duplicates_conflict、test_unknown_status_and_zero_scores、test_team_roster_roles_and_missing_match_lineup、test_roster_source_time_is_not_fetch_time、test_js_wrapper_never_executes。断言 2025 Worlds 不能进入 2026；9 月 LPL 不因目录 6 月结束而丢失；超过 2^53 的 ID 原样；未知码不认定完赛；未开赛 0 不作为赛果；activePlayers 只产生 source_current；任意额外脚本表达式拒绝。使用参数化覆盖待定、取消、延期、位置未知、重复昵称与冲突 ID。
- [ ] **Step 5: 实现模型和纯函数，运行同组测试。** 固定时间／名称类型校验，JSON 和官网已验证的单次赋值包装用严格匹配解析；不用 eval。通过条件：所有新解析测试 PASS，样本来源元信息齐全。保存仅本任务差异和测试结果，不提交原有补丁。

命令基准（后续 Python 测试沿用；变量值在执行前解析为绝对路径，不得为空）：

```powershell
$implRoot = (Resolve-Path -LiteralPath '.').Path # Run from the isolated checkout root.
$testPython = (Resolve-Path -LiteralPath '.\.venv\Scripts\python.exe').Path # Use this checkout's environment, or explicitly select another verified interpreter.
$env:PYTHONPATH = Join-Path $implRoot 'src'
Set-Location -LiteralPath $implRoot
& $testPython -B -c "import game_assistant; print(game_assistant.__file__)"
& $testPython -B -m pytest -p no:cacheprovider tests/adapters/test_lol_esports_parse.py -q
```

隔离路径若已存在，先核实是否属于本任务；不是则使用带时间后缀的新目录并统一更新执行变量，不覆盖既有目录。测试临时数据使用 pytest tmp_path。

## Task 2: 腾讯公开客户端与访问限制

**Files:** Create esports_client.py、tests/adapters/test_lol_esports_client.py。

**Interfaces:** `TencentEsportsClient(client: httpx.AsyncClient | None = None)`；async `fetch_catalog() -> dict`、`fetch_matches(season_source_id: str) -> dict`、`fetch_team(team_source_id: str) -> dict`、`aclose() -> None`。支持 async context manager；客户端只返回通过包装和业务状态校验的字典。`EsportsSourceError(code: str, retry_after_seconds: int | None = None)` 不含响应正文或任意上游异常文本。

- [ ] **Step 1: 写并运行失败测试。** test_client_reads_only_fixed_public_routes 校验目录、分赛季和战队路径；test_client_rejects_redirect_and_bad_ids 拒绝路径注入、非数字源 ID、站外重定向；test_client_limits_and_retry_after 验证 15 秒超时、429、Retry-After 数字／HTTP 日期、异常业务码、HTML 登录页、超大响应和无凭据请求。respx 阻止所有未模拟网络访问。
- [ ] **Step 2: 实现固定来源客户端。** HTTPS 验证开启、follow_redirects=False；只访问 Task 1 核实的 lpl.qq.com 公开目录／分赛季／战队文件。总响应上限 8 MiB，以流式字节累计限制；不下载完整选手图片目录，优先使用阵容自带图片。数字 ID 作为字符串校验后才插入固定模板；允许已验证业务成功码，未知码失败。
- [ ] **Step 3: 运行客户端与解析测试。** `& $testPython -B -m pytest -p no:cacheprovider tests/adapters/test_lol_esports_client.py tests/adapters/test_lol_esports_parse.py -q`。通过条件：PASS、无真实网络逃逸、无执行来源脚本或加载凭据。记录差异与验证结果。

## Task 3: 分组编排、失效保留与时效

**Files:** Create esports_service.py、tests/test_lol_esports_service.py。

**Interfaces:** `LolEsportsService(client_factory, *, clock, monotonic_clock, settings)`；async `refresh(previous: EsportsSnapshot | None) -> FetchResult`；`source_cooldown_seconds() -> int` 返回剩余上游冷却。`merge_snapshot(previous: EsportsSnapshot | None, incoming: EsportsSnapshot) -> EsportsSnapshot` 为纯函数；`snapshot_for_display(previous: EsportsSnapshot | None, poll_status: dict | None, now: datetime) -> dict` 返回标准快照包装，含 payload／fetched_at 由调用者补齐、stale、source_status 和分组派生过期信息。客户端工厂每轮创建并关闭，service 不直接写 SQLite。

- [ ] **Step 1: 写并运行失败测试。** test_partial_match_group_preserves_missing_records 断言不完整新列表遗漏旧 ID 时保留旧项，成功项更新；test_roster_failure_keeps_old_times 断言阵容失败不改其 last_success_at／source_updated_at；test_all_fail_returns_error_and_no_replacement；test_rollover_does_not_relabel_old_payload 断言北京时间切年后旧年不展示为当年，失败仍保留旧快照；test_refresh_coalesces_and_cools_down 验证并发最多 3、Retry-After 内不再访问对应来源；test_refresh_intervals 验证 900／86400 秒；test_stale_thresholds 验证 1800／172800／604800 秒边界，未来及空源时间不提高新鲜度。
- [ ] **Step 2: 实现分组拉取与合并。** 目录选择当年目标赛事，优先分赛程，按参赛队补阵容；不因汇总列表空就判无比赛。同赛季、同分组按稳定 ID 更新，缺项和异常不能当删除；只有已证实完整覆盖可替换整组。解析结果未知覆盖保持未知。阵容内重复位置不推断首发，国家队／俱乐部关系并存。
- [ ] **Step 3: 实现到期、预算和刷新结果。** 单轮总预算 120 秒，未完成分组标为部分并保留旧值；取消时关闭客户端，不发布半构建对象。目录和阵容 86400 秒到期，赛程 900 秒；缺失分组首次补取，失败／缺项再次尝试不得绕过冷却。无分组到期时返回现有有效快照，各组采集／源时间不变，界面提示缓存仍在有效期。每轮在内存形成一致快照；部分成功返回 ok=True 和 refresh_state=partial；全部请求失败返回 ok=False，交由现有调度器保留旧快照。仅首次目录成功时允许发布缺比赛状态；切年只在新年度有效数据包发布时替换旧年展示快照。
- [ ] **Step 4: 实现只读展示转换并运行测试。** 按各组时间计算过期而非用顶层 fetched_at 粉饰阵容；叠加 poll_status 的最后失败，不修改数据库。`& $testPython -B -m pytest -p no:cacheprovider tests/test_lol_esports_service.py tests/adapters/test_lol_esports_parse.py tests/adapters/test_lol_esports_client.py -q` 必须 PASS。记录已知资料缺口而不是补造样本完整性。

## Task 4: Capability、快照、调度和 API 隔离

**Files:** Create lol_esports_routes.py、tests/test_lol_esports_routes.py；Modify models.py、adapters/base.py、league_of_legends/adapter.py、snapshots.py、scheduler.py、config.py、api.py、config.example.toml；Extend tests/test_snapshots.py、test_scheduler.py、test_collection_api.py、test_api_security.py。

**Interfaces:** 新增 `Capability.ESPORTS = 'esports'`、`BaseGameAdapter.fetch_esports() -> FetchResult` 和 LOL override；Settings 默认 `esports_seconds=900`、`esports_profiles_seconds=86400`。`install_lol_esports_routes(app) -> None` 组装 service、缓存读取回调和 poller；`read_esports_snapshot(app, now: datetime) -> dict` 调用 Task 3 的只读转换。POST `/api/lol/esports/refresh` 返回 `{ok, error_kind, snapshot}`；GET 沿用 `/api/games/league_of_legends/snapshot/esports` 标准包装。

- [ ] **Step 1: 写并运行失败测试。** test_esports_public_and_silent 断言切账号清理保留 esports，成功／失败均不调用 ReminderEngine／notifier；test_esports_get_is_cache_only 禁止网络、LCU、SQLite 写入；test_refresh_only_polls_esports 断言不调用 collect、其他能力或 B 站；test_manual_and_scheduled_share_lock；test_no_scheduler_manual_refresh_persists；test_api_reports_partial_and_year_mismatch；test_refresh_security_and_cooldown 校验 Host／Origin／X-Game-Assistant、不接收上游 URL、60 秒内 429＋Retry-After。
- [ ] **Step 2: 接入模型、适配器、公开名单和间隔。** 现有 SnapshotStore 保存单个版本化公开快照，不迁移表；service 通过只读回调取得此前快照，adapter.fetch_esports 调用 service.refresh，写入仍只有 PollingScheduler 成功路径。更新 `_PUBLIC_CAPABILITIES`，同时检索其他公共能力分类，避免遗漏客户端或账号清理逻辑。新增配置有默认值，正式配置零改动。
- [ ] **Step 3: 组装唯一 poller 和独立路由。** 正常使用 app.state.scheduler；`start_scheduler=False` 的测试／手动模式创建未 start 的 PollingScheduler 作为 app.state.lol_esports_poller，确保手动请求也记录快照和状态。赛事独立更新与整游戏刷新中的 esports 分支统一使用该实例，不走原有无 scheduler 时仅 adapter.fetch 的不落盘分支；不会启动后台任务。保留调度器同 capability 锁，手动冷却在锁前预留，避免重复排队。无注册 LOL 返回 404，更新未成功仍返回可用旧 snapshot；首次无缓存失败也明确错误。
- [ ] **Step 4: 阻断提醒并运行后端集成回归。** 调度器对 esports 在所有结果分支跳过 reminder.handle_poll，包括连续失败；不生成 events 快照。运行 `& $testPython -B -m pytest -p no:cacheprovider tests/test_lol_esports_routes.py tests/test_lol_esports_service.py tests/test_snapshots.py tests/test_scheduler.py tests/test_collection_api.py tests/test_api_security.py tests/test_lol_routes.py tests/adapters/test_lol_adapter.py -q`。全部 PASS 后保存差异，检查 api.py／scheduler.py 里原统一资讯正文保留逻辑仍在。

## Task 5: 前端三视图、返回上下文与离线访问

**Files:** Create lol-esports-api.js/.test.js、esports.js/.test.js、LolEsportsPanel.vue/.test.js、EsportsSchedule.vue/.test.js、EsportsTeams.vue/.test.js、EsportsPlayers.vue/.test.js；Modify LolDashboard.vue/.test.js、dashboard.js/.test.js，必要时 GameCard.vue 和 IntegratedGameCard.test.js。

**Interfaces:** `getLolEsports({signal}={}) -> Promise<SnapshotEnvelope>`、`refreshLolEsports({signal}={}) -> Promise<{ok,error_kind,snapshot}>`，写请求带 X-Game-Assistant:1、120 秒服务预算对应前端超时 135 秒。`createEsportsBrowseState() -> {view,family,date,teamId,playerId,returnTo}` 为纯状态工厂；`selectEsportsMatches(payload, filters) -> Array`、`esportsGroupLabel(meta, now) -> string` 为纯展示函数。LolEsportsPanel props：snap、browseState；emit：snapshot、browse-change。子视图接受对应数据与筛选，发出 select-team／select-player／select-match／back，不自行抓取外网。

- [ ] **Step 1: 写并运行 API 与状态失败测试。** get uses local cached endpoint only；refresh does not call /api/lol/collect or whole-game refresh；unknown schema is explicit error；aborted／late refresh preserves current selection；test roster source timestamp differs from fetch timestamp；日期、缺数据和列表排序测试固定时钟，不以系统当前时间写脆弱断言。
- [ ] **Step 2: 实现 API、筛选及公共浏览状态。** dashboard.js 将 esports 加入 PUBLIC_CAPS；公共浏览状态由不随个人账号 revision 销毁的上层 dashboard 状态持有，以 game_id 索引，由 GameCard／LolDashboard 传递；不存关注、账号或私人信息，不使用个人账户键。局部赛事页签、赛事／日期与返回位置在切换三视图及账号导致重挂载时恢复。前端只读 schema_version=1，缺失图片和实体有占位，不生成猜测链接。
- [ ] **Step 3: 写并运行组件失败测试。** “schedule to team to player and back preserves filter”；“account remount keeps esports view and public snapshot”；“LCU offline and empty archive do not hide esports”；“missing current season is not no matches”；“unknown score and stale roster are explicit”；“manual failure retains useful data”；键盘按钮和窄屏布局断言以可见行为为主。加载和错误只影响对应视图，个人错误不泄露到赛事页。
- [ ] **Step 4: 实现三视图并接入 LOL。** 顶部个人采集、时间／模式筛选和归档空态限定在个人分区；职业赛事独立状态和更新按钮；首次缺缓存不自动外网抓取，明确提供更新入口。用户主动刷新取得响应后更新公开 snapshot，不触发父级整游戏刷新。所有三视图使用可读的覆盖与更新时间提示，链接只经现有 safeUrl 和来源路由校验后外部打开。
- [ ] **Step 5: 运行定向前端测试。** 在隔离 frontend 中执行 `node --test src/lol-esports-api.test.js src/esports.test.js src/components/LolEsportsPanel.test.js src/components/EsportsSchedule.test.js src/components/EsportsTeams.test.js src/components/EsportsPlayers.test.js src/components/LolDashboard.test.js src/dashboard.test.js src/components/IntegratedGameCard.test.js`。通过条件全部 PASS，原资讯分类和正文详情测试仍通过；保存差异。

## Task 6: 完整回归、实源验收与独立审查

**Files:** Create docs/lol-esports.md；Update 公开样本说明与有需要的回归测试。不改变已批准范围或引入新的数据源。

**Interfaces:** 交付经过验证的隔离实现、前端 dist、逐文件部署清单和实际测试报告；部署清单包含基线 hash／候选 hash，排除配置、数据、凭据、环境、锁文件、原有其他改动。

- [ ] **Step 1: 运行完整自动检查。** 隔离根目录执行 `& $testPython -B -m pytest -p no:cacheprovider -q`；隔离 frontend 执行 `npm test`、`npm run build`。通过条件退出码均为 0；如发现原有基线失败，分开列明并判断影响，不宣称全部通过。不得为绕过失败而跳过关键测试或更改产品范围。
- [ ] **Step 2: 进行隔离端到端验收。** 使用临时 config／SQLite，无真实凭据、无通知器、关闭其他游戏与非赛事后台任务；先选取未被占用的独立本地端口，不使用 8010。窗口隐藏启动预览进程；清理时核验 PID／命令行属于本次预览后仅停止该进程。完成宽屏与窄屏、键盘、LCU 离线、三视图往返、账号重挂载、失败旧值保留和无日历／通知检查；浏览器只操作隔离预览。
- [ ] **Step 3: 只读核验腾讯真实样本。** 在隔离预览中仅主动更新赛事一次，抽样对照一场 LPL、一项可得国际赛事、一个 LPL 队和一个国际队；记录来源 URL、采集时间、源更新时间、比分／阶段／位置／ID、链接可用性。缺项照实报告；不注册服务、不带凭据、不突破 429，不因数据空而改接其他来源。降级验收通过与完整数据覆盖分开记录。
- [ ] **Step 4: 完成独立审查并处理意见。** 按用户选定方法调用独立 reviewer，审查候选差异和测试证据；重点覆盖 Review Focus 五项、公开状态隔离、部分更新与当前年度。无依据的意见先核实，必要修复后只重跑受影响检查；有重大偏离设计、资料无法支撑基本功能或破坏现有补丁的风险时暂停说明。
- [ ] **Step 5: 出具部署候选。** 检查原安装自基线以来各待覆盖文件 hash；若出现新改动，在隔离候选中合并并重新验证，不能覆盖。最终记录新功能差异、已知腾讯覆盖缺口、验证结果与回滚清单。此时才满足 Task 7 的执行前提。

## Task 7: 本地 8010 部署、健康检查和定点回滚

**Files:** 只部署 Task 6 已审查的产品文件清单与隔离构建的 frontend/dist；保留原 config.toml、data、所有凭据、环境、Git 身份与自启动设置。需要安装依赖或迁移数据库则说明已偏离本计划并暂停。

**Interfaces:** 原有 scripts/status.ps1、stop.ps1、start.ps1、restart.ps1 均已存在，参数为 `-Port 8010`；执行者先只读核实 runtime-common.ps1 的实际进程识别与目录检查。部署不使用宽泛 taskkill／目录镜像删除／Git reset。

- [ ] **Step 1: 做部署前精确备份。** 在独立备份目录保存待覆盖文件的原样内容、存在性和 SHA256，以及当前 dist 完整树与文件清单；备份必须包含这些文件上的原有未提交补丁。配置和数据保持原地不操作。只读确认 8010 对应此安装，源文件 hash 与 Task 6 基线仍一致；不一致先合并重验。
- [ ] **Step 2: 短暂停服并应用候选差异。** 使用该安装的 `scripts/stop.ps1 -Port 8010`，核对退出和端口释放；定点复制清单内文件及已构建 dist，不运行依赖安装。dist 使用新旧目录受控切换，任何移动／删除前核验绝对路径位于原 frontend 与本次备份目录；保留旧 dist。不得覆盖其他未提交文件。
- [ ] **Step 3: 启动并只读验收。** 执行 `scripts/start.ps1 -Port 8010`，随后 `scripts/status.ps1 -Port 8010`；GET /api/health、/api/games、赛事缓存接口和首页，验证新 UI 入口与原页面正常。正式服务不主动执行整游戏刷新、LCU 采集、登录或短信；让正常调度按既定策略运行，实源更新已在隔离环境验证。
- [ ] **Step 4: 出现部署失败时定点回滚。** 停止经核验的本安装进程，按备份恢复本次覆盖的代码文件和旧 dist；本次新建文件仅在其 hash 仍等于候选且路径核验通过时移走至备份目录，避免删除他人后续修改。恢复后用 start/status/health 验证。无需回滚 SQLite；新 esports 公开快照可以留存，旧版本不读取该能力，禁止用旧整库覆盖运行期间其他数据。若不能确认安全恢复，则停止覆盖并报告明确阻塞。
- [ ] **Step 5: 交付实际结果。** 汇报部署状态、测试／审查结果、来源覆盖缺口、备份位置和已验证回滚条件；说明腾讯唯一来源、缓存延迟以及阵容时效。再次核对原有 B 站／资讯补丁和配置保持，删除或清理备份不在本次范围。没有成功部署证据时不得称“已上线”。

## 计划自审与执行方式建议

- 范围与来源：Task 1、2 覆盖已批准赛项和腾讯唯一来源；亚运会未实测 ID 明确以“待来源核实／资料暂缺”处理，没有虚构映射。
- 模型与时效：Task 1、3 覆盖 ID、阵容语义、跨年、部分更新、源时间和缓存时间；所有后续类型均在共用契约定义。
- 集成与交互：Task 4、5 覆盖无 LCU、公开缓存、同一 poller、三视图和返回上下文；不复用个人 Match 或异环 TEAMS。
- 保护与交付：Task 1 保留真实工作树基线，Task 6 回归与独立审查，Task 7 差异部署及原补丁回滚；不从 HEAD 恢复，不还原整库。
- Review Focus 五项均已指向所属测试；新代码任务均含失败测试、最小实现和可判定通过命令。部署步骤以健康检查和路径／hash 核验验证，不添加镜像式测试。
- 当前所有复选框保持未完成；本轮只写计划，未建副本、未采集来源、未实现、未运行产品测试／构建、未部署。

已保留用户选择“连续执行，最终独立审查”：同一执行者按依赖完成七个任务，关键测试通过后继续，最后由独立审查者检查整体；仅遇到影响范围、来源访问、依赖、原有改动保护或部署恢复的重大阻塞时询问。此方式适合本计划紧密衔接的模型／缓存／前端接口，减少逐任务交接成本，不再要求用户重复选择执行方法。

当前将本计划交回主对话，完成其要求的一次整体计划审核后连续推进，不逐任务请求确认。本轮不调用实施技能、不写产品代码、不启动 Task 1。
