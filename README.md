# 游戏管家

个人使用的本地游戏看板，集中查看鸣潮、异环、明日方舟：终末地和英雄联盟的账号数据、活动日历及公告资讯。后端使用 Python / FastAPI / SQLite，前端使用 Vue 3 / Vite；Windows 下可一键启动，网页与 API 共用 `8010` 端口。

本项目采用 **GPL-3.0-only**，见 [LICENSE](LICENSE) 和 [第三方说明](THIRD_PARTY_NOTICES.md)。公开版使用原创文字标识图标，不分发官方游戏图包。仅支持本机单用户使用；安全边界和漏洞反馈见 [SECURITY.md](SECURITY.md)。

**鸣潮、异环、终末地（官服）均已支持页面短信登录，正常使用无需手机抓包，也无需手工填写 token、b-at 或设备标识。** 手游资讯和日历以 B 站官方动态为主、社区为补充；LOL 保持客户端和原资讯渠道。

## 当前功能

| 游戏 | 已实现内容 | 登录方式 |
| --- | --- | --- |
| 鸣潮（官服） | 账号、体力、周期进度、角色练度、探索度、数据坞、公告与活动日历 | 看板「社区账号」中短信登录库街区 |
| 异环 | 账号、体力与日常、角色筛选/排序/收藏/对比、成就、探索、房产与载具详情、官方配队、社区抽卡统计、本地逐抽账本、公告与活动日历 | 看板「社区账号」中短信登录塔吉多 |
| 英雄联盟（国服） | 账号、最近20场战绩与统计、单场详情、公告资讯 | 启动并登录本机英雄联盟客户端，自动发现 LCU |
| 终末地（官服） | 账号、寻访记录自动同步与本地账本、B站资讯、版本公告解析的活动日历 | 看板「社区账号」中短信登录鹰角通行证 |

看板有四个主要入口：

- **今日总览**：游戏摘要、体力、临近截止的活动、公告资讯。
- **游戏档案**：按游戏能力展示概览、角色与探索、近期对局、抽卡统计、公告资讯。
- **活动日历**：独立横向时间轴，支持游戏筛选、近30天／整月／14天、翻页和活动详情。默认将今天放在偏左侧，同游戏活动紧凑排列。
- **社区账号**：鸣潮、异环与终末地登录、重新登录、退出及登录状态。

异环「抽卡统计」默认展示三池统计卡、头像与出 S 抽数横条，以及塔吉多官方近期评价和欧非标签，见[标签来源说明](docs/nte-community-gacha-ui.md)。页面下方的可选「本地逐抽账本」支持逐抽 JSON 校验预览、去重导入、分池查询、导出与分段备份。垫抽根据已导入记录的连续性计算；保底剩余需要自行核对并设置对应卡池规则。当前尚未取得国服完整历史自动同步接口，社区出 S 汇总不能替代逐抽记录，国服导出兼容性尚待实测。详见[抽卡实现形式与待补接口](docs/nte-gacha.md)。

## 第一次运行

### 环境

- Windows 10 / 11：支持单用户本机运行；Linux 部署和公网托管不在支持范围内。
- Python **3.11 或以上**；CI 覆盖 3.11 / 3.12，初次安装建议使用这两个版本。
- Node.js **22.12 或以上**；CI 使用 Node.js 22。
- Git。

在 PowerShell 中执行：

```powershell
git clone https://github.com/miyako-md/game-manage.git
cd game-manage
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item config.example.toml config.toml
cd frontend
npm ci --registry=https://registry.npmjs.org
cd ..
.\启动游戏管家.bat
```

已有 `config.toml` 的机器不要再次覆盖配置。模板已配置鸣潮、异环的官方 B 站 UID，私人游戏账号通过页面登录。

启动脚本根据 `package.json` 和 `package-lock.json` 的内容指纹检查依赖，变化或安装不完整时执行 `npm ci` 并重建看板；只有安装成功才保存标记。首次运行脚本会校验安装一次。随后启动或复用后台，并在默认浏览器打开 **http://127.0.0.1:8010/**。正常使用不需要另开 `5173`。启动脚本固定监听该地址，`config.toml` 不能改变监听地址或端口。

