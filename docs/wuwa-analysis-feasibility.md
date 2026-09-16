# 鸣潮保底、评分、配装与伤害计算可行性

调研日期：2026-09-16。本文件是可行性评估，本轮不实现这些计算，也未运行参考仓库代码。

## 保底分析：先解决记录覆盖与导入

官方查询端点为国服 `https://gmserver-api.aki-game2.com/gacha/record/query`；国际服使用 `.net`。请求包含 playerId、serverId、recordId、cardPoolType、languageCode。库街区 b-at 登录并不能替代抽卡记录链接中的 recordId。

本轮抽卡历史的输入路线：
1. 从游戏内唤取历史取得记录链接，粘贴到本机页面；服务端只解析授权参数，向固定官方端点请求，不访问任意用户 URL，不保存链接授权。
2. 导入 WutheringWavesUID 风格的 `{info:{uid,...},list:[...]}` JSON；也兼容可验证归属的标准列表包装。没有记录凭据时，页面保留可用的导入入口，不显示假数据。
3. 返回窗口之外的历史只能从旧导出记录回补。记录时间早并不等于覆盖完整；重复导入去重时仍需保留同一秒抽到同种物品的多次记录。

参考 [WutheringWavesUID 查询](https://github.com/kvcfdd/WutheringWavesUID/blob/1d693a2df0f940824cb34e102cec1cf3b381e70f/WutheringWavesUID/utils/api/requests.py#L646) 和 [导入模型](https://github.com/kvcfdd/WutheringWavesUID/blob/1d693a2df0f940824cb34e102cec1cf3b381e70f/WutheringWavesUID/wutheringwaves_gachalog/model.py)。该版已区分 1—9 类卡池，包括新手、感恩定向和新旅唤取，不能照搬只支持四池的分析器。

后续保底分析可做，但必须额外确认：卡池规则版本、是否共享保底、最后一次相关五星及其前后记录是否连续、当期 UP 名单与定向规则。已观察到的“距上一条五星记录多少抽”不必然等于准确保底；缺记录时应显示无法判定。出金率可按“已导入范围”统计，不能冒充账号终身概率。

## 可复用项目

以下为实际读取源码/许可证时的提交；不是对算法准确性的验收。

| 项目 | 本次提交 / 日期 | 实现与可用部分 | 复用判断 |
| --- | --- | --- | --- |
| [FrequencyManager](https://github.com/Voruzhu/FrequencyManager) | `f585e47` / 2026-08-30 | TypeScript；`shared/calc/optimizer.ts`、伤害计算模块、rotationEngine；支持配装、敌人抗性、防御与流程条件 | 根 LICENSE 为 MIT。优先候选，建议提取纯计算层，不把整个 Electron/React 应用塞进当前 Vue 项目；仍需角色/武器/套装数据映射和公式回归 |
| [EchoScoringSystem](https://github.com/KokoaChino/EchoScoringSystem) | `ab3e062` / 2025-12-23 | Java/SpringCloud + Vue；声骸副词条、角色权重、评分与配置管理 | 根 LICENSE 为 MIT。适合参考评分模型与公式并移植为独立模块；整套微服务对本地工具过重，且角色数据覆盖需重验 |
| [WutheringWavesUID（指定仓库）](https://github.com/kvcfdd/WutheringWavesUID) | `1d693a2` / 2025-11-23 | Python；`utils/damage`、逐角色 damage 脚本、calc_score_script、装备替换比较 | GPL-3.0；技术栈接近，但依赖角色静态数据和机器人上下文，不能仅复制公式就声称支持当前版本全部角色；后续若直接纳入代码要先确定分发方式和许可证处理 |
| [Echo Value Calculator](https://github.com/AstyuteChick/Echo-Value-Calculator) | `cc22ef3` / 2026-09-10 | Python `evc_engine.py`；角色/队伍权重、充能预算、单件及整套分数 | 自定义 EVC License v1.0，限制公开部署、分发等。适合作为算法对照或个人单独使用候选，不能视为 MIT 一样直接打包复用 |
| [wuwa-toolkit](https://github.com/MinhBN-dev/wuwa-toolkit) | `776c172` / 2026-08-10 | FastAPI + React + PostgreSQL；EVC 评分、声骸库、记录导入、套装 | README 明示 EVC 派生，未找到独立 LICENSE 文件；其抽卡服务仅国际服且卡池范围与参考 UID 不同。架构可借鉴，暂不作为直接移植首选 |

许可证依据：[FrequencyManager LICENSE](https://github.com/Voruzhu/FrequencyManager/blob/f585e47/LICENSE)、[EchoScoringSystem LICENSE](https://github.com/KokoaChino/EchoScoringSystem/blob/ab3e062/LICENSE)、[EVC LICENSE](https://github.com/AstyuteChick/Echo-Value-Calculator/blob/cc22ef3/LICENSE)。只记录仓库明示条款，不将“公开源码”等同于无限制复用。

## 当前接口能提供哪些输入

本轮 getRoleDetail 可提供已装备武器、技能等级、共鸣链、声骸主副词条与套装，以及角色面板属性。这足以支撑单角色已装备配置的评分，以及用户指定两套配置的比较。

接口不能据此提供整个声骸背包；全背包自动最优配装需要额外 JSON/截图/OCR 或手动录入。声骸图鉴是收集资料，不能冒充背包库存。

伤害计算还需要：角色基础值与倍率、武器/声骸被动、队伍增益及触发条件、敌人等级和抗性、攻击类型与暴击口径、操作循环。评分权重是模型选择，不是官方评分。公开项目可以减少建模工作，但每个版本仍要校准支持角色，不能仅依据最新提交日期认定数据已更新。

## 建议的后续路线

1. 先验收本轮真实角色/装备输入，建立稳定字段和版本标记。
2. 单件及整套评分先做有解释的权重模型，公开各词条贡献；将 EVC 作为对照，不未经处理直接移植受限代码。
3. 配装比较先做已保存的两套配置、固定同一角色和敌人的比较；全背包枚举作为独立后续范围。
4. 优先对 FrequencyManager 的纯计算层做小型适配试验，用几个已知配置交叉验算，再决定采用 TypeScript 子模块还是移植 Python。
5. 保底规则待导入覆盖与卡池元数据完整后再实现。当前版本只交付抽卡历史和范围内出金统计。
