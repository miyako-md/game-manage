# 个人游戏资讯助手

个人使用的游戏信息聚合工具：定时轮询关注的游戏，把账号、体力、活动、公告等信息汇聚到一处，
并在关键事件（体力已满等）发生时通过微信推送提醒。

需求与设计细节见 [docs/需求文档.md](docs/需求文档.md)。

当前进度（M2）：已接入 **鸣潮（官服）** 与 **英雄联盟（国服）**；
鸣潮支持账号 / 体力 / 活动 / 公告，英雄联盟支持账号 / 战绩 / 公告 / 资讯；
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
日志中 APScheduler 会按各游戏的注册能力逐项注册轮询 job
（鸣潮 4 个：account / stamina / activity / announcement；英雄联盟 4 个：account / match / announcement / news）。

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
| `activity_seconds` | `3600` | 活动轮询间隔（秒），1 小时；英雄联盟 account/match 轮询复用该间隔 |
| `announcement_seconds` | `3600` | 公告轮询间隔（秒），1 小时 |
| `news_seconds` | `14400` | 资讯轮询间隔（秒），4 小时 |
| `notify_provider` | `"serverchan"` | 微信推送渠道：`serverchan` 或 `pushplus` |
| `notify_send_key` | `""` | 推送密钥，留空 = 功能可用但未启用 |
| `notify_stamina_full` | `true` | 体力已满时推送微信提醒 |
| `stamina_threshold_percent` | `90` | 体力达到该百分比即视为已满 |
| `activity_remind_days` | `3` | 活动结束前 N 天开始临期提醒 |
| `fail_notify_threshold` | `3` | 轮询连续失败 N 次后推送告警 |
| `wuwa_enabled` | `true` | 是否启用鸣潮适配器 |
| `wuwa_token` | `""` | 库街区 token，抓取方式见下文 |
| `wuwa_user_id` | `""` | 库街区数字 userId |
| `lol_enabled` | `true` | 英雄联盟适配器开关 |

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

## 英雄联盟（国服）

支持账号、战绩、公告、资讯四项能力，**无需配置任何凭据**：
账号/战绩通过 LCU（客户端自带本地 API）在客户端运行时采集；公告/资讯来自官网内容接口，始终可用。

### LCU 采集原理

- **仅客户端运行时可用**：LCU 是 LOL 客户端进程内启用的本地 HTTPS 服务，
  端口与 token 每次客户端启动都会变。适配器在每次拉取前实时发现凭据，
  **不存储任何凭据**（无需任何配置，页面不会出现"未配置凭据"提示）。
- **双路径发现**（[lcu_discovery.py](src/game_assistant/adapters/league_of_legends/lcu_discovery.py)）：
  主路径用 psutil 扫描 `LeagueClientUx` 进程命令行，提取
  `--app-port` / `--remoting-auth-token`；备路径解析标准 Riot lockfile。
  **国服 WeGame 的 lockfile 常为 0 字节，故进程扫描是实际主路径**。
- 客户端未运行时，账号/战绩手动刷新返回"LOL 客户端未运行"，属预期，不是故障。

### 公告 / 资讯来源

数据来自腾讯 CMC 内容接口（lol.qq.com 新闻页的真实数据源，2026-09-13 在线校准通过）：

```
https://apps.game.qq.com/cmc/zmMcnTargetContentList?page={page}&num={num}&target={target}&source=web_pc
```

同一端点以 `target` 参数区分分类：**`24`=公告、`23`=综合（资讯）**（另有 25 赛事 / 27 攻略 / 28 社区，暂未接入）。
该项能力不依赖 LOL 客户端，端到端已验证能拉到真实公告/资讯（如"26.18版本更新公告"）。

### 账号 / 战绩人工验证步骤

LCU 采集依赖客户端运行，自动化测试只覆盖凭据发现与解析逻辑，首次接入请人工验证一次：

1. 启动 LOL 客户端（通过 **WeGame** 启动并进入大厅）；
2. 打开页面（`cd frontend && npm run dev` → http://localhost:5173），
   在英雄联盟卡片点击手动刷新（或等待轮询）；
3. 预期：**账号卡显示召唤师昵称 / 等级 / 段位；战绩列表出现最近对局**。
   若段位字段缺失，见下文已知限制（ranked_stats 端点未验证）。

### 已知限制

- **客户端未运行时账号/战绩不可用**：刷新返回"LOL 客户端未运行"；
  快照接口会保留上次成功的数据，首次运行成功前账号/战绩为空属正常。
- **ranked_stats 端点未验证**：`/lol-ranked/v1/ranked-stats/{puuid}` 尚未经真实客户端校准
  （见 [endpoints.py](src/game_assistant/adapters/league_of_legends/endpoints.py) 标注）。
  首次真实运行时请留意段位字段；若缺失/异常，按该文件头校准注释核对真实响应并修正解析
  （排位失败不影响账号卡其余信息）。
- 计划期候选接口 news_list.json 已实测 404 废弃，现行数据源为 CMC 聚合端点
  （见 endpoints.py 校准注释）。
- **掌盟 Cookie 渠道**为未来备选（计划 M3 评估），用于战绩查询任意玩家等 LCU 覆盖不到的场景。

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

当前为"满即推"简化规则：体力已满的每个轮询周期都会推送，暂无去重；阈值/临期规则在 M3 扩展。

## 已知限制

- **非官方接口**：鸣潮数据来自库街区社区接口（非官方公开 API），路径/参数可能随上游变动。
  若某能力报"接口错误"，按
  [src/game_assistant/adapters/wuthering_waves/endpoints.py](src/game_assistant/adapters/wuthering_waves/endpoints.py)
  文件头注释的校准流程核对并修复（只需改该文件）。
- **端口 8000 不可用**：Windows 系统服务 HTTP.sys（PID 4）永久占用 8000 端口，
  本项目默认端口统一为 **8010**，请勿改回 8000。
- 轮询采用定时拉取模拟准实时，不承诺 100% 实时。
