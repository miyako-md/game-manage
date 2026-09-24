# 终末地接入实施指导（官服）

编写日期：2026-09-24。本文件依据[可行性评估](endfield-feasibility.md)，把接入工作拆成可以逐步实施的里程碑。本文只是指导，不含代码改动。

## 已定决策

| 事项 | 决定 |
|---|---|
| 服务器 | 先做官服（鹰角通行证账号）。B服和国际服不在本期范围 |
| 活动日历 | 直接解析官方公告，不做手填 |
| 签到 | 能做就做，不强求；做不了就跳过 |
| 设备指纹 | 本轮没有改动需求文档的边界，所以默认**不伪造数美 dId**。森空岛相关功能只走不需要伪造指纹的路径，走不通就不做；如果以后要放宽，另行决定 |
| 提交方式 | 暂不提交 PR |

下文的接口事实都来自参考项目源码和公开页面，**没有经过实测**。所以第一步（M0）是在本机实测，确认后再动手。

## 里程碑总览

| 里程碑 | 内容 | 完成标准 |
|---|---|---|
| M0 本机实测 | 通行证登录、寻访接口、B站全文、森空岛无指纹路径 | “实测记录”一节填写完整 |
| M1 骨架与登录 | 注册适配器，实现通行证短信登录，显示账号基础信息 | 页面能登录，并显示昵称和 UID |
| M2 寻访记录 | 自动增量同步、本地账本、前端面板 | 近期记录与游戏内寻访记录逐条一致 |
| M3 资讯与日历 | B站资讯，以及终末地公告解析 | 当前版本的卡池和活动出现在日历上，时间与公告一致 |
| M4 森空岛（可选） | 理智、周期进度、练度、探索、签到 | 视 M0 结果决定是否实施 |

M1 到 M3 互不依赖森空岛，可以按顺序完成。M4 只有在 M0 证明存在不伪造指纹的路径时才实施。

## M0：动手前的本机实测

在自己的 Windows 机器上用临时脚本逐项请求，把结果填进文末的“实测记录”。请求要低频，每步只做一两次。

### 1. 通行证短信登录

1. `POST https://as.hypergryph.com/general/v1/send_phone_code`，请求体 `{"phone": "<手机号>", "type": 1}`。
2. `POST https://as.hypergryph.com/user/auth/v1/token_by_phone_code`，请求体 `{"phone": "<手机号>", "code": "<验证码>"}`，从 `data.token` 取得 token。

需要记录：是否出现人机验证；错误时 `status` 和 `msg` 的取值（注意这里的字段是 `status`，不是 `code`）；token 的长度。另外留意 token 多久后失效，以及失效时的返回内容。

### 2. 寻访记录链路

1. `POST https://as.hypergryph.com/user/oauth2/v2/grant`，请求体 `{"token": <通行证 token>, "appCode": "be36d44aa36bfb5b", "type": 1}`，返回 `data.token`。
2. `GET https://binding-api-account-prod.hypergryph.com/account/binding/v1/binding_list?token=<上一步 token>&appCode=endfield`，返回 `uid` 和 `roles`。
3. `POST https://binding-api-account-prod.hypergryph.com/account/binding/v1/u8_token_by_uid`，请求体 `{"uid": <uid>, "token": <第 1 步 token>}`，返回 `data.token`，即 u8_token。
4. `GET https://ef-webview.hypergryph.com/api/record/char?token=<u8_token>&server_id=1&pool_type=E_CharacterGachaPoolType_Special&lang=zh-cn`，翻页时追加 `seq_id=<上一页最后一条的 seqId>`。
5. `GET https://ef-webview.hypergryph.com/api/record/weapon/pool?token=…&server_id=1&lang=zh-cn`，再按返回的池 ID 请求 `/api/record/weapon?pool_id=…`。

需要记录：

