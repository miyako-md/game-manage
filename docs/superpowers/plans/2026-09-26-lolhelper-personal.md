# LOLhelper 个人战绩复用实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 LOLhelper 的个人评分和分析能力接入英雄联盟模块，保留已有 UI 工作。
**Architecture:** 现有 LCU 适配器采集，本地 SQLite 按账号归档，纯函数统计，新 Vue 面板读取分析 API。与 LOLhelper 云端独立，不复制账号、令牌或私人对局。
**Tech Stack:** Python / FastAPI / SQLite / Vue 3。
**Spec:** 本文件；用户已选择个人战绩、评分、趋势和海克斯分析。

## Global Constraints

- 源码参考 `miyako-md/LOLhelper` main `c2dc013368086c318f35bbd1db32891f171e0f3a`。
- 不把 20 场采集窗口称为完整历史。客户端关闭后仍可读取本机已归档资料。
- 胜负以客观队伍结果为准，未知不算失败。无本人参与的记录不得计入。
- 评分使用 LOLhelper v3，但仅在五名队友必需指标完整时计算；其他模式标为参考评分，不称官方评分/MVP。
- 海克斯统计仅 queue 2400；本地样本胜率不代表外部强度或因果。没有同版本英雄强化数据不生成胡烂评级。
- LCU 令牌只在内存，任何公网请求保留 TLS 校验，不启用云端推送。

## Review Focus

- 零值与缺字段、队伍胜负冲突、玩家未在场。
- 多账号、重复采集、详情失败不得覆盖已有完整数据。
- 日期按北京时间展示、筛选切换不能被迟到响应覆盖。
- 客户端离线和空档案显示明确状态；错误不泄露令牌。
- 仅本地 API 可写，复用现有 Host/Origin/X-Game-Assistant 保护。

## Interfaces

`analyze_matches(records, own_puuid, catalog=None, *, days=90, queue_id=None, now=None)` 接收 LCU game 字典列表，输出 JSON 字典：

- `schema_version: 1`
- `overview`: games, wins, losses, unknown_results, winrate (0–100/null), average_score, avg_kills, avg_deaths, avg_assists, play_minutes, current_streak ({kind:'win'|'loss'|'unknown',count})
- `trend`: [{date:'YYYY-MM-DD', games, wins, winrate, average_score}]
- `heatmap`: [{date, games, wins}]
- `champions`: [{champion_id, name, games, wins, winrate, average_score}]
- `matches`: [{match_id,queue_id,mode,start_at,duration_seconds,win,champion_id,champion_name,kills,deaths,assists,damage,score,kp,damage_share,augments:[{id,name}],highlights:[string]}]，最新在前
- `highlights`: [{match_id,label,start_at,champion_name,value}]
- `hextech`: {games,recorded_games,augments:[{id,name,games,wins,winrate}],combinations:[{ids,names,games,wins,winrate}],rating_status:'unavailable',rating_note}
- `coverage`: {archived_games,filtered_games,detail_games,score_games,first_at,last_at,scope_note}

GET `/api/lol/analysis?days=90&queue_id=2400`，days 允许 7/30/90/365/0（全部），queue_id 省略表示全部。返回上述字段并增加 `account:{nickname,level}` 或 null、`collected_at`、`source:'local_lcu_archive'`。

POST `/api/lol/collect`（X-Game-Assistant:1）显式采集当前客户端最近窗口及详情。返回 `{games,details,failed_details,collected_at}`；客户端未运行返回 503 和安全提示。

GET `/api/lol/matches/{match_id}` 返回 `{payload: MatchDetail}`，读取当前归档账号的对局，无此局为 404。旧实时对局详情接口继续保留。

## Tasks

- [x] 统计引擎：新增 `adapters/league_of_legends/analysis.py` 与专用测试，核对上游评分常量和语义；输出以上契约。
- [x] 本地归档：新增 `lol_archive.py`、`lol_routes.py` 与专用测试；绑定适配器与 API；采集去重、账号隔离、完整度保护。
- [x] 可视化：新增 `LolDashboard.vue`、`lol-api.js` 与交互测试，接入 GameCard；趋势、热力图、英雄和海克斯统计可筛选，详情可查看。
- [x] 集成验收：后端 766 passed / 4 skipped；前端 189 passed，构建通过，服务重启。浏览器验收独立示例库中的趋势、筛选、海克斯及详情；生产离线采集提示正确。客户端未运行，真实在线采集未验证。
- [x] 文档：`docs/lol-personal-analysis.md` 记录复用来源、差异、覆盖边界。

## 完成记录与判断

- Ruling: 在当前工作目录窄范围集成，不切分或提交现有大量 UI 改动；用户要求在现有模块直接复用，优先保留这些工作。
- 上游 v3 评分以 100 组合成队伍与原函数逐一核对，展示分一致。
- 独立审查发现的部分快照覆盖、详情未知值、账号切换刷新、账号轮询误更新采集时间已修复；追加修复已有完整指标但后续强化数据被跳过的问题，并补回归测试。
- 账号的 `seen_at` 与战绩的 `collected_at` 分开，采集时间不因单独账号刷新而前移。
- 上游强化名称随源码提供的是占位条目，因此未复制。外部版本强度评级与 SGP 回补明确不在本次接入范围。
- 未提交或推送仓库；本机服务已加载本次功能。演示数据使用独立的 8012 端口及测试数据库，未写入正式档案。
