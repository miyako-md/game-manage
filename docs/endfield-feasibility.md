# 明日方舟：终末地接入可行性

调研日期：2026-09-24。本文件对应[需求文档](需求文档.md)“新增游戏流程”第 1 步，即列出信息种类与渠道的对应清单。本轮只做评估，不实现。

调研环境无法访问 `zonai.skland.com`、`endfield.hypergryph.com` 和 `api.bilibili.com`。下文的接口事实来自参考项目源码（已注明提交）和公开公告页面，**都没有实测**。只有“现有日历解析器能否处理终末地公告”这一项，在本地用公告原文的标题和时间行实际跑过。

## 结论

可以接入。按是否要经过森空岛，数据分成两档，第二档要先做一个边界决定：

- **第一档：不经过森空岛，在现有规则内就能做。** 包括鹰角通行证登录、寻访记录自动同步、B站官方动态资讯，以及活动日历（需要新写终末地的解析规则，也可以先手填）。寻访这一项比异环方便：官方有逐抽接口，但社区工具普遍说只能查到约 90 天。
- **第二档：经过森空岛，能拿到看板的核心数据。** 包括理智（相当于体力）、每日活跃、每周任务、协议通行证、干员练度、地区建设与探索、帝江号和签到。社区实现已经成熟，EndUID 在 2026-09-23 还有提交。但现有实现都要**在本地伪造数美设备指纹 `dId`**，这和需求文档里“不破解加密、不绕过反爬的高对抗手段”冲突，需要你决定是否放宽。

游戏背景：2026-01-22 在 PC、iOS、Android、PS5 同步公测。国服分官服（鹰角通行证）和 B服；国际服走 Gryphline/SKPORT，接口域名与国服一一对应。当前版本「雪凇幽梦」于 2026-09-02 更新，版本周期大约 5 到 7 周。

## 信息种类 × 渠道

| 信息类别 | 渠道 | 凭据 | 档 | 备注 |
|---|---|---|---|---|
| 账号（UID、昵称、服务器） | 鹰角 `binding_list` | 通行证 token | 一 | 只有这几项基础信息 |
| 账号详情（权限等级、世界等级、主线进度、干员与武器数量） | 森空岛 `card/detail` 的 `base` | cred + dId | 二 | |
| 理智 | `card/detail` 的 `dungeon`：`curStamina`、`maxStamina`、`maxTs` | cred + dId | 二 | `maxTs` 就是回满时间，可以直接填进 `StaminaInfo.expected_full_at` |
| 周期进度 | `dailyMission` 活跃度、`weeklyMission` 每周任务、`bpSystem` 协议通行证、`seekSuspicion` 蚀像寻遗、`indieHard` 影拓丰碑 | cred + dId | 二 | 转成 `ProgressItem` |
| 干员练度 | `chars[]`：等级、精英阶段、潜能、技能、装备、武器与基质 | cred + dId | 二 | 转成 `RoleEntry` |
| 地区建设与探索 | `domain[]`：据点等级与资金、各区域收集进度 | cred + dId | 二 | 转成 `ExplorationData` |
| 帝江号 | `spaceShip.rooms[]` | cred + dId | 二 | 现在没有对应模型 |
| 危机合约、战争回响、影拓丰碑详情 | `card/crisis-contract`、`card/war-echoes`、`card/indie-hard` | cred + dId | 二 | 可选 |
| 寻访记录 | `ef-webview.hypergryph.com/api/record/*` | 通行证 token 换 u8_token | 一 | 官服可用；B服可能要粘贴游戏内的记录链接，未实测 |
| 公告与资讯 | B站官号 UID `1265652806`、官网 `endfield.hypergryph.com/news`、森空岛官方栏目 | 无 | 一 | 森空岛公开接口从 2026-08-19 起也校验 dId |
| 活动日历 | 官方版本说明全文、森空岛 Wiki 结构化接口、手填 | 无或 dId | 一/二 | 见后文 |
| 每日签到 | `POST /api/v1/game/endfield/attendance` | cred + dId | 二 | 属于写操作，本项目目前没有签到功能 |

