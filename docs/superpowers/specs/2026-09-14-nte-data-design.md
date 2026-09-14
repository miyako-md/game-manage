# 异环数据展示

用户要求参考 NTEUID 和现有鸣潮模块完成异环展示。本轮沿用本地仪表盘及登录模块，新增数据标准化与游戏专属卡片。

## 来源与范围

参考 NTEUID ba7790e13e39f9a825090853498848b51a06c3c9 的 utils/sdk/tajiduo_model.py、tajiduo.py 与 nte_role/nte_gacha 数据用法；不复制其 UI 模板、纹理或自定义绘图资源。头像仅使用官方公共 CDN 地址。

异环能力顺序：account、stamina、roles、progress、exploration、gacha、record、events、announcement。
roleHome 包含体力与日常字段，纠正旧文档“无体力”判断。体力按 5 分钟轮询，其余复用既有频率；同账号 home 查询可复用 30 秒缓存，换账号或 token 不得复用。

## 统一数据契约

除 stamina 继承现有 StaminaInfo 外，其余均为 Pydantic 模型。所有顶层 payload 带 `schema_version: 1`，缺失数字为 null，0 是真实零值。非法顶层结构抛明确解析异常，调度器保留旧快照。前端遇到旧原始 payload 显示“数据格式已更新，请刷新”，不显示假零。

- account: `{schema_version,nickname,level,role_id,server_name,world_level,tycoon_level,active_days,character_count,achievement_count,achievement_total,house_count,house_total,vehicle_count,vehicle_total}`。来自 roleHome：rolename/lev/roleid/servername/worldlevel/tycoonLevel/roleloginDays/charidCnt/achieveProgress/realestate/vehicle。
- stamina: `{schema_version,current,maximum,updated_at,expected_full_at:null,city_current,city_maximum,daily_activity,weekly_remaining}`。current/maximum 来源 staminaValue/staminaMaxValue，缺失不得构造 0；citystaminaValue/citystaminaMaxValue、dayvalue（分母100）、weekcopiesremainCnt（显示剩余，不显示已完成）。不猜恢复时间与重置时间。继承 StaminaInfo 保留通用体力提醒兼容。
- roles: `{schema_version,entries:[{id,name,level,quality,element,awaken_level,mix_level,affinity_exp,icon_url,weapon:{name,level,quality,mix_level}|null,properties:[{name,value}],skills:[{name,level}],city_skills:[{name,level}]}]}`。等级=alev，觉醒=awakenLev，混频=slev，likeabilitylev=羁遇累计经验。品质原值映射 S/A/B/C/N；元素映射魂/光/灵/咒/暗/相，未知显示原文本。角色卡可展开属性、战技、城区技能、弧盘；不显示鸣潮五星/6链/90级满级口径。
- progress: `{schema_version,completed,total,bronze,silver,gold,categories:[{id,name,current,total}]}`。来源 achievementCnt/total、bronzeUmdCnt 等、detail[].progress/total。标题“成就进度”；不计算周期重置。
- exploration: `{schema_version,areas:[{id,name,current,total,details:[{id,name,current,total}]}]}`。来源 areaProgress 列表。progress 是数量，百分比仅在分母>0且分子已知时计算；null 表示未提供/未解锁，不能当0。
- gacha: `{schema_version,role_id,nickname,total_draws,total_s,pools:[{name,total_draws,s_count,average,percentile,guarantee,details:[{item_id,name,pity,obtained_at}]}]}`。来源 gachaDetails：tab/drawCount/rareCount/average/playerOver/m/details。detail rareCount=本次第几抽出S，timeStamp毫秒转UTC+8，time可作日期回退。name 可从当前账号角色/弧盘名称表查找，未命中显示“角色/弧盘 ID”。UI注明“社区统计窗口；仅列已出S明细，不含当前垫抽，不代表完整历史”。不推算当前保底、胜率或长期运气。
- record: `{schema_version,cards:[{game_name,role_id,nickname,level,server_name,url}]}`。getGameRecordCard返回跨游戏列表，只取 gameId=1289 且符合当前已选 roleId 的卡片。bindRoleInfo.account 不输出。标题“社区名片”，不是对局战绩。

## 解析和身份边界

解析函数位于 adapters/neverness/parse.py，模型位于 data_models.py：`parse_account(raw, expected_role_id='')`、`parse_stamina(raw, now, expected_role_id='')`、`parse_roles(raw)`、`parse_progress(raw)`、`parse_exploration(raw)`、`parse_gacha(raw, names=None, expected_role_id='')`、`parse_record(raw, expected_role_id='')`。

raw 为现有客户端返回的 `{code,data}` 包装；data也可为JSON字符串。严格识别公开结构；不采用任意递归字段搜索。公开模型内的可选字段缺失显示未知，非法数值与非有限值不进入百分比或提醒；结构变化不能保存为成功空数据。home/gacha 若返回的 roleid 与当前角色不同必须报错。图片/链接限 http(s)，不允许 javascript/data 链接。

## 验证与非目标

测试公开响应形状、有效空列表、坏结构保留旧快照、缺值与0、null探索、角色切换、跨游戏名片筛选、抽卡出S语义、JSON字符串、缓存隔离、前端展开与旧快照提示。前端构建、浏览器模拟数据检查，并在有异环登录后真实校准。

本轮不开发签到操作、抽卡导入、战斗伤害计算或机器人命令；房产/载具先在账号卡展示数量概览。首次参考检查时异环未登录，不能将模拟测试报告为真实上游通过。