- 每页条数（参考项目说是 5 条），以及 `data.list` 和 `data.hasMore` 的结构。
- 单条记录的字段。参考项目用到了 `seqId`、`charId`/`charName`、`weaponId`/`weaponName`、`rarity`、`poolName`、`gachaTs`、`isFree`。
- 能查到的最早记录日期，用来验证“约 90 天”的说法。
- 四种已知角色池类型（`Special`、`Standard`、`Beginner`、`Joint`）各自的返回。
- 「重构寻访」（2026-09-24 开启）的记录出现在哪个池类型下，还是需要新的枚举值。可以用浏览器打开官方记录页 `ef-webview.hypergryph.com/page/gacha_char`，在开发者工具里看它请求时带的 `pool_type`。
- token 在 URL 里是否必须做 URL 编码。

### 3. B站官号全文

配置 `endfield = "1265652806"` 后回补 60 天，确认以下两点：

- 「X」版本更新说明、「Y」特许寻访说明是否以全文进入（opus 或专栏）。已知「春晓时」版本更新说明在 B站有全文 opus：<https://www.bilibili.com/opus/1192064737057177641>。
- 这些动态被判成了什么 `reason`。按现有规则，它们很可能被判为“宣传展示”，原因见 M3。

### 4. 森空岛无指纹路径（决定 M4 做不做）

按顺序尝试，任何一步成功就可以停下：

- **A. 换 cred 时完全不带 dId 请求头**（TNXG/skland-api 的做法）：先 `grant`，请求体 `{"appCode": "4ca99fa6b56cc2ba", "token": …, "type": 0}`，再 `POST https://zonai.skland.com/api/v1/user/auth/generate_cred_by_code`，请求体 `{"kind": 1, "code": …}`。记录返回。
- **B. 使用浏览器已登录的 cred**：在自己的浏览器登录 www.skland.com，在开发者工具任意 `zonai.skland.com` 请求的请求头里复制 `cred`。然后用 `GET https://zonai.skland.com/api/v1/auth/refresh`（请求头只带 `cred`）换取签名 token。
- 拿到 cred 和签名 token 后，用**空 dId** 依次请求 `GET /api/v1/game/player/binding`、`GET /api/v1/game/endfield/card/detail`、`POST /api/v1/game/endfield/attendance`，记录各自是否被拒。
- 如果 card/detail 拒绝空 dId，可以再试一次浏览器请求头里的 `dId`。这个值是官方 SDK 在你自己的设备上生成的，不属于伪造。
- 每一步都记录 `code` 和 `message`。只要需要本地生成或提交伪造的设备指纹才能通过，就判定这条路径走不通。

签名算法（参考 EndUID `utils/api/ds.py`），GET 请求用 query 字符串，POST 请求用 JSON body：

```python
import hashlib, hmac, json, time

def sign(token: str, path: str, query_or_body: str, did: str = "") -> dict:
    ts = str(int(time.time()))
    header = json.dumps({"platform": "3", "timestamp": ts, "dId": did, "vName": "1.0.0"},
                        separators=(",", ":"))
    digest = hmac.new(token.encode(), (path + query_or_body + ts + header).encode(),
                      hashlib.sha256).hexdigest()
    return {"sign": hashlib.md5(digest.encode()).hexdigest(), "timestamp": ts,
            "platform": "3", "dId": did, "vName": "1.0.0"}
```

## M1：骨架与登录

### 后端文件

