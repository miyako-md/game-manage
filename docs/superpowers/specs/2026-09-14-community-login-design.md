# 社区免抓包登录

用户于 2026-09-14 确认实施上一轮讨论的方案。本模块使用现有 FastAPI + Vue，在电脑仪表盘完成手机号、人工验证、短信验证码登录。二维码是可选入口，本轮优先交付电脑登录；无需手机抓包。

## 范围与数据流

- 鸣潮：用户完成极验 → 发送短信 → sdkLogin → 绑定角色 → requestToken 获取 b-at。生成并保存设备标识，自动换取失效的 b-at。
- 异环：老虎短信登录 → 塔吉多用户中心 → access/refresh token → 绑定异环角色。自动续期 access token 并保存轮换后的 refresh token。
- 当前保持单账号、首个已绑定角色；不扩展异环展示解析器、签到或任意玩家查询。
- 凭据存于独立本地文件，Windows 使用当前用户 DPAPI 加密；旧 TOML 配置在没有保存登录或退出标记时继续兼容。退出仅清除本工具授权，不调用社区注销接口；禁止重新激活旧配置。
- 登录会话有效期 10 分钟，最多 5 次验证码提交；短信按游戏/手机号和全局限流。会话绑定手机号及设备，上游失败不能覆盖旧凭据。所有登录写接口校验来源与自定义请求头。
- 页面不返回任何 token、完整手机号或短信验证码；异常不透传上游响应内容。登录模块不记录请求体。
- 登录成功立即更新适配器；重启后加载本地凭据。保留既有快照策略，账号变更时清除该游戏的旧账号相关快照。

## API 契约

写接口请求头 `X-Game-Assistant: 1`；JSON 错误 `{detail: 中文说明}`。

- `GET /api/auth/status` → `{accounts: {wuthering_waves: {configured, source, state, nickname, message}, nte: {...}}}`。
- `POST /api/auth/{game}/sessions` → `{session_id, expires_in: 600, captcha_id: string|null}`。
- `POST /api/auth/{game}/sms` body `{session_id,mobile,captcha?:object}` → `{ok:true,retry_after:60}`。
- `POST /api/auth/{game}/login` body `{session_id,mobile,code}` → `{ok:true,account: {...}}`。
- `DELETE /api/auth/{game}` → `{ok:true,account:{...}}`。

## 验收

模拟网络测试涵盖成功、验证码错误、异常响应、限流、会话过期、凭据持久化与重启、续期竞争、退出和旧配置兼容；前端构建及浏览器交互验证。真实短信、极验和账号数据联调需用户在页面操作，未执行不得报告在线登录通过。