`dev` 包含测试所需的 NumPy / OpenCV，普通看板不依赖 OCR 引擎。要使用独立的长图 OCR 辅助命令，可另执行 `.\.venv\Scripts\python.exe -m pip install -e ".[ocr]"`；未安装时命令会给出提示。OCR 不会自动将图片日期导入日历。

### 更新已有安装

在仓库根目录执行，先保留自己的 `config.toml` 和 `data/`；升级时无需再次复制配置模板：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop.ps1
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install --upgrade -e ".[dev]"
cd frontend
npm ci --registry=https://registry.npmjs.org
cd ..
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/launch.ps1 -Rebuild
```

若 Git 提示本地改动冲突，先保存并处理改动，再继续升级。不要删除 `data/` 来解决依赖问题。

### 使用锁定的后端依赖（可选）

仓库提交 `uv.lock`，CI 按它安装依赖。上面的 pip 流程适合一般安装，但会解析当前满足版本范围的依赖。需要与锁文件一致时，可用以下命令替代 pip 安装项目的步骤：

```powershell
python -m pip install uv==0.12.3
uv sync --locked --extra dev
# 需要 OCR 引擎时改用：uv sync --locked --extra dev --extra ocr
```

`uv sync` 使用项目的 `.venv` 并清理未声明的依赖，因此请勿与其他项目共用虚拟环境。维护依赖时更新 `pyproject.toml` 后执行 `uv lock --default-index https://pypi.org/simple`，将锁文件一同提交。前端以 `package-lock.json` 和 `npm ci` 固定依赖。

### 日常启动与停止

双击根目录的 **[启动游戏管家.bat](启动游戏管家.bat)** 即可。重复运行会复用健康的受管后台；关闭网页或启动窗口不会停止后台。

```powershell
# 启动但不打开浏览器
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/launch.ps1 -NoBrowser

# 强制重建看板后启动
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/launch.ps1 -Rebuild

# 查询状态、重启、停止
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/status.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/restart.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop.ps1
```

日志位于 `data/runtime/service.log`。若8010被非本项目管理的进程占用，脚本会报错并保留该进程。登录后自启动默认关闭，启用和撤销见[本地运行说明](docs/local-runtime.md)。

## 配置游戏账号

打开看板的 **「社区账号」**，选定游戏后按页面提示操作：

| 游戏 | 操作 | 程序自动处理 |
| --- | --- | --- |
| 鸣潮 | 输入手机号，开始登录，手动完成人机验证，发送并填写短信验证码，登录并保存 | 登录 token、绑定角色、设备标识、roleBox 会话票据 b-at，以及短期票据续期 |
| 异环 | 输入手机号，开始登录，发送并填写短信验证码，登录并保存 | 塔吉多 access/refresh token、绑定角色和令牌续期 |
| 终末地 | 输入鹰角通行证手机号，开始登录，发送并填写短信验证码，登录并保存 | 通行证 token、官服角色；寻访记录授权在每次同步时临时换取 |

登录后进入对应游戏，点击「刷新数据」。主登录态或刷新令牌失效时，回到此页面重新登录即可。退出只清除本工具中该游戏的登录状态和私人快照，不注销社区账号，也不删除公共资讯。

凭据默认保存到 `data/assistant.credentials.json`，Windows 使用当前系统用户的 DPAPI 加密，短信验证码不落盘。旧版 `config.toml` 手填字段仅保留兼容；已保存的页面登录优先，正常使用可不填写这些字段。详见[社区登录说明](docs/community-login.md)。

**LOL 无需填写社区凭据。** 账号与战绩依赖本机客户端运行；客户端关闭时显示离线并保留旧快照。最近20场统计不代表完整生涯统计。

## 手游资讯与活动日历

鸣潮、异环、终末地以官方 B 站动态为主来源，社区公告作为补充和回退（终末地暂无社区来源）。此规则不用于 LOL。模板已包含以下公开账号，UID是游戏官方账号，不是用户自己的账号：