| 文件 | 改动 |
|---|---|
| `src/game_assistant/adapters/endfield/endpoints.py` | 集中定义域名和路径。文件头仿照 `adapters/neverness/endpoints.py`，逐条写明协议来源和实测日期（EndUID `7781451`、bhaoo/endfield-gacha `72c526d`） |
| `src/game_assistant/adapters/endfield/hg_client.py` | 通行证客户端：`grant`、`binding_list`、`u8_token_by_uid`。以 `status == 0` 判断成功，失败时抛 `EndfieldError(message, status)`。每次拉取新建 `httpx.AsyncClient`，用 `async with` 收尾，超时 15 秒 |
| `src/game_assistant/adapters/endfield/parse.py` | 把 binding 数据转成 `AccountInfo`：`nickname`、`extra={uid, role_id, server_name, channel}` |
| `src/game_assistant/adapters/endfield/adapter.py` | `EndfieldAdapter`：`game_id="endfield"`、`display_name="终末地"`、`section="mobile"`。M1 只声明 `ACCOUNT` |
| `src/game_assistant/config.py` | 新增 `endfield_enabled: bool = True`，以及与登录服务 `FIELDS` 对应的字段 `endfield_hg_token`、`endfield_uid`、`endfield_role_id`、`endfield_server_id` |
| `src/game_assistant/registry.py` | `endfield_enabled` 为真时注册适配器 |
| `config.example.toml` | 增加 `endfield_enabled = true`；`[bilibili_sources]` 增加 `endfield = "1265652806"`，同时更新注释里“只对这两款手游”的说法 |

### 登录服务

`src/game_assistant/auth/providers.py` 新增 `EndfieldLoginProvider`：

- `start_context()` 返回空上下文即可，这条链路没有设备 ID。
- `send_sms()` 调用 `send_phone_code`。
- `login()` 依次调用 `token_by_phone_code`、`grant(type=1)`、`binding_list`。选出官服角色后，返回 `{hg_token, uid, role_id, server_id, nickname}`。如果没有绑定终末地角色，提示“该账号未绑定终末地角色”。
- `renew()`：通行证 token 没有刷新机制。续期时用 `grant` 验证一次，失败就按登录失效处理。
- 现有的 `_request()` 只认 `code` 字段，鹰角接口用的是 `status` 和 `msg`。需要给 `_request()` 加一个 `status_key` 参数，或者单独写一个小函数；不要把 `status` 硬塞进 `code` 的判断逻辑。

`src/game_assistant/auth/service.py` 需要以下调整：

- `GAMES` 加入 `'endfield'`，`FIELDS['endfield']` 映射上面的四个字段。
- `_configured()` 和 `fetch()` 里现在用 `game == GAMES[0]` 区分鸣潮和“其他”。加入第三个游戏后要改成按游戏显式判断，否则终末地会落进异环的分支。终末地的判断条件是 `hg_token` 存在。
- 公开能力绕过登录锁：现在只对 `nte` 写死了 `ANNOUNCEMENT`/`EVENTS`/`TEAMS`，改成按游戏配置公开能力集合，终末地为 `{ANNOUNCEMENT, EVENTS}`。
- 失效码：先按 M0 实测到的 `status` 值映射，在确认之前只把 HTTP 401/403 当作登录失效。

### 前端

- `frontend/src/components/LoginPanel.vue`：`GAMES` 加 `{ id: 'endfield', name: '终末地' }`。不需要极验，`needsCaptcha` 保持只对鸣潮生效。
- `frontend/src/dashboard.js`：`GAME_STYLE.endfield = { mark: '终', icon: '/game-icons/endfield-mark.svg', color: <自选>, english: 'ARKNIGHTS: ENDFIELD', resource: '理智' }`。第 58 行主来源判断的列表也要加上 `'endfield'`。
- `frontend/public/game-icons/endfield-mark.svg`：套用 `nte-mark.svg` 的模板，只改文字“终”和颜色；同时在 `sources.json` 追加一条来源说明，写明是原创文字标识，保持“不分发官方图包”的约定。
- `frontend/src/components/OverviewPage.vue`：参照第 32 行异环的写法，为终末地补一句数据来源说明。

### 测试

- `tests/test_auth_providers.py`：用 respx 离线模拟 `send_phone_code`、`token_by_phone_code`、`grant`、`binding_list`，覆盖以下情况：成功；验证码错误；没有绑定角色；接口返回 `status != 0`。
- `tests/test_auth_service.py`：覆盖三个游戏各自的 `_configured` 判断；终末地公开能力不受登录锁限制。
- `frontend/src/components/LoginPanel.test.js`：能选择终末地，且不会加载极验。

## M2：寻访记录

### 同步流程