## 登录（第一档）

两档都从鹰角通行证 token 开始，参考 EndUID 的 `utils/api/api.py` 和 `requests.py`：

- 短信登录：`POST as.hypergryph.com/general/v1/send_phone_code`，请求体 `{phone, type:1}`；再 `POST /user/auth/v1/token_by_phone_code`，请求体 `{phone, code}`，从 `data.token` 取得 token。参考实现里没有人机验证步骤，触发风控时会不会弹极验还不清楚。
- 扫码登录：`POST /general/v1/gen_scan/login` 得到 `scanId`，页面上显示内容为 `hypergryph://scan_login?scanId=…` 的二维码，用森空岛 App 扫描；接着轮询 `GET /general/v1/scan_status` 得到 `scanCode`，再用 `POST /user/auth/v1/token_by_scan_code` 换 token。这样不用收短信，但前端要加二维码组件。
- 以上请求都不带 `dId`。token 的有效期和失效码没有文档，需要实测。这里也没有异环那样的 refresh token，过期后按鸣潮、异环现有做法，提示用户重新登录。

凭据照旧用 `auth/store.py` 加密保存。`auth/service.py` 里的 `GAMES`、`FIELDS`、`_configured` 和续期分支都要加上终末地。

## 寻访记录（第一档，建议优先做）

完整链路参考 bhaoo/endfield-gacha 的 `useGachaAuth.ts`、`AddAccount.vue` 和 EndUID 的 `requests.py`：

1. `POST as.hypergryph.com/user/oauth2/v2/grant`，请求体 `{token, appCode:"be36d44aa36bfb5b", type:1}`，返回授权 token。
2. `GET binding-api-account-prod.hypergryph.com/account/binding/v1/binding_list?token=…&appCode=endfield`，得到 `uid` 和角色信息（`roleId`、`serverId`、昵称）。
3. `POST …/account/binding/v1/u8_token_by_uid`，请求体 `{uid, token}`，返回 `u8_token`。
4. 角色池：`GET ef-webview.hypergryph.com/api/record/char?token=&server_id=1&pool_type=&lang=zh-cn[&seq_id=]`。武器池要先用 `/api/record/weapon/pool` 取池列表，再按 `pool_id` 请求 `/api/record/weapon`。

已知的事实和限制：