```toml
[bilibili_sources]
wuthering_waves = "1955897084"
nte = "3546636978489848"
endfield = "1265652806"
```

已有 `config.toml` 的机器需在 `[bilibili_sources]` 下手动加上 `endfield` 这一行，否则终末地没有资讯和日历。终末地版本公告用「版本名」标识，“版本更新维护前”在下个版本的维护预告发布前显示为截止未知，口径见[终末地数据说明](docs/endfield-data.md)。

默认回补最近 **60天**，后台约每 **10分钟**检查更新；失败会退避并保留已取得的记录。页面底部「B站官方动态来源」提供采集状态、回补、筛选记录和登录配置。

**B站登录与游戏社区登录相互独立。** 当前来源面板支持输入B站 `SESSDATA`，以及可选的 `bili_jct`、`buvid3`；凭据仅在本机加密保存。匿名请求可能受到分页限制，配置登录后可重试回补。此前扫码验证通过辅助脚本完成，当前产品页面尚无内置B站扫码入口。

收录与解析规则：

- 保留正文有明确日期、与游戏内更新、活动或卡池直接相关的图文通知。
- 过滤视频、转发视频、抽奖、PV/EP、实机演示、时装展示、周边、网页活动和线下宣传。
- 长公告补读全文，保留作者、动态ID、正文、原链接和日期依据；截断且无法取得全文的内容不会直接采纳。
- 版本总公告生成日历基础数据，独立活动和卡池通知补充时间与后续调整。同内容优先B站，社区只补明确同版本的缺项。
- “版本更新后”保留为相对时间。只有日期时按日期展示活动条，详情明确具体时刻未知，不自动填成00:00或维护预计结束时刻。
- 新版本前瞻不替代当前版本；多阶段保留独立时段。图片内日期暂不自动OCR入库。

2026-09-16实测样本：鸣潮3.6版本日历16项，异环1.3版本23项，数量会随公告变化。规则与证据见[B站来源说明](docs/bilibili-source.md)及[日历验证报告](docs/bilibili-calendar-validation.md)。

## 数据刷新与可信度

| 数据 | 当前来源与处理 | 边界 |
| --- | --- | --- |
| 鸣潮体力、单质、活跃度等 | 先刷新角色面板，再读取对应字段；深塔使用专项接口的周期性深境区 | 不承诺与游戏零延迟同步；失败保留旧快照 |
| 鸣潮角色、探索、数据坞 | 短信登录自动取得的 roleBox 会话 | 主登录过期需重新登录，不要求重新抓包 |
| 异环账号与游戏数据 | 塔吉多角色及专项接口；手动刷新清除本地复用缓存 | 官方体力、都市活力存在同步延迟，清缓存不能修复上游数据 |
| 异环抽卡 | 社区统计及出S明细；另有本机逐抽 JSON 账本 | 社区统计不能推算当前保底；账本依据导入覆盖计算，尚未接通国服全历史自动同步 |
| LOL账号与战绩 | 本机 LCU，凭据随客户端变化动态发现 | 客户端离线时不能更新账号与战绩 |
| 终末地账号与寻访记录 | 鹰角通行证授权后查询绑定角色与官方寻访记录，本机账本累积保存 | 接口尚未经真实账号实测；官方约只保留 90 天，首次同步较多时分几次完成 |

默认体力5分钟轮询，进度／账号／角色等主要为1小时，探索／数据坞／部分慢变化数据为4小时。看板每60秒读取本地快照；「刷新数据」会触发采集，B站任务异步执行。各来源独立记录成功时间、失败次数与错误，缺失值不直接当作零。来源细节：[鸣潮](docs/wuwa-data.md) · [异环](docs/nte-data.md)。

## 配置与本地数据

主要配置集中在 `config.toml`，完整模板见[config.example.toml](config.example.toml)。