每次同步都先用通行证 token 执行 `grant(type=1)`，再调用 `u8_token_by_uid` 取得新的 u8_token。u8_token 只放在内存里，不落盘。

对每个池（四种角色池类型，加上武器池列表里的每个 `pool_id`）按以下规则逐页请求：

1. 首页不带 `seq_id`；之后每页用上一页最后一条的 `seqId` 翻页。
2. 页与页之间至少间隔 0.5 秒，并设置单池最大页数上限。
3. 出现以下任一情况即停止：连续遇到一定数量的已知 `seqId`（EndUID 的阈值是 50 条）；`hasMore` 为假；返回空列表。
4. 记下本次是“接上了已有记录”还是“翻到了官方窗口的尽头”，后者表示更早的记录已无法取得。

还有几点要注意：

- 首次全量同步可能需要请求几百次，不要放在登录服务的锁里执行（`LoginService.fetch()` 执行期间一直持有该游戏的锁）。做法是在锁内取得 u8_token，然后交给后台任务同步，并提供进度查询，做法可以参考B站回补。
- 遇到不认识的池类型或字段时，写入“未知”，不要静默丢弃。新卡池可能带来新的类型：「辉光庆典」（`Joint`）是随 2026-05-14 开启的卡池才出现的，EndUID 当天补上了支持。
- 寻访记录接口以 `code == 0` 判断成功，这和通行证接口使用的 `status` 字段不同。

### 存储

新增 `src/game_assistant/endfield_gacha.py`，数据库文件为 `db_path` 旁的 `.endfield-gacha.sqlite3`。结构参考 `nte_gacha.py` 的 `GachaStore`：

- `records(role, pool_key, seq_id, payload)`，主键为前三列。`pool_key` 取角色池类型，或 `weapon:<pool_id>`。
- `sync_state(role, pool_key, newest_seq, oldest_seq, last_sync_at, reached_known, window_exhausted)`。
- 账本按 `role_id` 隔离。退出登录时不删除账本，这与异环的逐抽账本一致。

### 统计口径

- 沿用 `docs/nte-gacha.md` 的 exact / lower_bound / unknown 三级口径。只有覆盖连续、没有缺口时，才给出“距上次 6★ N 抽”的确定值；缺口会让结果降级为下限或未知。
- 不内置保底数值。终末地的规则一直在变：1.5 版本新增的「重构寻访」，官方公告写明“寻访规则与其他的干员寻访不同”，社区解读为大保底可以在同一角色的复刻之间继承。如果需要保底提示，参照异环 `rules` 接口，由用户配置规则并注明依据。
- `isFree` 记录是否计入垫抽，要在 M0 核对后再决定，未核对前按“未知”处理。

### 接口与前端

- 能力 `GACHA`：适配器按 `news_seconds`（默认 4 小时）轮询，执行增量同步，然后把各池的统计写入快照。
- 路由 `/api/endfield/gacha/summary`、`/records`、`/export`，以及 `POST /sync`（手动同步）。安全要求沿用 `nte_gacha_routes.py`：只接受本机 Host 和 Origin，写请求要带 `X-Game-Assistant: 1` 头，禁止缓存响应。
- 前端新增 `EndfieldGachaPanel.vue`：分池标签、6★ 历史、覆盖状态。页面要写明“官方只能查到约 90 天，本地账本从第一次同步开始积累”。在 `GameCard.vue` 的 `capComponent()` 里为 `endfield` 的 `gacha` 指定这个组件。

### 测试

- 翻页：每页 5 条，用 `seqId` 作游标，遇到已知记录停止，达到页数上限时停止。
- 去重：同一 `seq_id` 重复写入不会产生新行；同键内容冲突时报错。
- 未知池类型会出现在统计结果里，不会被丢弃。
- u8_token 不出现在日志、异常信息和快照中。

## M3：资讯与日历（公告解析）

### 来源

