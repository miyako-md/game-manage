# 社区账号登录

在仪表盘顶部的「社区账号」中选择鸣潮或异环，输入手机号并点击「开始登录」。

- 鸣潮：先手动完成人机验证，再点击「发送验证码」，输入短信验证码后「登录并保存」。
- 异环：点击「发送验证码」，输入短信验证码后「登录并保存」。
- 使用社区已经绑定游戏角色的中国大陆手机号。当前自动使用接口返回的首个有效绑定角色。
- 页面收到成功结果后才显示已连接；短信验证码只用于当次登录，不保存在磁盘。
- 登录后切换到「手游」，点击对应游戏卡片的「刷新」加载新账号数据；账号切换会清理旧的私人快照，不能将尚未刷新时的空卡片当作登录失败。
- 「退出」仅清除本工具的登录状态和该游戏的私人快照，保留公告、活动等公共快照，不注销社区账号。

## 本地凭据与旧配置

新登录保存在数据库旁的 `assistant.credentials.json`（可通过 `auth_store_path` 指定）。Windows 使用当前 Windows 用户的 DPAPI 加密。其他系统使用 AES-GCM 和同目录的 `.key` 文件，文件权限限当前用户；密文与密钥应一同备份。

不再需要填写 `wuwa_b_at`、`wuwa_did`、`wuwa_dev_code` 或塔吉多 token。没有新登录记录时仍兼容旧 `config.toml`；退出标记会阻止旧配置重新自动登录。删除整个凭据文件会恢复旧配置回退语义，因此正常退出请使用页面按钮。

鸣潮 token 和 roleBox 的 b-at 是不同凭据：短信登录取得 token 后，通过 `/aki/roleBox/requestToken` 换取 b-at；短期令牌失效时自动换取一次并重试。主登录 token 失效后需要重新短信登录。

短信登录得到 APP 端 token，后续账号与小组件请求使用 `source=ios`；旧网页版 token 配置继续使用 `source=h5`。首版已保存的短信登录凭据会自动识别为 APP 来源，无需重新接收验证码。

异环通过老虎短信登录换取塔吉多 access/refresh token。访问令牌会按本地 1 小时间隔或服务端拒绝时刷新，轮换后的令牌保存到本地。refresh token 失效后需要重新短信登录。旧配置中只有 refresh token 时也支持换取访问令牌。

登录仅解决授权；异环角色、进度、抽卡、战绩的标准化展示仍属于 Phase 2，登录成功不意味着这些页面已完成。

## 运行

首次更新后执行 `.venv/Scripts/python.exe -m pip install -e .[dev]` 安装新依赖。前后端开发启动命令见 README。登录写接口只允许配置中的来源地址及本工具专用请求头，默认支持 `localhost/127.0.0.1` 的 8010 和 5173 端口。

本轮交付电脑端短信登录，二维码不是必需步骤。不要把 `127.0.0.1` 链接拿到手机上打开；局域网或反向代理部署需同时配置精确的 `auth_allowed_origins` 与监听地址，并自行保证访问控制。

## 异常提示

- 会话 10 分钟过期；错误验证码最多提交 5 次，重新开始会使该游戏上一次会话失效。
- 短信同游戏同手机号 60 秒冷却，本进程累计最多 5 次发送尝试 / 10 分钟；网络超时可能已经发出短信，因此失败尝试也计入限流。
- 人机验证加载失败时可重新开始；程序不代答人机验证。
- 主登录态失效显示「登录已失效」；在页面重新登录即可，无需抓包。
- Windows 用户改变、密文损坏或无法保存时会明确报错，不回显 token、不静默覆盖成空配置。

## 参考协议与验证边界

根据以下公开源码实现登录协议，未引入机器人框架、模板或图像资源：

- WutheringWavesUID `1d693a2df0f940824cb34e102cec1cf3b381e70f`：[登录](https://github.com/kvcfdd/WutheringWavesUID/blob/1d693a2df0f940824cb34e102cec1cf3b381e70f/WutheringWavesUID/wutheringwaves_login/login.py)、[HTTP 与令牌](https://github.com/kvcfdd/WutheringWavesUID/blob/1d693a2df0f940824cb34e102cec1cf3b381e70f/WutheringWavesUID/utils/api/requests.py)。
- NTEUID `ba7790e13e39f9a825090853498848b51a06c3c9`：[老虎 SDK](https://github.com/tyql688/NTEUID/blob/ba7790e13e39f9a825090853498848b51a06c3c9/NTEUID/utils/sdk/laohu.py)、[塔吉多 SDK](https://github.com/tyql688/NTEUID/blob/ba7790e13e39f9a825090853498848b51a06c3c9/NTEUID/utils/sdk/tajiduo.py)。

自动化验证使用模拟 HTTP 和独立临时数据，不发送真实短信。完整在线验收需要用户在页面完成人工验证及输入真实短信验证码，然后检查账号、体力与 roleBox 数据；不得将模拟通过视为真实账号在线通过。

2026-09-14 后续联调：用户完成鸣潮短信登录后，发现旧采集客户端固定 `source=h5` 导致账号/小组件返回 code 220。使用同一已保存凭据只修改为 `source=ios`，角色列表和小组件均返回 code 200。修复并重启后，鸣潮 8 项能力全部刷新成功，页面账号、体力和周期进度恢复；无需重发短信。异环真实短信登录仍待验证。