| 配置 | 默认值／用途 |
| --- | --- |
| `wuwa_enabled` / `nte_enabled` / `lol_enabled` / `endfield_enabled` | 是否启用对应游戏 |
| `db_path` | `data/assistant.db`，快照、来源记录与提醒去重 |
| `stamina_seconds` | `300`，体力轮询间隔 |
| `activity_seconds` / `announcement_seconds` | `3600`，进度等／社区公告与活动轮询间隔 |
| `news_seconds` | `14400`，社区资讯及慢变化数据轮询间隔 |
| `bilibili_history_days` / `bilibili_poll_seconds` | `60` / `600`，B站回补窗口与轮询间隔 |
| `auth_store_path` | 留空使用数据库旁的凭据文件 |
| `auth_allowed_origins` | 所有 API 的浏览器 Origin 允许列表，默认仅本机8010、5173；写请求还需要 `X-Game-Assistant: 1`。不是公网用户鉴权。 |
| `notify_provider` / `notify_send_key` | 微信推送渠道与密钥，密钥留空即不发送 |

`config.toml`、`data/`、虚拟环境、node_modules和构建产物均不提交Git。换电脑后应重新登录社区；Windows凭据文件绑定原系统用户，不能当作通用配置直接复制使用。

### 可选微信提醒

可在配置中填写 Server酱或 PushPlus 的密钥，再重启后台。已有体力满、接近满、活动临期和连续失败提醒，按北京时间去重；客户端正常离线及未配置账号不累计故障告警。

**当前活动提醒仍由游戏适配器的事件轮询触发，尚未接入B站合并日历。** B站补出的活动能在看板看到，不代表都会触发微信提醒。异环体力还受官方同步延迟影响，开启相关提醒前应考虑这一限制。

## 开发与验证

开发模式在两个终端分别执行：

```powershell
# 终端一：后台
.\.venv\Scripts\python.exe -m uvicorn game_assistant.main:app --host 127.0.0.1 --port 8010

# 终端二：前端热更新
cd frontend
npm ci
npm run dev
```

开发看板位于 `http://127.0.0.1:5173/`，`/api`代理到8010。已运行受管后台时可直接复用，不要重复占用端口。

```powershell
# 后端测试
.\.venv\Scripts\python.exe -m pytest -q

# 前端测试和生产构建
cd frontend
npm test
npm run build
```

2026-09-16主分支整合验证记录（鸣潮扩展及异环社区抽卡改版）：后端657项通过、4项条件跳过，前端134项通过，生产构建成功。跳过项包含需要显式启用的运行管理测试及Windows符号链接权限用例；测试通过不等同于所有上游接口持续可用。

```text
src/game_assistant/
  adapters/          鸣潮、异环、终末地、LOL适配器与字段解析
  auth/              短信登录、令牌续期、本地加密存储
  sources/           B站采集、筛选、日历解析与来源合并
  api.py             API与快照接口
  scheduler.py       游戏能力定时采集
frontend/            Vue看板与前端测试
scripts/             一键启动、启停管理、自启动
tests/               后端回归测试
docs/                使用说明、数据口径与历史设计记录
```

## 已知限制与排查入口

- 当前面向单用户本机使用，默认只监听127.0.0.1；没有公网多用户权限体系。
- 游戏社区和B站接口、登录规则可能变化；接口成功不等于数据已与游戏实时同步。
- B站未公开、已删除、仅图片载明日期或格式尚不支持的公告可能无法生成日历事件；“60天回补完成”表示已完成返回列表的窗口遍历。
- 图片OCR自动入库、国服抽卡历史自动同步、官方 UP 保底追踪、伤害计算尚未交付。逐抽文件导入已经可用，当前真实账号尚未导入记录。
- 终末地的理智、练度、探索和签到需要森空岛数据，而现有实现都要伪造设备指纹，暂未接入；终末地接口整体尚未实测，见[实施指导](docs/endfield-implementation-guide.md)。
- 登录问题先看「社区账号」和游戏采集状态；B站问题看来源面板；启动问题看 `data/runtime/service.log`。

更多记录：[登录说明](docs/community-login.md) · [终末地数据](docs/endfield-data.md) · [运行管理](docs/local-runtime.md) · [改动汇总](docs/changes-2026-09-16.md) · [分支与对话核查](docs/branch-audit-2026-09-16.md)。`docs/superpowers/`保存历史设计与实施过程，历史阶段描述不代表当前使用步骤。