- **主来源：B站官号**。已确认官号会以全文 opus 发布版本更新说明。
- **备选来源：官网公告** `https://endfield.hypergryph.com/news`，详情页为 `/news/<id>`。列表里每条标注“公告”或“新闻”，例如“公告 2026.08.08「晨星于此闪耀」特许寻访说明”。本轮环境无法访问官网，M0 时要确认数据来自服务端渲染的 HTML 还是 JSON 接口。
- 两个来源共用同一个终末地解析模块，输入都是正文按行拆分后的列表。

配置上，`sources/public_content.py` 的 `MOBILE_GAMES` 要加入 `'endfield'`。这样 `/api/games` 会为终末地自动加上 `news` 和 `events` 能力，快照接口也会按手游规则把B站和原生来源合并。

提醒功能目前只会在适配器自己的 `EVENTS` 轮询中触发，B站合并出来的日历不会触发（见 README 的“可选微信提醒”一节）。所以如果需要终末地活动的临期提醒，就要把官网公告做成适配器的原生 `EVENTS`。另一种办法是让提醒接入合并后的日历，但那是影响所有游戏的改动，建议单独立项。

### B站过滤规则要改

在本地用 `classify_dynamic` 模拟过：一篇全文版的「雪凇幽梦」版本更新说明会被判为 `promotion`（宣传展示）并排除。原因有两个：

1. 正文里有“前往网页活动”，命中了 `PROMOTION` 规则中的“网页活动”。
2. 标题“版本更新说明”“版本更新维护预告”“特许寻访说明”都匹配不上 `NOTICE_TITLE`，而现有规则依赖它来豁免正文里的宣传词。

`src/game_assistant/sources/bilibili.py` 的改法：在 `NOTICE_TITLE` 里加入终末地的标题写法（`版本更新说明`、`版本更新维护预告`、`版本预下载与更新预告`、`(特许|特殊|重构)寻访说明`、`申领.*说明`、`限时特卖说明`）；把 `RULE_VERSION` 升到 5；补充三类标题的测试，并确认鸣潮和异环已有的过滤测试不受影响。

### 解析规则

新建 `src/game_assistant/sources/endfield_notice.py`。`public_content.parse_post_events()` 和 `calendar_from_posts()` 遇到 `game == 'endfield'` 时交给这个模块处理，鸣潮和异环的分支保持不动。

在本地用现有解析器跑过公告原文：`calendar_from_posts` 返回空，即使补上标题识别，16 个编号条目也只有 5 个能取到时间。下表是需要支持的写法，原文示例都摘自官方公告：

| 要素 | 原文示例 | 处理 |
|---|---|---|
| 版本基准公告 | `「雪凇幽梦」版本更新说明` | 用「版本名」作版本键，不再依赖 `x.x版本` |
| 版本上线时间 | `■ 更新维护时间` 下一行：`2026/09/02 06:00 - 2026/09/02 12:00（UTC+8）` | 维护结束时刻就是版本开启时刻，“版本开启后”取这一天 |
| 下个版本预告 | `「春晓时」版本更新维护预告`：“计划将于2026年4月17日 06:00（UTC+8）开始……停机维护” | 维护开始时刻即上个版本的“版本更新维护前”，用来补全结束时间 |
| 编号条目 | `1.「冬猎」特许寻访`、`2. 「行舟申领」开放`、`3.「辉光庆典」特殊寻访`、`3.「绚丽异彩」重构寻访#1`、`2.「幽寒申领」` | 数字后可能有空格；类型后缀可以没有 |
| 单独公告条目 | `▼//「晨星于此闪耀」特许寻访说明` | 当作一个条目 |
| 嵌套与附带 | `○「虚像赛季」`；`同时，玩法更新后还将同步开放「丰碑留名·刻影」限时挑战活动` | 生成独立条目，不能把时间算到上一个标题名下 |
| 分类 | 小节 `■ 全新寻访及申领` / `■ 全新活动` / `■ 活动及玩法更新` | 寻访类归“角色寻访”，申领类归“武器申领”，活动取后缀（签到活动、引入活动等），玩法更新单独一类 |
| 时间标签 | `开放时间`、`活动时间`、`活动开放时间`、`物资兑换处开放时间`、`赛季更新`、`更新时间` | 都视为时间行 |
| 绝对时间 | `2026/09/24 12:00（服务器时间）` | 官服的服务器时间就是北京时间；年份都是写全的 |
| 相对开始 | `「雪凇幽梦」版本更新后`、`「向渊行」版本开启后`、`公测开启后` | `start_precision='relative'`，`start_date` 取版本开启日 |
| 版本末结束 | `… - 版本更新维护前` | `end_at=None`，`end_precision='version_end'`；有下个版本预告后再补全 |
| 整个版本 | `「雪凇幽梦」版本期间` | 相对开始，加上版本末结束 |
| 依附结束 | `于3次「特许寻访」后结束（从「冬猎」起计算）`、`于「辉光庆典」特殊寻访后结束` | `end_precision='dependent'`，原文放进 `end_text`；第一版先不自动推算 |
| 常驻 | `「春晓时」版本开启后常驻开放` | 不进日历，或标为常驻 |
| 多段时间 | 标签后为空，下面几行各写一段；或用“及”连接两段 | 每段生成一个事件，名称相同，附带阶段序号 |
| 分隔符 | 国服用 ` - `，繁中和国际服用 `~` | 两种都支持，也兼容“至” |

