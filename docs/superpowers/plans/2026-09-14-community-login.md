# Community Login Implementation Plan

**Goal:** 在本地仪表盘交付鸣潮与异环免抓包登录。
**Architecture:** 登录提供者处理上游协议；会话服务管理限流、加密保存与适配器热更新；Vue 登录面板仅处理用户交互。
**Tech Stack:** Python/FastAPI/httpx/pytest、Vue/Vite、pycryptodome（老虎短信协议 AES）。
**Spec:** ../specs/2026-09-14-community-login-design.md

## Global Constraints

- 用户已批准直接实施；当前干净目录切换功能分支，保持交付位于用户指定的 C:\Zcode\game-manage。
- 不打印凭据，不发送真实短信，不引入验证码代答服务。
- 执行 TDD；使用独立子任务实施提供者和前端，主任务完成会话、存储和适配器集成并审查。

## Task 1: 登录提供者
- [x] 新增 auth/providers.py 与 tests/test_auth_providers.py。
- [x] 先编写 respx 协议测试并运行确认缺少模块失败。
- [x] 实现 start_context/send_sms/login/renew 四方法，返回标准凭据字典。
- [x] 验证鸣潮 requestToken、老虎签名及 AES、塔吉多令牌交换和刷新、错误脱敏。

## Task 2: 登录服务与持久化
- [x] 新增 auth/store.py、auth/service.py、auth/routes.py 及针对性测试。
- [x] 先验证会话失效/手机号绑定/限流/保存失败保留旧凭据/退出/重启测试为红。
- [x] 实现受保护写接口、DPAPI 存储和适配器热更新。
- [x] 接入现有适配器令牌续期与单次重试，账号变化清理私人快照。

## Task 3: 登录页面
- [x] 新增 LoginPanel.vue、auth-api.js；App.vue 接入账户管理与登录完成刷新。
- [x] 表单支持手机号、人工极验、短信冷却、错误和过期提示；无 token 回显。
- [x] npm run build 与浏览器功能交互检查。

## Task 4: 集成验收
- [x] 全量 pytest、前端构建、独立代码审查和修复。
- [x] 更新 README、配置示例与上游参考来源记录。
- [x] 明确报告 PASS/BLOCKED，真实登录等待页面操作验收。

## 验收记录（2026-09-14）

- 后端全量：331 passed；原有测试依赖弃用警告 2 条。
- 前端请求/组件生命周期：14 passed；生产构建通过。
- 独立最终审查：通过，认证相关测试独立重跑 58 passed。
- 浏览器隔离环境：模拟异环短信、登录、页面刷新保留状态、退出通过；鸣潮真实极验组件可加载，人工验证前禁止发送短信；无控制台错误。
- 真实服务：8010 健康接口与 5173 页面/登录状态代理均验证正常，使用原 TOML 兼容配置。
- BLOCKED（需用户页面操作）：真实短信验证码登录、极验完成、登录后的真实账号数据获取。本次未发送真实短信。
- 代码位于 feat/community-login 分支；不推送远端。
