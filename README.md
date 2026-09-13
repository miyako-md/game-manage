# 个人游戏资讯助手

个人使用的游戏信息聚合工具：定时轮询关注的游戏，把账号、体力、活动、公告等信息汇聚到一处，
并在关键事件（体力已满等）发生时通过微信推送提醒。

需求与设计细节见 [docs/需求文档.md](docs/需求文档.md)。

当前进度（M3）：已接入 **鸣潮（官服）**、**英雄联盟（国服）** 与 **异环（塔吉多社区）**；
鸣潮支持账号 / 体力 / 活动日历 / 周期进度 / 公告 / 探索度 / 数据坞 / 角色练度
（探索度/数据坞/角色练度需可选的 roleBox 三件套配置），英雄联盟支持账号 / 战绩 / 公告 / 资讯，
异环支持公告 / 活动日历（公告匿名可用，活动日历以手填为主、自动扫描兜底，
见下"游戏内活动手填"）/ 角色 / 进度 / 抽卡 / 战绩（后四项需可选的塔吉多凭据）；
新增提醒引擎（体力 / 活动日历临期 / 拉取失败告警，微信推送带去重）；
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
（鸣潮 8 个：account / stamina / events / progress / announcement / exploration / calabash / roles；英雄联盟 4 个：account / match / announcement / news；异环 6 个：announcement / events / roles / progress / gacha / record）。

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
| `stamina_threshold_percent` | `90` | 体力达到该百分比且未满时提醒即将回满 |
| `activity_remind_days` | `3` | 活动结束前 N 天开始临期提醒 |
| `fail_notify_threshold` | `3` | 轮询连续失败 N 次后推送告警 |
| `wuwa_enabled` | `true` | 是否启用鸣潮适配器 |
| `wuwa_token` | `""` | 库街区 token，抓取方式见下文 |
| `wuwa_user_id` | `""` | 库街区数字 userId |
| `wuwa_app_token` | `""` | 库街区 APP 端 token（预留字段，当前功能未消费，保留） |
| `wuwa_b_at` | `""` | roleBox 会话票据（探索度/数据坞/角色练度），与 `wuwa_dev_code`/`wuwa_did` 三项全部填写才启用，见下文"APP 端 roleBox 抓包教程" |
| `wuwa_dev_code` | `""` | roleBox `devCode` 请求头整串（格式 = "客户端公网IP, 空格+完整UA"） |
| `wuwa_did` | `""` | roleBox `did` 请求头（设备 UUID） |
| `lol_enabled` | `true` | 英雄联盟适配器开关 |
| `nte_enabled` | `true` | 异环适配器开关 |
| `nte_access_token` | `""` | 塔吉多社区访问令牌（JWT），抓取方式见下文"异环凭据配置" |
| `nte_refresh_token` | `""` | 塔吉多刷新令牌（可选），用于会话过期后换新令牌对 |

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

5. 重启后端，在页面点击刷新（或等待轮询），账号/体力/活动日历/周期进度/公告应显示真实数据。

## 鸣潮活动与周期进度

鸣潮卡片的"周期进度"来自库街区小组件接口
（`/gamer/widget/game3/getData`，无需额外配置；体力走同族 `refresh` 端点——
参数相同，实测比 getData 的缓存值更实时）：

- **周期进度卡片**：逆境深塔 / 冥歌海墟 / 周本（战歌重奏）/ 千道门扉的异想 /
  终焉矩阵 / 周度游历 / 活跃度 / 结晶单质 / 电台（联觉觉醒之战令）等条目的
  当前进度条与百分比；带重置时间的条目显示"X 天后重置 / 今日重置"。
- 旧的社区活动列表（findEventList）已退役：社区帖子流并非官方活动；
  原"版本活动"卡片（activityData 主推活动）也已删除——游戏内限时活动的
  展示与临期提醒统一由活动日历承担。
- **活动日历（events）**：从版本内容说明公告正文自动解析游戏内限时活动
  （名称 / 类型 / 起止时间，服务器时间 UTC+8），按结束时间升序展示剩余天数；
  结束前 0~3 天推送临期提醒。

## 鸣潮 APP 端 roleBox 抓包教程（可选）

探索度/数据坞/角色练度来自库街区 APP 端独有的 `/aki/roleBox` 系列接口，
鉴权与网页 token **完全不同**：请求不带 `token` 头，靠 APP 内 WebView 会话签发的
`b-at` 头（会话票据）加 `devCode`/`did` 头完成鉴权。抓包时需记录三样，
分别填入 `config.toml` 的三个配置（**三项全部填写才启用**，留空不影响其它功能）：

