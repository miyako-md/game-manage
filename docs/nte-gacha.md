# 异环逐抽账本与保底说明

这是本机逐抽文件导入账本。塔吉多的抽卡统计仍由原账号卡展示；统计中的总抽数、S 结果和平均值不会被反推成逐抽记录。新账本不会自动启动抓包、安装驱动、读取游戏凭据或请求未知私人接口。

## 当前支持与数据获取

支持 `Golumpa/nte-exporter` 的 `nte-history-export` v1 JSON，以及本项目自己的 `game-assistant-nte-gacha` v1 JSON 归档。导入前先预览、确认归属与覆盖边界，再写入；选项或文件变化后须重新预览。文件缺少 `user_uid` 时须明确确认归属，有 UID 但与当前登录角色不同则直接拒绝。

上游导出器通过游戏历史通信生成逐条 JSON，须由用户自行获取文件。它需要用户在游戏内从最新历史页向下翻阅，可能缺页、仅含部分历史或截断最老十连。其区域映射目前以国际服为主，国服兼容性尚未在本项目实测。没有确认可复用的国内官方全历史 HTTP 接口或游戏日志 URL 提取方式，因此本功能不提供“一键自动全量同步”的承诺。

国内开源 `wzyboy/nte-dice-analysis` 能从简体中文历史截图生成 OCR JSON 和 XLSX，但其字段、页内顺序和置信度不等同于本项目支持的流水规范；当前不直接接受其数组文件。需要单独转换并保留识别与覆盖校验后再接入，不能将 OCR 行直接当作已验证官方流水。

## 界面上数字的含义

- `exact`：在用户确认最新、连续的导入段中，找到最近一次有效 S 奖励重置点，且该段没有来源警告、序号缺口或已知账本记录缺失。准确性依据是导入数据及用户确认，不是官方实时状态。
- `lower_bound`：最新连续段中尚未找到重置点，当前只能说至少已累计 N 抽。
- `unknown`：没有最新/连续确认，存在缺页或未知记录语义，或卡池规则无法判断。不会以 0 代替未知。

角色棋盘只将 `result_type=dice` 计为投掷；`points_gift`、`chase_reward` 和规范中的 `sleeping_land` 行保留在历史内，但不计数也不重置角色保底。只有 S 级 `character` 行能重置角色计数，S 级皮肤或物品不会重置。弧盘只接受 `source_type=miracle_box` 对应的逐条结果，按 S 级 `arc` 重置。其计数表示“距任意 S 弧盘”，不表示“距当期限定 UP”；目前没有实现弧盘 UP 追踪。Mystery Box 缺轮换身份，暂不计算精确保底。

同秒记录使用 `timestamp_group_ordinal`，0 表示该秒中最新记录。总排序是时间降序、同秒序号升序，不按奖励名称或随机 UID 排序。奖励数量不等于抽数。无法识别的结果类型、奖励类型、品质，以及非正常骰子值，均阻断对应垫抽的精确结论。

`as_of` 与 `latest_record_at` 是源文件最新记录的时间原文；不推测其时区，不等于导出时间或现在。`confirmed_at` 是用户确认覆盖的 UTC 时间；`imported_at` 是对应原始导入段的 UTC 时间。归档迁移保留原有覆盖边界与时间；重新导入时勾选选项不会把归档中的未知覆盖提升为准确。

硬保底规则不内置未验证的国服数值。用户可明确配置 `s_hard_pity`、`reset_reward_type` 和依据说明，标为 `user_configured`。仅精确垫抽且不与规则冲突时，返回 `hard_pity_remaining`。没有规则时返回 null 和 `hard_pity_rule` 缺失说明。用户设置不是官方认证；该功能不声明“下次必出当期 UP”。规则随本项目归档导出，迁移时先在预览中展示；与目的账本规则冲突则整批拒绝。

## API

安装入口：`install_nte_gacha_routes(app, settings)`。角色身份每次从 `app.state.settings.nte_role_id` 读取，无身份返回 409。数据保存为 `settings.db_path` 相邻的 `.gacha.sqlite3` 文件，按角色逻辑隔离。源 `server_id` / `account_region` 存在时保存；同角色提供相冲突的服务器或地区时拒绝合并。缺少地区信息不会被猜测为国服，也无法凭空验证服务器。

所有接口要求允许列表中的本机 Host，带 Origin 时也须在允许列表。写请求必须包含 `X-Game-Assistant: 1`。请求实际读取上限为 8 MiB，单文件最多 50000 行，以先到达的限制为准；不依赖 Content-Length。错误消息不包含原始记录、凭据或请求内容，响应禁止缓存。

| 接口 | 输入 | 返回 |
|---|---|---|
| GET `/api/nte/gacha/summary` | 无 | `role_id,total_records,pools,missing_requirements` |
| GET `/api/nte/gacha/records` | `pool_id?`, `limit=100`（1–1000）, `offset=0` | `role_id,total,records` |
| GET `/api/nte/gacha/export` | `pool_id?`, `offset?`, `limit?` | 可重新导入的 v1 归档下载；分段时附 `export_page` |
| POST `/api/nte/gacha/preview` | 下方请求对象 | `preview_id,record_count,new_records,duplicates,pools,warnings,source_metadata,imported_rules,identity_confirmation_required,missing_requirements` |
| POST `/api/nte/gacha/import` | 同预览对象，另加 `preview_id` | `imported,duplicates,summary` |
| GET `/api/nte/gacha/rules` | 无 | `rules` 数组 |
| POST `/api/nte/gacha/rules` | 下方规则对象 | 保存后的规则，含 `basis=user_configured` |

```json
{
  "document": {"format": "nte-history-export", "format_version": 1},
  "latest_confirmed": false,
  "continuity_confirmed": false,
  "identity_confirmed": false
}
```

