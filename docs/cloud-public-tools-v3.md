# 云端公开工具与成长历史接线 v3

本地服务与响应格式复用，云端路由独立挂载；`public` 指无私人游戏凭据的数据，网站登录仍必需。所有维护路由要求管理员身份及会话 CSRF。未增加本地不存在的审核或地图写接口。

| 本地行为 | 云端对应行为 | 来源与差异处置 | 验证 |
| --- | --- | --- | --- |
| `/api/nte/guides` 目录与 `/sources/{post_id}` 原帖 | GET `/api/public/nte/guides`、`/sources/{post_id}` | 复用固定来源目录、`GuideService`、源指纹及持久缓存；普通用户可读 | 合成目录/原帖/登录测试 |
| 异环原帖刷新 | POST `/api/admin/nte/guides/sources/{post_id}/refresh` | 固定帖子白名单；新增管理员与30秒维护冷却 | 普通用户403、缺CSRF403、旧数据保留 |
| 鸣潮攻略更新读取、搜索、提炼 | GET `/api/public/wuwa/guides/updates`；POST `/api/admin/wuwa/guides/updates` 与 `/extract` | 复用 `GuideUpdates` 和原社区来源。GET只读缓存；查询参数 `character_id/name/attribute`，提炼另有 `post_id`。审核结果仍来自版本化目录与匹配源指纹，不新增运行时审核写路由 | 缓存读取、权限、搜索失败保留候选 |
| 鸣潮逆境深塔攻略 | GET `/api/public/wuwa/guides/tower`；POST `/api/admin/wuwa/guides/tower/check` | `TowerGuides` 匿名检索库街区每期阵容帖，每期一帖，白名单作者优先，其余标“待校对”；读取到期（当期缺失 6 小时、否则 24 小时）时后台检查一次；失败保留上次结果。前端以人工校对的静态条目为准，自动条目只补缺期 | 缓存读取、权限、30 秒冷却、搜索失败保留结果 |
| 终末地公开资讯/地图/点位详情 | GET `/api/public/endfield/public`、`/map`、`/map/marks/{mark_id}`；POST `/api/admin/endfield/public/refresh` | 复用官网、官方地图及 `EndfieldPublicService`，保留 `map_id/level_id/type_id/q/offset/limit` 与详情 `map_id` 参数；资料库暂不可读取状态原样保留 | 合成公告、地图、详情、参数验证 |
| 鸣潮从现存快照回补成长历史 | POST `/api/accounts/{account_id}/roles/{role_id}/wuwa/history/backfill`，JSON `{}` | 原本云端只有政策声明，现挂载。仅本人鸣潮库街区作用域与当前授权版本的 `combat/roles` 快照；不接收路径或身份参数，保留 `complete:false` | 两网站用户相同上游UID隔离、CSRF、当前版本、重复回补 |

公开终末地请求增加全应用每分钟32次上游请求预算、最多3条并发上游请求、失败来源60秒冷却及最多128条失败记录。读取超时45秒，超时后禁用该请求的网络访问，使用原服务展示持久化旧数据并标注来源错误；缓存呈现额外最多1秒，锁仍不可用则返回503且保留数据库。异环继续使用每帖30秒来源冷却；管理员维护按功能30秒冷却。成功缓存读取不消耗上游预算。

`public.nte-guides.sqlite3`、`public.wuwa-guides.sqlite3` 新增到备份精确文件清单；终末地公开缓存已有清单项。备份格式及schema版本不变，旧备份不要求包含这两个文件。恢复仍核验原清单、文件摘要与数据库完整性。

本次验证只使用合成账号、合成快照、HTTP模拟来源和临时文件，包含应用关闭/重入与新增缓存备份恢复。真实上游字段与线上读取仍待实际验收；未读取私人配置、未发真实上游请求、未部署。
