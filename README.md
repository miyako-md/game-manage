# 个人游戏资讯助手

个人使用的游戏信息聚合工具：定时轮询关注的游戏，把账号、体力、活动、公告等信息汇聚到一处，
并在关键事件（体力已满等）发生时通过微信推送提醒。

需求与设计细节见 [docs/需求文档.md](docs/需求文档.md)。

当前进度（M1）：已接入 **鸣潮（官服）**，支持账号 / 体力 / 活动 / 公告四项能力；
后端为 FastAPI + APScheduler + SQLite，前端为 Vue 3 + Vite。

## 项目结构

```
src/game_assistant/    后端（API、调度器、存储、通知、游戏适配器）
frontend/              前端（Vue 3 SPA）
docs/                  需求文档与开发计划
config.example.toml    配置模板（复制为 config.toml 后填写）
tests/                 后端测试（pytest）
```

## 快速启动

### 1. 后端

```bash
# 首次运行：创建虚拟环境并安装依赖
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .[dev]   # Linux/macOS 用 .venv/bin/python

# 启动（默认读取 config.toml，缺省端口 8010）
.venv/Scripts/python.exe -m uvicorn game_assistant.main:app --host 127.0.0.1 --port 8010
```

启动后 `http://127.0.0.1:8010/api/games` 应返回已注册的游戏列表；
日志中 APScheduler 会注册 4 个轮询 job（account / stamina / activity / announcement）。

### 2. 前端（开发模式）

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173，/api 已代理到 127.0.0.1:8010
```

### 3. 前端生产构建

```bash
cd frontend && npm run build   # 产物输出到 frontend/dist
```

> 注意：当前 `src/game_assistant/main.py` 尚未挂载静态文件托管。
> 生产部署时可在 FastAPI 应用上挂载 `frontend/dist`，例如：
>
> ```python
> from fastapi.staticfiles import StaticFiles
>
> app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="spa")
> ```
>
> （mount 需放在 API 路由注册之后、且位于 `/api` 之外，避免覆盖接口。）

## 配置说明（config.toml）

复制 `config.example.toml` 为 `config.toml` 后按需填写；`config.toml` 已被 gitignore，不会入库。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `app_host` | `"127.0.0.1"` | 后端监听地址 |
| `app_port` | `8010` | 后端监听端口（8000 被 Windows HTTP.sys 系统服务占用，故默认 8010） |
| `db_path` | `"data/assistant.db"` | SQLite 快照库路径 |
| `stamina_seconds` | `300` | 体力轮询间隔（秒），5 分钟 |
| `activity_seconds` | `3600` | 活动轮询间隔（秒），1 小时 |
| `announcement_seconds` | `3600` | 公告轮询间隔（秒），1 小时 |
| `news_seconds` | `14400` | 资讯轮询间隔（秒），4 小时 |
| `notify_provider` | `"serverchan"` | 微信推送渠道：`serverchan` 或 `pushplus` |
| `notify_send_key` | `""` | 推送密钥，留空 = 功能可用但未启用 |
| `wuwa_enabled` | `true` | 是否启用鸣潮适配器 |
| `wuwa_token` | `""` | 库街区 token，抓取方式见下文 |
| `wuwa_user_id` | `""` | 库街区数字 userId |

## 鸣潮凭据配置（token 抓取）

未配置凭据时，卡片能力区块显示"未配置凭据"，手动刷新返回错误，属正常现象。
抓取步骤：

1. 浏览器打开 [kurobbs.com](https://www.kurobbs.com) 并登录库街区账号；
2. 按 `F12` 打开开发者工具，切到 **Network（网络）** 面板；
3. 刷新页面，任选一个发往 `api.kurobbs.com` 的请求，在请求头中复制 `token` 的值，
   以及数字 `userId`（部分请求体/响应中可看到）；
4. 填入 `config.toml`：

   ```toml
   wuwa_token = "<复制的 token>"
   wuwa_user_id = "<数字 userId>"
   ```

5. 重启后端，在页面点击刷新（或等待轮询），账号/体力/活动/公告应显示真实数据。

## 微信推送启用

1. 注册 [Server酱](https://sct.ftqq.com/)（或 [PushPlus](https://www.pushplus.plus/)），
   获取 SendKey；
2. 填入 `config.toml`：

   ```toml
   notify_provider = "serverchan"   # 或 "pushplus"
   notify_send_key = "<你的 SendKey>"
   ```

3. 重启后端即生效。体力已满时后端会主动推送提醒。

未配置时页面顶部显示"**微信推送未配置（功能已就绪）**"，属预期状态。

## 已知限制

- **非官方接口**：鸣潮数据来自库街区社区接口（非官方公开 API），路径/参数可能随上游变动。
  若某能力报"接口错误"，按
  [src/game_assistant/adapters/wuthering_waves/endpoints.py](src/game_assistant/adapters/wuthering_waves/endpoints.py)
  文件头注释的校准流程核对并修复（只需改该文件）。
- **端口 8000 不可用**：Windows 系统服务 HTTP.sys（PID 4）永久占用 8000 端口，
  本项目默认端口统一为 **8010**，请勿改回 8000。
- 轮询采用定时拉取模拟准实时，不承诺 100% 实时。
