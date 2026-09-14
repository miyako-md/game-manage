# 可靠性与本地常驻 Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for independent backend and runtime tasks and read-only final review; root owns API/frontend integration.

**Goal:** 提醒准确、来源状态可追踪、单端口本机常驻易管理。
**Architecture:** 既有适配器添加结构化失败类型，SQLite独立状态表；API补充状态并调用静态托管模块。前端沿用当前工作台，展示采集状态。原生PowerShell脚本管理唯一项目进程。
**Tech Stack:** Python/FastAPI/SQLite/APScheduler、Vue3/node:test、PowerShell。
**Spec:** ../specs/2026-09-14-reliability-runtime.md

## Global Constraints

- 不修改正式凭据，不发送短信/真实通知；单端口只监听127.0.0.1。
- 保留最后成功快照；账号更换清理私人状态；未知值不变零。
- 先验证失败，再实现；不为纯样式写镜像测试。
- 分工文件互不覆盖，所有改动在当前feature分支；根代理负责最终集成提交。

## Task 1: 后端可靠性（代理）

Files: models.py, snapshots.py, scheduler.py, reminder.py, adapters/*/adapter.py, auth/service.py（仅失败分类）, tests对应文件。
Interface:
```python
# FetchResult增加可选error_kind:
# offline, unconfigured, auth_expired, source_error, invalid_data, account_changed
SnapshotStore.record_poll(game_id, capability, result, now=None) -> dict
SnapshotStore.get_poll_status(game_id, capability) -> dict | None
SnapshotStore.list_poll_status(game_id=None) -> list[dict]
# status dict fields: game_id, capability, state, last_attempt_at,
# last_success_at, consecutive_failures, error, error_kind
# state: ok/offline/unconfigured/auth_expired/error
```
- [x] 提醒时区、临期秒数、正常离线免告警测试先失败后修复。
- [x] 采集状态表、恢复与持久化、账号清理、并发串行测试并实现。
- [x] 活动缺公告/无解析结果/全部手填无效不覆盖旧快照，更新原空列表预期测试。
- [x] 小范围回归与行为复核，交付状态契约，不修改api.py/配置/前端。

## Task 2: 本机启动与静态托管（代理）

Files: scripts/*.ps1, src/game_assistant/web_ui.py, tests/test_web_ui.py, docs/local-runtime.md；如需CLI runner可新增src/game_assistant/runtime.py。不修改api.py/config.py/main.py。
Interface:
```python
install_web_ui(app, dist_dir=None) -> None
# root在API路由注册后调用；默认定位项目frontend/dist；缺目录不使API启动失败。
# /api/health增加service='game-assistant'由root实现，脚本据此验证身份。
```
- [x] 静态index/assets/API404行为测试先失败后实现。
- [x] 启停状态重启脚本，验证目标进程身份/创建时间，避免PID复用误杀。
- [x] 当前用户开机入口支持Enable/Disable/Status，安装删除均可幂等，日志与PID路径明确。
- [x] PowerShell语法检查与独立端口/临时数据验证，不停止真实8010，由root最终迁移。

## Task 3: API与前端整合（根代理）

Files: api.py, tests/test_api.py, frontend/src/dashboard.js/test.js, App.vue, GameCard.vue, OverviewPage.vue, CalendarPage.vue, SourceStatusPanel.vue/test.js, time.js/test.js,旧时间卡片/MatchList.vue及测试。
- [x] API状态返回与旧快照状态测试先失败，按Task1接口实现；health项目标识/静态托管调用。
- [x] collection状态读取、首页/日历/游戏详情展示，保留旧后端兼容默认值。
- [x] 统一北京时间显示、周期倒计时边界、对局详情请求竞态测试先失败后实现。
- [x] 更新README、现有过时说明，前后端完整回归。

## Task 4: 实机验收与提交（根代理）

- [x] 独立审查新改动，修复明确缺陷。
- [x] 先识别8010原项目进程，再用项目脚本启动/验证；保留5173开发兼容。
- [x] 浏览器查看8010正式UI与状态；不发送短信或启用未配置推送。
- [x] 测试重复启动、状态、重启；开机启动入口测试并明确最终开关。
- [x] 记录PASS/未验证项目并提交本轮改动。

## Pre-flight / decisions

Task1生产poll_status字典供Task3使用；Task2只暴露install_web_ui与健康service约定。Task1/2不改api.py，避免并发编辑。Task3调用列表接口时以注册能力为准为无记录项补never。Task4在所有代码验证通过后才接管真实服务。
Ruling: 开机启动先验证可撤销的入口，不默认永久开启；本次保持本机服务运行，提供用户一条启用命令。部署方案完成不等于必须修改系统登录习惯。


## 完成记录（2026-09-14）

- UI基线先提交为cdbedef；本轮只增加可靠性与运行能力。
- Task1完成：结构化错误、持久采集状态、同能力串行、账号版本防护、北京时间提醒及严格秒数边界、活动源失效与手填逆序保护。
- Task2完成：单端口静态托管、隐藏运行、身份验证与创建时间防PID复用、互斥启停、nonce文件优雅退出、滚动日志、自启动可撤销入口。
- Task3完成：API状态与observed_at、首页和游戏详情采集状态、日历来源错误可见、旧卡片北京时间、LoL详情过期请求隔离。
- 全量后端：设置GA_RUN_RUNTIME_TESTS=1执行，500 passed / 1 skipped / 2 warnings。跳过为Windows缺少创建符号链接权限；两个警告为既有依赖弃用。包含3项实际隔离PowerShell进程测试。
- 全量前端：67 passed；生产构建通过。
- 独立审查：RoleBox状态码/异常去敏、逆序日历保留、状态清空的乱序保护、httpx推送URL日志暴露均修复并复审通过，无剩余高/中问题。
- 实机：验证原8010进程属于本项目后切换受管runner；HTTP首页200、health服务标识正确、重复start复用进程。
- 真实刷新：鸣潮8/8、LoL5/5、异环9/9成功；已确认notify.enabled=false后执行，未发送真实微信或短信。
- 真实restart：22项状态与最后尝试时间完整保留，日志确认Application shutdown complete，重新读取status健康。
- 浏览器：8010真实页面、9项异环采集状态、日历和窄屏布局；控制台无错误/警告。5173开发服务保持兼容。
- 最终开机启动Disabled；注册/撤销实际测试通过，但没有注销Windows重登录验收。手动启用命令见docs/local-runtime.md。
- 自动审批拒绝两处旧隔离测试日志目录的可选删除，仅返回blocked by policy；对应进程已停止，目录保留在gitignored区域，未重试删除。
