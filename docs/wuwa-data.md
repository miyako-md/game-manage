# 鸣潮数据来源与刷新

2026-09-15 校准：小组件 `getData` / `refresh` 均曾返回体力 240、单质 415、
活跃度 0、电台 41，而直接读未刷新的角色面板也仍返回旧体力 26。
调用角色面板 `refreshData` 后，体力返回 2、单质 334、深境区 18/36；
随后汇总接口同步为活跃度 100、周本收取次数 3、电台 43、本周经验 1800。
这些是当时的账号观测值，不是固定测试数据或当前值的保证。

## 当前链路

所有下表请求均发向 `https://api.kurobbs.com`。
已登录账号先 POST `/aki/roleBox/akiBox/refreshData`，确认业务码 200 且 `data=true`。
体力每 5 分钟、周期进度每小时采集；手动刷新同时采集全部能力。
同角色、同会话十秒内只复用刷新确认，数据仍重新查询；角色或会话变化立即失效。

| 项目 | 接口及原始字段 | 处理方式 |
| --- | --- | --- |
| 结晶波片 | `/aki/roleBox/akiBox/baseData`：`energy/maxEnergy` | 保留真实零值；字段异常不构造零 |
| 结晶单质 | 同上：`storeEnergy/storeEnergyLimit` | 不沿用小组件旧值，不推测恢复时间 |
| 活跃度 | 同上：`liveness/livenessMaxCount` | 使用刷新后的直接值 |
| 战歌重奏 | 同上：`weeklyInstCount/weeklyInstCountLimit` | 使用上游 `weeklyInstTitle`，不擅自反算剩余次数 |
| 千道门扉 | 同上：`rougeScore/rougeScoreLimit` | 使用上游 `rougeTitle` |
| 逆境深塔 | `/aki/roleBox/akiBox/towerDataDetail`：`difficultyList` | 固定选择 `difficulty=3` 深境区，汇总各塔 `star/maxStar` |
| 深境区周期 | 同上：`seasonEndTime` | 是剩余毫秒数；负数/零/缺失视为过期或异常，不能作为本期成绩发布 |
| 冥歌海墟、终焉矩阵、周度游历、电台等级及本周经验 | `/gamer/widget/game3/getData` 对应对象 | 在角色刷新之后读取；目前仍为上游汇总值，不承诺和游戏零延迟同步 |

刷新失败时保留上次成功快照并报告失败，不自动退回缓存接口冒充新值。
仅配置旧 token、没有 roleBox 会话的历史账号继续兼容原小组件路径；建议通过
页面社区登录取得 roleBox 会话。普通游戏账号、公告、活动日历、角色、探索度及
数据坞本来不使用小组件，接口保持各自的数据来源。

## 验证依据

- 实际账号分别对比小组件、未刷新角色面板、刷新后角色面板及深塔专项数据。
- [WutheringWavesTool 接口定义](https://github.com/leck995/WutheringWavesTool/blob/new-ui/wwt-kuro-api/src/main/java/com/kuro/kujiequ/ApiConfig.java)
- [角色刷新调用](https://github.com/leck995/WutheringWavesTool/blob/new-ui/wwt-kuro-api/src/main/java/com/kuro/kujiequ/api/KujiequUserApi.java)
- 回归覆盖：零值、旧缓存被替换、超载区和深境区区分、剩余毫秒、过期周期、刷新失败、短时刷新合并及切换角色。
