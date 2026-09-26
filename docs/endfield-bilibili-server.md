# 终末地 B服接入可行性

调研日期：2026-09-26。本轮只做评估，不改代码。调研环境仍然访问不了鹰角和 B 站的域名，下文的接口事实来自参考项目的源码、README、issue 和公开页面，**都没有实测**。

## 结论

可以做，而且改动不大。

- **登录和寻访记录**：B服玩家先在鹰角网络用户中心的[角色绑定](https://user.hypergryph.com/bindCharacters?game=endfield)页面，把 B服账号绑到鹰角通行证上，这是一次性操作。之后用通行证手机号短信登录，走和官服相同的接口：授权 → `binding_list` → `u8_token_by_uid` → 寻访记录。本工具不需要接触 B 站账号。
- **资讯和日历**：来自同一个 B站官号，不用改。
- **理智、练度和签到**：和官服一样，卡在森空岛的数美设备指纹上。森空岛也支持添加 B服角色（明日方舟有官方答疑，终末地未核实），所以这个问题解决后，B服大概率也能一起用。

建议按下文的方案一做，工作量约 1 天，另需一个 B服账号实测。

## 依据

| 事实 | 来源 |
|---|---|
| B服用户先在用户中心「角色绑定」绑定 B服账号，再用通行证登录同步寻访记录 | [bhaoo/endfield-gacha](https://github.com/bhaoo/endfield-gacha) README 的“Bilibili 渠道服注意”，从 2026-02-01（`22821ca`）起一直保留；该工具声明支持官服、B服和国际服 |
| 这样绑定后，同一通行证的 `binding_list` 会列出 B服角色 | [bhaoo/endfield-gacha#21](https://github.com/bhaoo/endfield-gacha/issues/21)（2026-03-21，转述 B站用户反馈）：“在官网通行证只绑定了舟和终末地的B服账号”，工具列出了正在玩的角色，另外还有一个没有角色的 UID |
| 每个通行证都预分配了一个官服 UID，条目为 `isOfficial: true`、`channelMasterId: 1`、`channelName: "官服"`；没玩过官服时 `roles` 为空 | [NGA tid=46021821](https://bbs.nga.cn/read.php?tid=46021821)（2026-01-19）贴出的 `binding_list` 样例。上面 issue 里那个没有角色的 UID 就是它 |
| 国服寻访记录接口对 B服也传 `server_id=1` | EndUID `7781451` 的 `end_gacha/__init__.py` 导入时固定传 `"1"`，链接里是 `channel=2` 也一样；bhaoo `72c526d` 的 `getEfServerId` 对国服一律返回 `"1"` |
| 游戏内的寻访记录链接用 `channel=2&subChannel=2` 表示 B服 | bhaoo `useGachaAuth.ts` 的 `inferChannelLabel`；EndUID 的 `_parse_gacha_token` |
| B服有 PC 客户端。PC 客户端会把寻访记录页的链接写进 `%USERPROFILE%\AppData\LocalLow\Hypergryph\Endfield\sdklogs\HGWebview.log`，链接里的 token 有时效 | bhaoo 的日志同步从 2026-01-31（`dfcdc05`）起区分官服和 B服两类账号；EndUID 的抽卡帮助页 `templates/end_gacha_help.html` |
| bhaoo 在 2026-03-22 的提交 `08f1d07` 里暂停了日志同步入口，随 v0.5.3 发布，没有说明原因 | [v0.5.3 发布说明](https://github.com/bhaoo/endfield-gacha/releases/tag/0.5.3) |
| 森空岛可以手动添加 B服角色，一个 B服账号只能绑定一个森空岛账号 | [鹰角客服答疑](https://customer-service.hypergryph.com/app/skland/question/ART176759522777671912827866)，内容针对明日方舟；终末地未核实 |

## 方案一（推荐）：通行证绑定 B服账号

用户要做的：

1. 注册或登录鹰角通行证（手机号）。
2. 在用户中心「角色绑定」选择终末地，授权 B 站账号完成绑定。
3. 在本工具的「社区账号」里选择终末地 B服，用通行证手机号短信登录。

需要的改动：

| 位置 | 改动 |
|---|---|
| `adapters/endfield/parse.py` 的 `select_official_role` | 改成按渠道选角色：官服取 `isOfficial` 为 true 的条目，B服取为 false 的条目。是否还要求 `channelMasterId` 为 2，等实测后再定。B服角色先不限制 `serverId`。没有 `roleId` 的条目照旧跳过 |
| 同一文件的 `parse_account` | 按已保存的 `role_id` 在所有渠道里查找，查不到才报“角色已变化” |
| `auth/routes.py`、`auth/service.py`、`auth/providers.py` | 终末地的登录请求带上渠道（官服或 B服）。通行证下两个渠道都有角色时由用户选，不自动猜。选了 B服却没有 B服角色时，提示先去用户中心绑定 |
| `adapters/endfield/hypergryph.py` | 寻访接口照参考工具继续传 `server_id=1` |
| 前端登录面板 | 终末地加“官服 / B服”选择，选 B服时附上用户中心绑定页的链接；账号卡片显示渠道名 |
| 测试 | B服的 `binding_list` 样例（带一个没有角色的官服条目）、两个渠道都有角色时按所选渠道取、已保存的角色查不到 |

寻访账本按 `role_id` 隔离，B服角色不会和官服混在一起。资讯、日历和寻访接口本身都不用改。

## 方案二（备选）：粘贴游戏内寻访记录链接

这个方案给不想绑定通行证的 B服玩家用，官服玩家也能用。

- **做法**：参照鸣潮抽卡链接导入（`wuwa_gacha.py`）。只接受 `ef-webview.hypergryph.com` 的链接，只取 `u8_token`，向固定接口请求，不保存链接和 token。记录要归到哪个角色，需要另外调用 `u8.hypergryph.com/game/role/v1/query_role_list`，从 token 反查 `uid` 和 `roleId`（bhaoo 就是这么做的）。
- **限制**：
  - 链接只出现在 PC 客户端的日志里，手机端没有公开的获取方法。
  - token 有时效，每次同步前都要先在游戏里打开寻访记录页，没法定时自动同步。
- 本工具在本机运行，可以直接读日志文件，省去复制粘贴。但 bhaoo 已经暂停了这条路径，原因不明，所以不建议先做。
- 工作量约 1 到 2 天。

## 不建议的做法

不建议在本工具里做 B 站账号登录，也就是用 B 站游戏 SDK 登录，再拿渠道 token 换 u8_token。这样本工具就得保管 B 站账号凭据，还要模拟游戏客户端的登录流程，风险大、收益小，而方案一已经能满足同样的需求。

## 实测清单（追加到 M0）

需要一个已在用户中心绑定了 B服账号的通行证：

1. 记下 `binding_list` 中 B服条目的 `isOfficial`、`channelMasterId`、`channelName`，以及 `roles[].serverId`、`serverName` 的实际值。
2. 对 B服条目的 `uid` 调用 `u8_token_by_uid`，看能否拿到 token。
3. 用 `record/char` 传 `server_id=1`，看能否取到 B服记录；取不到时改传 `roles[].serverId` 再试。
4. 只玩 B服的通行证，列表里是否确实有一个没有角色的官服条目。