上例 document 仅示意格式字段，真正导入必须包含身份或归属确认、banner 和非空 records。latest/continuity 的确认不能消除来源警告、skipped_records、pages_seen 缺页、序号缺口或账本中已知缺失的行。`preview_id` 对文件、角色和全部确认选项做 HMAC 绑定；进程重启后须重新预览。预览不写流水，提交在单事务内重新校验冲突。重复导入去重，同键内容冲突则整批回滚。

### 累计账本的分段备份

省略 offset/limit 时，小账本完整导出；如果累计超过 50000 行、覆盖引用上限或文件字节上限，返回 413 并提示分段，避免生成无法重新导入的归档。无记录时返回 409。

例如 `GET /api/nte/gacha/export?offset=0&limit=2000`，返回归档和 `export_page:{offset,limit,total,next_offset}`。limit 是实际返回条数；如果记录或边界信息较大，服务端自动减小条数，保证紧凑 UTF-8 JSON 小于 8 MiB 并留出导入请求封装余量。继续使用 next_offset 下载，直到它为 null；不能假定每页固定为请求条数。分段期间请暂停继续导入，避免账本顺序变化。每个文件都可使用同一预览/导入流程恢复。

分段是传输切片，不能代表游戏来源的连续扫描。部分导出的覆盖边界会保守设置为未确认，并附 `ARCHIVE_SEGMENTED`；即便所有分段恢复完毕、用户勾选确认，仍不会自动将其提升为精确保底。流水可以完整恢复，保底保持未知；需要后续真正覆盖最新连续段的原始导出补足证明。分段会合并重复来源警告；超过 1000 个诊断代码时保留前 1000 个并加 `SOURCE_WARNING_TRUNCATED`，不会消除未知状态。完整小账本归档仍保留原始覆盖等级。

```json
{
  "pool_id": "Lottery_LimitedCharacter",
  "s_hard_pity": 90,
  "reset_reward_type": "character",
  "source_note": "用户查阅当前游戏内规则后填写，示例不代表已验证数值",
  "confirmed": true
}
```

规范记录保留 `uid,pool_group_id,timestamp,timestamp_group_ordinal,reward_id,reward_name,reward_type,reward_rank,result_type,roll_result,quantity,source_type`。未知 quantity 保留 null，不置 0。必需 ID/顺序/时间缺失时拒绝整个文件。唯一键为 `(role,pool,uid)`；uid 是导出器生成的行标识，非服务端原始抽取 ID。

本项目归档额外包含 `coverage` 数组，每段有 `pool_id,record_uids,latest_confirmed,continuity_confirmed,basis,as_of,latest_record_at,confirmed_at,imported_at,warnings`；每行必须属于至少一个边界段，不能将多个不连续段简单拼接后提升覆盖等级。另保存明确用户配置的 rules 与来源地区元数据。任意第三方声明的覆盖和规则仍属于导入证据，不是官方签名证明。不会保存原始网络包、认证字段或整个未知 JSON 对象。

来源 warnings 保留稳定诊断代码；非代码自由文本被归一为 `SOURCE_WARNING`，避免回显上游可能附带的路径或凭据，但仍阻断精确值。常见 missing_requirements：`latest_records_confirmation`、`continuous_records_confirmation`、`resolve_source_gaps`、`resolve_record_order`、`known_records_missing_from_segment`、`identify_pull_reward_semantics`、`rotation_and_reset_rules`、`hard_pity_rule`、`rule_record_conflict`。

## 公开依据与验证边界

- [NTEUID gacha_service](https://github.com/tyql688/NTEUID/blob/main/NTEUID/nte_gacha/gacha_service.py) 和 [adapters](https://github.com/tyql688/NTEUID/blob/main/NTEUID/nte_gacha/adapters.py)：社区汇总与 S 结果适配。
- [nte-exporter 格式](https://github.com/Golumpa/nte-exporter/blob/main/docs/export-format.md)、[协议](https://github.com/Golumpa/nte-exporter/blob/main/docs/packet-format.md)、[限制](https://github.com/Golumpa/nte-exporter/blob/main/docs/limitations.md)：逐条导出、池分组、同秒序号、分页缺口。
- [exporter JSON 源码](https://github.com/Golumpa/nte-exporter/blob/main/src/nte_history_exporter/export/json_export.py) 和 [protocol](https://github.com/Golumpa/nte-exporter/blob/main/src/nte_history_exporter/decoder/protocol.py)：`points_gift` 与 `chase_reward` 的真实输出；后者对应 source flag -4 的额外奖励。
- [国内 OCR 项目](https://github.com/wzyboy/nte-dice-analysis)、[计数逻辑](https://github.com/wzyboy/nte-dice-analysis/blob/master/src/nte_dice_analysis/export_records.py)：集点赠礼/沉眠地不计抽数，区分角色 S 与其它 S。
- [国际服官方限定棋盘公告](https://nte.perfectworld.com/en/article/news/gameevent/20260603/262503.html)：限定棋盘共享保底、70 次变格、90 次保证角色。这是国际服公告，不自动用作国服全部池规则。
- [国服制作组通讯](https://yh.wanmei.com/news/gamebroad/20260428/261946.html)：弧盘 6 次研募保底相关修复；不足以证明全部 UP、跨池与周期规则。

专项回归使用临时 SQLite，覆盖真实导出字段形状、同秒排序、赠礼/S皮肤、未知品质、上下界、源缺页、归档恢复、规则与地区冲突、账号切换、提交阶段原子回滚、5 万行规模、实际 8 MiB 流限制和本机请求保护。没有进行真实账号历史导入、国服抓包兼容或服务器保留期限验证。
