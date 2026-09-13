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
#    注意 /aki/roleBox/akiBox/baseData 需 APP 端 token（网页 token 恒 code=10901
#    禁止访问，已实测），不可用，故体力走 widget 端点。
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
#    calabashData（数据坞等级/捕获率/声骸收集）。
BASE = "https://api.kurobbs.com"
ROLE_LIST = f"{BASE}/gamer/role/list"
WIDGET_DATA = f"{BASE}/gamer/widget/game3/getData"
EVENT_LIST = f"{BASE}/forum/companyEvent/findEventList"
ROLEBOX_BASE = f"{BASE}/aki/roleBox/akiBox"
ROLEBOX_BASE_DATA = f"{ROLEBOX_BASE}/baseData"
ROLEBOX_EXPLORE_INDEX = f"{ROLEBOX_BASE}/exploreIndex"
ROLEBOX_CALABASH_DATA = f"{ROLEBOX_BASE}/calabashData"