| 请求头 | 配置项 | 说明 |
| --- | --- | --- |
| `b-at` | `wuwa_b_at` | 会话票据（32 位十六进制），**可能过期** |
| `devCode` | `wuwa_dev_code` | **整串复制**（含公网 IP 和完整 UA） |
| `did` | `wuwa_did` | 设备 UUID |

抓包步骤：

1. **安卓**：安装 [Reqable](https://reqable.com/) 或 HttpCanary → 按应用指引安装并
   信任其 CA 证书 → 打开库街区 APP；**iOS**：使用 Stream（需在应用设置里生成并
   安装描述文件证书）；
2. 在 APP 内进入鸣潮的探索度/数据坞/角色练度页面，在抓包记录中找发往
   `api.kurobbs.com/aki/roleBox/...` 的 POST 请求；
3. 从该请求的请求头中复制 `b-at`、`devCode`（整串含 IP 和 UA）、`did` 三个头的值，
   分别填入 `config.toml` 的 `wuwa_b_at` / `wuwa_dev_code` / `wuwa_did` 后重启后端；
4. 页面刷新后鸣潮卡片应多出"探索度""数据坞""角色练度"三个区块。

`b-at` 是 APP 会话签发的票据，**可能过期**：过期后探索度/数据坞/角色练度会显示
"b-at 已失效或角色不可见，请按 README 重新抓包"提示，重新抓一次三个头
（或仅 `b-at`）填入即可。

注意：`wuwa_app_token` 为预留字段，**当前功能未消费**（探索度/数据坞已改用
上述 roleBox 三件套），保留不填即可。

风险与边界：

- 抓包证书仅本机自用，请勿长期开启抓包或安装来源不明的证书；
- `b-at` 等同账号会话凭据，**不要分享给任何人**（含截图脱敏）；
- 库街区接口属非官方，路径/鉴权随时可能变化，抓包结果仅供个人使用。

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

## 异环（NTE / 塔吉多社区）

异环卡片的能力（announcement / events / roles / progress / gacha / record）数据来自
塔吉多社区接口（`bbs-api.tajiduo.com`，与官方 BBS 同源）：

| 能力 | 前端区块 | 凭据 |
| --- | --- | --- |
| 公告（announcement） | 公告列表 | **无需凭据**，始终可用 |
| 活动日历（events） | 活动日历 | **无需凭据**，始终可用 |
| 角色（roles） | 角色练度墙 | 需塔吉多凭据 |
| 进度（progress） | 周期进度 | 需塔吉多凭据 |
| 抽卡（gacha） | 敬请期待（Phase 2） | 需塔吉多凭据 |
| 战绩（record） | 敬请期待（Phase 2） | 需塔吉多凭据 |

公告走匿名接口（社区"官方资讯"栏目，2026-09-13 实测拉到真实帖子）；
活动日历以**手填为可靠主路径**（`config.toml` 的 `[[nte_events]]`，见下
"游戏内活动手填"），手填为空时回退到版本公告正文自动扫描（与鸣潮同一套
解析器，官方栏目当前暂无版本更新公告在榜，解析格式待下个版本公告出现后
联调校准）；
角色 / 进度 / 抽卡 / 战绩的接口客户端已实现，**解析器待配置凭据联调后激活**
（Phase 2）——配置凭据前这四项显示"未配置塔吉多凭据"，属预期。

### 游戏内活动手填（OCR 辅助）

异环官网前瞻/回顾页的活动起止日期在长图里，HTML 无结构化日期；长图 OCR
自动解析实测不可靠（11 行日期仅 1 行全对，自动入库会静默出错），因此活动
日历采用**手填为主**：每个版本把当期限时活动的名称与起止时间抄进
`config.toml`（**每版本填一次**），时间戳非法的条目会跳过并在后端日志告警
（不会回退到自动扫描）。

```toml
[[nte_events]]
name = "第二索拉·诡影迷踪"
category = "休闲活动"
start = "2026-08-27 04:00"   # 服务器时间（UTC+8），格式 YYYY-MM-DD HH:MM
end = "2026-09-14 03:59"
```

`start` / `end` 可只填其一；填了 `end` 的活动在结束前 0~3 天推送临期提醒。
手填非空时优先于版本公告自动扫描。

抄写长图可用 OCR 辅助命令（RapidOCR 为可选依赖，未安装先执行
`pip install rapidocr-onnxruntime`）：

```bash
# 第一步：从前瞻新闻页找出长图地址（列出页面全部 png/jpg/jpeg/webp）
python -m game_assistant.nte_ocr --news-page <新闻页URL>

# 第二步：对长图 OCR，按行输出"置信度 文本"（自上而下），人工比对后抄写
python -m game_assistant.nte_ocr <图片URL或本地路径> [<更多图片>...]
```

**OCR 数字可能不准，以人眼比对长图为准**——命令输出仅是抄写的参考，
不做自动入库。

### 异环凭据配置（token 抓取）

塔吉多凭据即社区登录态（JWT），抓取步骤：

1. 浏览器打开 [bbs.tajiduo.com](https://bbs.tajiduo.com) 并登录异环社区账号；
2. 按 `F12` 打开开发者工具，切到 **Network（网络）** 面板；
3. 刷新页面，任选一个发往 `bbs-api.tajiduo.com` 的请求，在请求头中复制
   `authorization` 的值（JWT，即访问令牌）；若能在请求/响应中找到
   `refreshToken`（刷新令牌），一并复制；
4. 填入 `config.toml`：

   ```toml
   nte_access_token = "<复制的 authorization>"
   nte_refresh_token = "<刷新令牌，如可获取>"
   ```

5. 重启后端，在页面点击刷新（或等待轮询），角色 / 进度应显示真实数据
   （抽卡 / 战绩待 Phase 2 解析器上线）。

**只拿到 access_token 也先填**：查询能力立即可用；access_token 过期后相关
能力会报"塔吉多会话已失效，请重新抓取 token"，重新抓一次即可。同时填了
`nte_refresh_token` 时，后端可在会话失效后用刷新令牌换取新令牌对（自动续期，
Phase 2 联调激活）。

`authorization` 等同账号登录凭据，**不要分享给任何人**（含截图脱敏）。

### 已知边界

- **无体力接口**：塔吉多社区未提供体力查询端点（参考项目
  [NTEUID](https://github.com/tyql688/NTEUID) 同样如此），故异环无体力能力；
- **无结构化活动列表接口**：官方活动为帖子形式，活动日历（events）以手填
  为主（见上"游戏内活动手填"）；官网前瞻回顾页（yh.wanmei.com）的活动日期
  在长图里，HTML 无结构化日期，OCR 自动入库不可靠（数字识别易错）——提供
  `nte_ocr` 辅助命令按行提取文本供人工比对抄写，自动扫描仅作兜底；
- 需凭据端点的响应解析器为 Phase 2 范围：当前配置凭据后角色 / 进度 /
  抽卡 / 战绩返回原始数据（联调校准后接入对应卡片展示）。

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

### 提醒规则

提醒引擎随每次轮询评估，命中规则时经微信推送，去重记录在 SQLite（`notified` 表）。
四条规则及去重策略（键名均可在 `config.toml` 覆盖）：

| 规则 | 触发条件 | 去重策略 | 配置键（关闭语义） |
| --- | --- | --- | --- |
| 体力已满 | 体力 ≥ 上限 | 每自然日一次 | `notify_stamina_full`（`false` 关闭） |
| 体力即将回满 | 体力 ≥ 上限的 90% 且未满 | 每自然日一次，不与体力满重复 | `stamina_threshold_percent`（设 0 或 ≥100 关闭） |
| 活动日历临期 | 版本公告解析/手填的活动结束前 0~3 天 | 每活动一次（跨日不重复推） | `activity_remind_days`（`0` 关闭） |
| 数据拉取连续失败 | 同一能力连续失败达 3 次（成功即清零计数） | 当日一次 | `fail_notify_threshold`（`0` 关闭） |

推送失败（含 SendKey 未配置）不会标记"已发送"，补配 SendKey 后提醒仍可正常送出。

配置 SendKey 后即真实推送；未配置时仪表盘状态条显示"微信推送未配置（功能已就绪）"，
日志出现 `提醒渠道未启用（send_key 未配置），跳过推送: …`（INFO 级），属预期。
注意 uvicorn 的 `--log-level` 只影响 uvicorn 自身日志，应用 INFO 日志需自行配置
root logging（如启动前 `logging.basicConfig(level=logging.INFO)`）方可在控制台看到。

鸣潮卡片展示周期进度（深塔/海墟/周本等）与活动日历（版本公告自动解析的
游戏内限时活动）；配置 roleBox 三件套后追加探索度（国家分组进度条 + 地区
小字列表 + 残象已收录按级汇总）、数据坞（等级/捕获率/声骸收集）与角色练度墙
（角色总数/满级/6链/五星统计 + 头像网格：等级/属性/命链/五星角标）区块，
不再提供社区活动列表。

## 已知限制

- **非官方接口**：鸣潮数据来自库街区社区接口（非官方公开 API），路径/参数可能随上游变动。
  若某能力报"接口错误"，按
  [src/game_assistant/adapters/wuthering_waves/endpoints.py](src/game_assistant/adapters/wuthering_waves/endpoints.py)
  文件头注释的校准流程核对并修复（只需改该文件）。
- **端口 8000 不可用**：Windows 系统服务 HTTP.sys（PID 4）永久占用 8000 端口，
  本项目默认端口统一为 **8010**，请勿改回 8000。
- 轮询采用定时拉取模拟准实时，不承诺 100% 实时。
