# 游戏管家工作台重设计 Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for the independent calendar implementation and final review. Continue local shell/data integration in the same session.

**Goal:** C配色+A布局的真实数据工作台，独立横向活动日历。
**Architecture:** Vue3保持现有API。App负责hash导航与统一快照状态，CalendarPage只接收games和snapshots；GameCard保留游戏详情能力组件。
**Tech Stack:** Vue3 / Vite / 原生CSS / node:test。
**Spec:** ../specs/2026-09-14-dashboard-redesign.md

## Global Constraints

- 不改后端或账号协议，不发送短信，不输出凭据。
- 所有展示来自快照，未知值不变为0；日期统一北京时间。
- 只有手动刷新触发原有refresh API，定时轮询仅读取本地快照。
- 全局配色变量：--bg #101620，--card-bg #19232e，--text #f3f0e9，--text-muted #a2b0bf，--border #34404e，--accent #d8bb84。

## Task 1: 日历时间轴（独立实现）

Files: frontend/src/calendar.js, calendar.test.js, components/CalendarPage.vue.
Consumes: props.games Array<{game_id,display_name,capabilities}>, props.snapshots Record<game_id,Record<capability,{payload,fetched_at,stale}>>, optional props.loading Boolean.
Produces: CalendarPage default Vue component; 可独立展示并筛选现有events。不发网络请求，不修改App或全局CSS。

- [x] 先编写node:test行为用例：北京时间跨日、已结束一小时、区间裁剪、单侧未知时间、非法区间、筛选无事件。
- [x] 运行 `node --test src/calendar.test.js` 确认缺失实现失败。
- [x] 实现日期运算与页面，按真实起止分组定位；14天/月范围、前后翻页、今天、游戏筛选和详情。
- [x] 用相同命令验证，再自查组件可访问标签与窄屏滚动。

## Task 2: 工作台数据与布局（主执行者）

Files: frontend/src/dashboard.js, dashboard.test.js, App.vue, style.css, components/OverviewPage.vue, components/AppIcon.vue, components/GameCard.vue, api.js, package.json.
Produces: createDashboard(api) 的 state/load/loadSnapshots/refresh/invalidateGame；App将 state.games 与 state.snapshots传给CalendarPage与OverviewPage。

- [x] 测试旧快照在读取失败后保留，以及 invalidateGame 后旧在途响应不得重新出现；测试摘要未知值。
- [x] `node --test src/dashboard.test.js` 验证失败。
- [x] 实现集中快照状态、hash导航、总览、全宽游戏详情、独立社区账号页面、深蓝金色主题。
- [x] 连接news到公告列表，保留NTE独立卡片、登录事件与真实数据契约。
- [x] 测试新逻辑及原前端29项测试；不为纯样式编写镜像测试。

## Task 3: 整体验收与审查

- [x] `npm test`、`npm run build`、`.venv/Scripts/python.exe -m pytest -q`。
- [x] 浏览器核对真实快照的总览、3个游戏详情、日历过滤与时间条、账号状态；不得用自动化发送短信。
- [x] 在桌面/窄屏检查布局、键盘导航和错误提示；修复实际发现。
- [x] 独立审查UI/data竞态/时间边界/回归，处理明确问题。
- [x] 更新README与本计划勾选状态，记录通过结果和未验证范围。

## Pre-flight

Task1与Task2仅通过CalendarPage props连接，字段名固定如上；不共享编辑文件。Task3只在两者完成后执行。原GameCard仍可独立加载快照，App可传递统一快照以避免重复读取。用户对色彩、布局及独立日历的要求均已覆盖。


## 完成记录（2026-09-14）

- Task 1 完成：独立日历、真实区间几何、缺失日期、整月/14天与筛选，10项日历测试通过。
- Task 2 完成：侧栏工作台、真实数据首页、原生游戏能力分区、账号页、LoL资讯展示、统一深蓝金色主题。
- Task 3 完成：前端52项、后端416项测试通过，生产构建通过，git diff --check通过（仓库换行策略提示不影响结果）。
- 浏览器验证：桌面总览/独立日历；真实活动筛选、翻页、未知开始日期详情；鸣潮46角色、异环17角色及3卡池、LoL20场近期对局；登录表单展开收起；390px手机导航焦点/inert/同页关闭与时间轴滚动。无控制台错误/警告。
- 审查与修复：账号刷新结束阶段epoch竞态、移动导航隐藏可聚焦、日历失败状态、非法开始时间摘要一致性均处理。复审无剩余高/中问题，两个轻微建议也已修正。
- 限制：本轮没有发送真实短信、重新登录或触发账号退出；沿用已登录状态与服务已有快照。后端仍有原有两条测试依赖弃用警告。events未提供横幅素材，当前用游戏色与纹理绘制活动条。