数据格式在现有事件字典的基础上新增 `end_text`、`end_precision`（取值 `minute`、`version_end`、`dependent`、`unknown`），`version` 改存版本名。仍然遵守“不虚构截止时间”：只有找到明确的维护公告，才能补全 `end_at`。

前端 `CalendarPage.vue` 已经支持“截止未知”的点状显示，详情区会显示 `time_text`。只需在详情里增加一行 `end_text`，比如“版本更新维护前（待维护公告）”。

### 测试用例

按原文整理下列公告作为测试用例（只保留标题和时间行，不含账号信息）。每篇写出期望的事件列表：

| 公告 | 来源 | 覆盖的写法 |
|---|---|---|
| 「新潮起，故渊离」版本更新说明（2026-03-12） | 官网 news/6003 | 多段“及”、依附结束、玩法更新 |
| 「春晓时」版本更新说明（2026-04-17） | B站 opus 1192064737057177641 | 特殊寻访、依附于某寻访的结束、常驻、活动开放时间 |
| 「春晓时」版本更新维护预告（2026-04-13） | 官网 news/2666 | 补全上个版本的结束时间 |
| 「雪凇幽梦」版本更新说明（2026-09-02） | 官网或 TapTap | 重构寻访、赛季更新、多行多段、附带条目 |
| 「晨星于此闪耀」特许寻访说明（2026-08-08） | 官网 news/1165 | 单独公告、版本末结束 |

另外要跑一遍鸣潮和异环现有的日历测试，确认结果不变。

## M4：森空岛（理智、进度、练度、探索、签到）

只有 M0 第 4 项找到了不伪造指纹的路径，才实施本节。

### 凭据

- 路径 A 可用时：登录时顺带执行 `grant(type=0)`，再调用 `generate_cred_by_code`，把 cred 和签名 token 一起加密保存。
- 只有路径 B 可用时：在“社区账号”的终末地一栏增加一个可选的“森空岛凭据”输入框，交互参照B站来源面板输入 `SESSDATA` 的做法。凭据加密保存，页面上说明取得方法和失效后怎样更新。
- 签名 token 过期（响应码约定见 M0 记录）后，用 `/api/v1/auth/refresh` 换新；cred 失效时提示重新填写或重新登录。

### 数据

一次 `card/detail` 调用就能覆盖以下能力。参照异环 `_home_cache` 的做法缓存 30 秒，避免每个能力各请求一次：

