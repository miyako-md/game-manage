# 库街区接口端点。原初值依据 Kuro-API-Collection（TomyJan）文档，2026-09-13 起以
# 真实账号在线实测为准（首次真实连接校准），以下结论全部实测验证：
# ① BASE=https://api.kurobbs.com 已实测确认。
# ② ROLE_DATA（/gamer/aki/api/getRoleData）实测返回 HTTP 404，接口已死，
#    相关常量与客户端方法已删除，账号信息改走 ROLE_LIST。
# ③ ROLE_LIST（POST /gamer/role/list，form body gameId=3；token 即身份，无需 userId）
#    实测 200：data 为数组，首元素（默认角色 isDefault=true）含 roleId/serverId/
#    roleName/gameLevel（字符串，如 "80"）/activeDay/achievementCount/roleNum/serverName。
# ④ WIDGET_DATA（POST /gamer/widget/game3/getData，form body gameId=3 + roleId +
#    serverId + type=2 + sizeType=1）实测 200：data.energyData =
#    {name/cur/total/refreshTimeStamp/expireTimeStamp/status}，另有 hasSignIn/roleName；
#    data 还含 activityData（版本活动 title/endTime/coreRewards）与 towerData/
#    slashTowerData/weeklyData 等同构进度对象（解析见 widget.py）。
#    baseData 需要下述 roleBox 三件套；不能直接沿用网页 token。
# ⑤ EVENT_LIST（POST /forum/companyEvent/findEventList，form body gameId=3 +
#    eventType，eventType：1=活动 2=资讯 3=公告）实测 200：data.list 含
#    postTitle/publishTime（毫秒时间戳）/postId/coverUrl/firstPublishTime/eventType/id。
# ⑥ forum/list 的鸣潮板块 forumId 9/10/11（推荐/天诚茶馆/同人）为社区板块而非官方
#    公告（实测核对），公告统一走 findEventList eventType=3，forum/list 不再使用。
# ⑦ roleBox 系列（/aki/roleBox/akiBox/*，探索度与数据坞）不走 token 鉴权，而是
#    b-at 头（APP 内 WebView 会话票据，32 位十六进制）+ devCode/did 头三件套，
#    与 ③④⑤ 的 token 鉴权完全不同（头逐字实测见 rolebox_client.py）；
#    响应 data 是 JSON 字符串，需二次解析（解析见 rolebox.py）。
#    实测端点（POST form）：baseData（体力/等级/活跃天数等）、
#    exploreIndex（body 另加 channelId=19&countryCode=1，探索度/残象探寻）、
#    calabashData（数据坞等级/捕获率/声骸收集）、
#    roleData（角色练度墙：data.roleList 46 项，含等级/命链/突破/属性/武器）。
# ⑧ WIDGET_REFRESH（POST /gamer/widget/game3/refresh）实测 200：参数与 getData
#    相同，响应形状一致。2026-09-13 实测对比：getData 返回缓存体力 26/240，
#    refresh 返回 33/240（更新鲜，Kuro-API-Collection 亦注明"refresh 返回的
#    数据更准确点"）。该结论仅是历史观测，2026-09-15 已被新实测修正：
#    已登录账号必须先 roleBox refreshData，再读 baseData / towerDataDetail；
#    小组件 refresh 不能保证触发最新角色数据，现仅供旧 token 配置兼容。
BASE = "https://api.kurobbs.com"
ROLE_LIST = f"{BASE}/gamer/role/list"
WIDGET_DATA = f"{BASE}/gamer/widget/game3/getData"
WIDGET_REFRESH = f"{BASE}/gamer/widget/game3/refresh"
EVENT_LIST = f"{BASE}/forum/companyEvent/findEventList"
# 帖子详情（2026-09-13 实测）：POST form 仅 postId 即可；网页 token 头即可访问；
# data.postDetail.postH5Content 为 H5 HTML 全文，postTitle 为标题（活动日历用）
POST_DETAIL = f"{BASE}/forum/getPostDetail"
ROLEBOX_BASE = f"{BASE}/aki/roleBox/akiBox"
ROLEBOX_BASE_DATA = f"{ROLEBOX_BASE}/baseData"
ROLEBOX_EXPLORE_INDEX = f"{ROLEBOX_BASE}/exploreIndex"
ROLEBOX_CALABASH_DATA = f"{ROLEBOX_BASE}/calabashData"
ROLEBOX_ROLE_DATA = f"{ROLEBOX_BASE}/roleData"
# 2026-09-15 live check: widget refresh stayed at 240 while refreshed roleBox
# baseData returned 2. refreshData returns data=true, not a data object.
ROLEBOX_REFRESH_DATA = f"{ROLEBOX_BASE}/refreshData"
ROLEBOX_TOWER_DETAIL = f"{ROLEBOX_BASE}/towerDataDetail"
