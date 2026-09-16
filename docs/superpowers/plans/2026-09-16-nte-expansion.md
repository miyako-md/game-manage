# NTE Expansion Implementation Plan

**Goal:** 交付资产详情、官方配队、角色工具、本地逐抽账本，并明确完整历史和保底的数据边界。
**Architecture:** 独立资产解析与快照能力；独立角色工具组件；独立 SQLite 抽卡账本和本地 API；GameCard 统一集成。
**Tech Stack:** Python/FastAPI/Pydantic/SQLite/pytest；Vue3/Vite/node:test。
**Spec:** ../specs/2026-09-16-nte-expansion-design.md

## Global Constraints
- 不覆盖既有实现，不修改真实账号凭据，不执行签到或抽卡游戏操作。
- 保留当前 UI 风格；本地收藏按角色隔离，缺值不伪造零。
- 抽卡真实记录未提供或接口未核实时，不声称已取得完整历史；保底规则必须有来源。
- 并行任务只修改分配文件，公共集成点由主任务处理。

## Task 1：资产与推荐
- [x] 在 assets.py 定义 parse_realestate / parse_vehicles / parse_teams 和版本化公开模型；测试拥有/未拥有、家具与载具属性、空集合、坏结构和危险 URL。
- [x] 新建 NteAssetsPanel.vue，props 为 capability、snap、roles；展示可搜索的资产详情、拥有筛选与官方推荐图文。
- [x] 集成 realestate/vehicles/teams 枚举、BaseGameAdapter 方法、NteAdapter 请求、调度频率与 GameCard 分区；真实只读验证三项。

## Task 2：角色工具
- [x] 新建 nte-roles.js 与 NteRolesPanel.vue；props 为 snap、accountId。纯函数覆盖中文检索、数值缺失排序、筛选组合、账号隔离收藏和属性对齐。
- [x] 对比选择限制 4 名，页面展示 2–4 名并支持移除；保留旧角色完整展开信息。
- [x] GameCard 仅对 NTE roles 使用新组件，传入账号快照 role_id。

## Task 3：抽卡来源调查和账本
- [x] 核查 NTEUID 当前记录获取方式、官方规则、分页/签名与身份字段，写入 docs/nte-gacha.md。
- [x] 独立 nte_gacha.py 实现校验预览、SQLite 事务导入、去重与冲突拒绝、按账号查询/导出；临时数据库测试覆盖重复记录、相同时间十连顺序、池隔离、空记录与不完整窗口。
- [x] 本地路由提供预览、提交、查询、导出。写入要求本机来源及 X-Game-Assistant 标识，限制文件大小，错误不回显认证数据。
- [x] NteGachaLedger.vue 提供文件选择、预览反馈、导入确认、卡池筛选、逐抽历史和保底证据提示；现有社区统计另列保留。

## Task 4：集成和验收
- [x] 对已完成实现做独立评审并修正实质问题。
- [x] 运行 pytest、npm test、npm run build；使用项目脚本重启并核对健康状态。
- [x] 浏览器验证资产/推荐、筛选/排序/收藏/对比和抽卡导入空态/查询；真实数据不填充样例记录。
- [x] 更新来源说明、剩余接口清单和本计划完成状态。

## 验收记录与边界

2026-09-16：后端 605 passed / 4 skipped，前端 102 passed，Vite 构建成功；运行管理脚本重启成功，/api/health 返回 status=ok。

真实账号：房产 7 项（拥有 4）、载具 21 项（拥有 9）、官方配队 23 项。浏览器验证房产展开、918 Spyder 属性、官方图片、收藏持久化和双角色对比。

独立 8012 测试服务使用 qa-role 和独立 SQLite：浏览器完成预览、导入 3 条、当前垫抽 2、测试阈值 90 对应剩余 88、重复导入新增 0 / 重复 3、JSON 导出；API 重新读取导出为 3 条。测试规则仅用于独立库。正式账号账本仍为 0 条。

独立评审发现并修复了退出登录删除公共配队、切换文件保留确认、Mystery Box 计数以及累计大账本不可恢复导出的问题；最后一项加入自适应分段导出和回归测试。

研究任务已完成，未找到并验证国服全历史 HTTP 接口。实际国服历史导入、导出工具国服兼容性、完整池继承/UP 规则仍待真实来源；不能据此把自动全历史同步或官方 UP 保底标为完成。分段归档可恢复流水，但连续性证据需原始导出重新补足。