- 每页 5 条，用上一页最后一条的 `seqId` 翻页，所以记录可以直接按 `seqId` 去重。
- 社区工具普遍说官方只能查到约 90 天（例如[终末地抽卡助手](https://yukiovo.com/420.html)写着“突破官方九十天限制”），本轮没有实测。所以本地账本要长期累积，同步间隔必须远小于 90 天；窗口之外的历史只能靠以前的导出补回。
- 已知的角色池类型有 `E_CharacterGachaPoolType_Special`（特许）、`Standard`（基础）、`Beginner`（启程）和 `Joint`（辉光庆典）。EndUID 到 2026-05-14 才补上 `Joint`，在那之前它不会去查这个池。今天（2026-09-24）开启的「重构寻访」按公告是一种新的寻访类型，接口里是否对应新的枚举值还不知道。解析时遇到不认识的池类型必须标成未知，不能静默丢掉。
- 请求之间要留间隔，参考工具就是为了防风控加了延迟。增量同步时，连续遇到已知的 `seqId` 就停止。token 需要做 URL 编码。
- B服：参考工具根据记录链接里的 `channel=2&subChannel=2` 判断是 B服。B服能不能走通行证这条链路还不知道；如果不能，就和[鸣潮的抽卡记录链接](wuwa-analysis-feasibility.md)一样，让用户粘贴游戏内的寻访记录链接。

和异环对比：异环没有官方逐抽接口，只能导入文件；终末地可以自动同步。`nte_gacha.py` 里的 `seqId` 去重、分池存储，以及 exact / lower_bound / unknown 三种保底口径，都可以沿用设计思路，但数据源不同，存储键和路由要单独做。

## 森空岛与设备指纹（第二档，需要决定）

链路参考 EndUID 的 `requests.py`、`ds.py` 和 TNXG/skland-api 的 `src/hg/skland.ts`：

1. `POST as.hypergryph.com/user/oauth2/v2/grant`，请求体 `{token, appCode:"4ca99fa6b56cc2ba", type:0}`，返回 `data.code`。
2. `POST zonai.skland.com/api/v1/user/auth/generate_cred_by_code`，请求体 `{kind:1, code}`，返回 `cred`、用作签名密钥的 `token`，以及 `userId`。
3. 签名算法：`sign = MD5(HMAC-SHA256(token, path + query或body + timestamp + JSON{platform,timestamp,dId,vName}))`。请求头带 `cred`、`sign`、`platform:3`、`timestamp`、`dId`、`vName`。签名 token 过期后，用只带 cred 的 `GET /api/v1/auth/refresh` 换新。
4. `GET /api/v1/game/player/binding` 取出 `appCode=endfield` 的 `roleId` 和 `serverId`；再请求 `GET /api/v1/game/endfield/card/detail?roleId=&serverId=&userId=`，请求头带 `sk-game-role: 3_{roleId}_{serverId}`。上表第二档的字段大多一次就能拿到。

`dId` 的要求在逐步收紧，而且各接口不一样：

- 换 cred：[skyland-auto-sign](https://github.com/zhiquawa/skyland-auto-sign) 记录了 2024-09-10 起登录接口要求 dId。[arknights-mower PR #967](https://github.com/ArkMowers/arknights-mower/pull/967)（2026-09-06，已合并）也说，dId 为空时会被判为“设备信息无效”。
- 公开 Web 接口：EndUID 在 2026-08-27 的提交 `ffe20cd` 里写明，“2026-08-19 起服务端校验 dId，为空返回 10001 设备信息无效”。
- 玩家数据：EndUID 从第一版（2026-01-29）起请求 card/detail 就带 dId，现在 binding 等玩家接口也都带。反例是 TNXG/skland-api（2026-07-13），它换 cred 和请求 card/detail 都不带 dId。这个请求方式现在是否仍然可用，是最值得实测的一项：如果可用，第二档就不再有边界问题。

现有取得 `dId` 的做法有两种：

- EndUID 的 `utils/api/smsdk.py`：按数美 Web SDK 的协议在本地拼一份浏览器指纹（随机 smid、屏幕参数、UA 等），用数美公钥做 RSA 加密，逐字段做 DES 加密，再整体 AES 加密后封装成 `dId`，全程不请求数美服务器。
- Endfield-Gacha-Assistant 和 arknights-mower：把伪造的设备档案提交给 `fp-it.portal101.cn/deviceprofile/v4` 换取 `dId`。mower 会把拿到的 dId 存盘复用。

这两种做法都是复现风控 SDK 的加密协议来伪造设备指纹，正是需求文档排除的“破解加密、绕过反爬的高对抗手段”。现在鸣潮、异环的登录只是生成随机设备 ID、填固定机型字段，没有复现任何风控 SDK。可选的处理方式：

1. **不接森空岛**，只做第一档。代价是拿不到理智（需求文档里的 P0 项）、活跃度和练度。
2. **放宽边界，做成独立的可选模块**：默认关闭（比如 `endfield_skland_enabled = false`）；每次安装只生成并保存一个 dId，不要每次请求都换一份指纹；模块出错不影响第一档；在 README 写清原理和风险。维护成本需要考虑：2026-08-19 这次收紧就让公开接口不带 dId 后无法使用，之后还可能再变。
3. **使用你自己浏览器里的会话**：在自己的浏览器登录 www.skland.com，把 cred、签名 token 和浏览器生成的 dId 填进本工具。这样 dId 由官方 SDK 生成，但需要手动抓取，不符合“正常使用无需抓包”的约定；换一个客户端使用这些值能否通过校验，也没有验证过。

账号安全方面，没有查到有人因为只读查询被处罚的公开记录，但这不能说明没有风险。签到是写操作，无论选哪种都建议默认关闭。

## 公告与活动日历

资讯：B站官号“明日方舟终末地”的 UID 是 `1265652806`。在 `config.example.toml` 的 `[bilibili_sources]` 里加 `endfield = "1265652806"`，再把它加进 `public_content.MOBILE_GAMES`，资讯流就能沿用现有的采集和过滤。

日历：用「雪凇幽梦」版本更新说明的原文标题和时间行整理了一份样本，在本地跑了现有解析器（官网和 TapTap 发布的全文格式相同）：

- `calendar_from_posts` 返回空。原因是标题为 `「雪凇幽梦」版本更新说明`，既没有 `x.x版本`，也不含“内容说明”或“更新公告”。终末地的版本要改用「版本名」来识别。
- 活动标题的格式是 `1.「冬猎」特许寻访`，鸣潮和异环两个 `_heading` 分支都匹配不上。
- 临时补上这种标题的识别后，16 个编号条目里只有 5 个能拿到起止时间，另外 11 个被丢弃，原因是时间写成了 `2026/09/24 12:00 - 版本更新维护前`、`「雪凇幽梦」版本期间` 或 `于3次「特许寻访」后结束`。「理智补给」分两段，第二段丢失；「丰碑留名·刻影」被算到了「影拓丰碑」名下。
- “版本更新维护前”的具体时刻，要等下一版本的“版本更新维护预告”才知道，比如“计划将于2026年9月2日06:00（UTC+8）开始……停机维护”，通常提前几天发布。在那之前结束时间是未知的。按照现有“不虚构截止时间”的规则，事件要新增一个“相对结束”字段，前端日历也要能显示没有确定结束时间的活动条。
- 本轮能搜到的官号动态有长图形式，版本说明是否以全文发布没能确认。如果只发长图，按现有“不自动 OCR”的规则，日历就应该改以官网全文为主来源。这需要新写官网抓取，目前没有找到公开的 JSON 接口。

其他来源：

- 森空岛 Wiki 的结构化接口 `/web/v1/wiki/activity`、`char-pool`、`weapon-pool`、`banner`（见 EndUID 的 `end_calendar/zonai_client.py`）直接返回起止时间戳，数据质量最好。但它的匿名 token 来自 `/web/v1/auth/refresh`，而这个接口从 2026-08-19 起校验 dId，所以归入第二档。
- 手填：参照 `[[nte_events]]` 增加 `[[endfield_events]]`，成本最低，可以作为兜底。

## 本项目需要改动的地方

- 后端：新增 `adapters/endfield/`，包括接口地址、通行证与寻访客户端、可选的森空岛客户端、解析和适配器；在 `registry.py`、`config.py`（`endfield_enabled` 等）、`config.example.toml` 中注册。
- 能力映射：第一档是 `ACCOUNT`（基础信息）、`GACHA`、`ANNOUNCEMENT`/`NEWS`/`EVENTS`；第二档是 `STAMINA`、`PROGRESS`、`ROLES`、`EXPLORATION`，帝江号可以放进 `RESOURCES` 或新增一个能力。理智回满时间直接取 `maxTs`，提醒引擎的体力规则不用改。
- 登录：`auth/providers.py` 新增通行证短信或扫码的 provider；`auth/service.py` 加入 `GAMES`、`FIELDS` 和失效码处理；前端 `LoginPanel.vue` 加上游戏选项，扫码还要一个二维码组件（新依赖）。
- 寻访：新增本地账本的存储和路由，按角色隔离、按 `seqId` 去重、定时增量同步；前端新增对应面板。
- 日历：在 `sources/public_content.py` 增加终末地分支（版本名、标题格式、相对结束、多段时间）并补测试；也可以先上手填配置。
- 前端：在 `dashboard.js` 的 `GAME_STYLE` 加一项，图标用原创文字（比如“终”），遵守不分发官方图包的约定。标准格式的数据可以直接用现有的 `StaminaCard`、`ProgressCard`、`RoleWallCard`、`ExplorationCard` 显示，定制面板可以以后再做。

## 参考项目

下表是本次读取源码时的提交，不代表接口现在仍然可用。

| 项目 | 提交 / 日期 | 内容 | 复用判断 |
|---|---|---|---|
| [Loping151/EndUID](https://github.com/Loping151/EndUID) | `7781451` / 2026-09-23 | gsuid_core 插件：通行证短信和扫码登录、森空岛签名与 dId、card/detail 的完整字段模型、寻访同步、日历、公告、签到 | GPL-3.0，与本项目一致。它和鸣潮的 WutheringWavesUID、异环的 NTEUID 属于同一类插件，适合作为协议参考；其中 `smsdk.py` 取决于第二档的决定 |
| [bhaoo/endfield-gacha](https://github.com/bhaoo/endfield-gacha) | `72c526d` / 2026-08-23 | Tauri 桌面寻访工具：通行证换 u8_token 的链路、官服/B服/国际服识别、增量同步 | MIT，寻访链路的首选参考 |
| [Thanatosoul/Endfield-Gacha-Assistant](https://github.com/Thanatosoul/Endfield-Gacha-Assistant) | `c6a10b7` / 2026-09-17 | 寻访同步、森空岛签到，dId 从 `fp-it.portal101.cn` 取得 | MIT，只作对照 |
| [TNXG/skland-api](https://github.com/TNXG/skland-api) | `9d5913b` / 2026-07-13 | TypeScript 服务：扫码登录，card/detail 字段的中文含义对照表 | 没有 LICENSE 文件，只参考协议事实，不复制代码 |
| [Entropy-Increase-Team/astrbot_plugin_endfield](https://github.com/Entropy-Increase-Team/astrbot_plugin_endfield) | `41482b7` / 2026-08-24 | 机器人插件，依赖第三方托管的“终末地协议终端”服务 | AGPL-3.0；需要把凭据交给第三方，不符合本机优先的原则，不采用 |
| [AixLnyt/skport-api-docs](https://github.com/AixLnyt/skport-api-docs) | `54fd90c` / 2026-06-18 | 国际服 SKPORT 接口文档 | 没有 LICENSE；接国际服时参考 |

## 需要你确认

1. 你玩的是官服、B服还是国际服？B服的寻访可能只能粘贴链接；国际服要换一套域名。
2. 第二档森空岛选上面三种处理方式中的哪一种？
3. 日历先手填，还是直接投入做官网或B站全文解析？
4. 要不要签到功能？它是写操作。

## 待实测清单

- 通行证短信是否会触发人机验证；token 的有效期和失效码。
- 寻访：官服链路能否跑通，实际能查到多少天，「重构寻访」对应什么池类型，B服是否只能粘贴链接。
- B站官号的版本公告是否发全文。
- 如果做第二档：换 cred、binding、card/detail 现在对 dId 的要求，尤其是 TNXG 那种完全不带 dId 的请求方式能否通过；理智数据是否实时（异环的同类数据有延迟）。

## 建议路线

1. 第一期只做第一档：通行证登录，然后是寻访自动同步和本地账本，再接B站资讯；日历先手填，之后补上终末地解析分支。
2. 第二期根据“需要你确认”第 2 项的结果决定。如果选放宽边界，就做可选的森空岛模块（理智、进度、练度、探索），签到默认关闭。
3. 动手实现前，先在本机按待实测清单逐项验证，把结果补进本文件。