| 能力 | 字段 | 模型 |
|---|---|---|
| `STAMINA` | `dungeon.curStamina`、`maxStamina`、`maxTs` | `StaminaInfo`：`expected_full_at` 取 `maxTs`，`updated_at` 取 `currentTs` |
| `PROGRESS` | `dailyMission`、`weeklyMission`、`bpSystem`、`seekSuspicion`、`indieHard` | `ProgressItem` |
| `ROLES` | `chars[]` | `RoleEntry`；精英阶段、潜能、武器放进 `extra` |
| `EXPLORATION` | `domain[]` 的 `levels`、`collections` | `ExplorationData`：地区对应 `country_groups`，区域对应 `areas` |
| `ACCOUNT` | `base.level`、`worldLevel`、`mainMission` | 并入 `AccountInfo.extra` |

帝江号（`spaceShip.rooms`）现在没有对应模型，可以放进 `RESOURCES` 或以后再说。理智的同步是否有延迟未知，概览页先照异环的写法标注“森空岛快照，可能有同步延迟”。提醒引擎的理智规则可以直接复用。

### 签到

- 签到是写操作，不要做成能力轮询。单独做成每日任务：配置 `endfield_sign_in = false`（默认关闭）；每个北京时间日最多执行一次，用类似 `ReminderDedup` 的表去重；页面提供“立即签到”按钮，请求必须带 `X-Game-Assistant: 1` 头。
- 接口：`POST https://zonai.skland.com/api/v1/game/endfield/attendance`，请求头带 `sk-game-role: 3_{roleId}_{serverId}`。请求体两个参考实现不一致：EndUID 带 `{"uid": roleId, "gameId": "1"}`，endfield_auto_sign 不带请求体，以 M0 实测为准。返回 `code == 0` 表示成功，奖励在 `awardIds` 和 `resourceInfoMap` 中；消息含“请勿重复签到”表示今天已经签过。
- 签到结果写入状态表，在页面上显示。连续失败时可以通过现有推送渠道通知。
- 签到的重置时刻（0 点还是 4 点）未知，实测前先安排在北京时间 04:10 之后执行。

## 文档与收尾

- README：在当前功能表中加入终末地；更新配置表和 B站来源段落。
- 实现完成后新增 `docs/endfield-data.md`，写明数据来源、实测日期和字段含义，格式参考 `docs/nte-data.md`。
- 如果从参考项目移植了代码，要在 `THIRD_PARTY_NOTICES.md` 中补充说明：EndUID 是 GPL-3.0，与本项目一致；bhaoo/endfield-gacha 是 MIT。只参考协议事实时不需要。
- 在 `CHANGELOG.md` 增加条目。
- 验收：后端 `pytest -q` 全部通过，前端 `npm test` 和 `npm run build` 通过；用真实账号跑一遍登录、同步和日历，并把结果写进 `docs/endfield-data.md`。

## 已知版本（整理测试用例用）

| 版本 | 更新日期 | 全文来源 |
|---|---|---|
| 公测 | 2026-01-22 | 官网 news/1188（「熔火灼痕」特许寻访说明） |
| 「新潮起，故渊离」 | 2026-03-12 | 官网 news/6003 |
| 「春晓时」 | 2026-04-17 | B站 opus 1192064737057177641；预告见官网 news/2666 |
| 「寻遗散记」 | 2026-06-05 | 官网 news/0439 |
| 「向渊行」 | 2026-07-16 | 官网 news/9335 |
| 「雪凇幽梦」 | 2026-09-02 | TapTap 论坛上的同文公告；预告发布于 2026-08-31 |

## 实测记录

M0 完成后在这里填写：日期、结论、原始返回（去掉 token 和手机号）。

| 项目 | 日期 | 结果 |
|---|---|---|
| 通行证短信登录 |  |  |
| 寻访链路与字段 |  |  |
| 最早可查记录日期 |  |  |
| 「重构寻访」池类型 |  |  |
| B站全文与过滤结果 |  |  |
| 官网公告数据格式 |  |  |
| 森空岛路径 A |  |  |
| 森空岛路径 B |  |  |
| 空 dId 下 binding、card/detail、签到的结果 |  |  |
