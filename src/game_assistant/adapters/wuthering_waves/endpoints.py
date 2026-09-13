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
#    {name/cur/total/refreshTimeStamp/expireTimeStamp/status}，另有 hasSignIn/roleName。
#    注意 /aki/roleBox/akiBox/baseData 需 APP 端 token（网页 token 恒 code=10901
#    禁止访问，已实测），不可用，故体力走 widget 端点。
# ⑤ EVENT_LIST（POST /forum/companyEvent/findEventList，form body gameId=3 +
#    eventType，eventType：1=活动 2=资讯 3=公告）实测 200：data.list 含
#    postTitle/publishTime（毫秒时间戳）/postId/coverUrl/firstPublishTime/eventType/id。
# ⑥ forum/list 的鸣潮板块 forumId 9/10/11（推荐/天诚茶馆/同人）为社区板块而非官方
#    公告（实测核对），公告统一走 findEventList eventType=3，forum/list 不再使用。
BASE = "https://api.kurobbs.com"
ROLE_LIST = f"{BASE}/gamer/role/list"
WIDGET_DATA = f"{BASE}/gamer/widget/game3/getData"
EVENT_LIST = f"{BASE}/forum/companyEvent/findEventList"
