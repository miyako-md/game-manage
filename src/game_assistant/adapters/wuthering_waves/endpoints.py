# 库街区 APP 端接口。来源与校准基准：
#   https://github.com/TomyJan/Kuro-API-Collection （README 与 PARAMS.md）
# 若上游调整路径/参数，只改本文件。
#
# Task 11 Step 5 校准结论（2026-09-12 在线核对）：
# ① BASE=https://api.kurobbs.com 已确认（collection 的 API/forum/list.md、
#    API/gamer/role/list.md 均为此域名）。
# ② ROLE_DATA（/gamer/aki/api/getRoleData）：Kuro-API-Collection 未收录该路径，未能核实。
#    该库收录的鸣潮角色数据端点为 /aki/roleBox/akiBox/baseData（[新]，2025.05.25，
#    body 为 gameId=3 + roleId + serverId，必填请求头 source/token/devCode，其中 devCode
#    "必须但不校验"、可随机生成，version 非必填）；参考实现 waves-plugin 取角色数据用
#    /aki/roleBox/akiBox/roleData（body 同为 roleId/serverId，接口契约不同）。
#    gameId=3 指鸣潮已在 collection 多份文档确认（"固定 鸣潮 = 3"）。
#    本端点按简报保留 userId 形式；若实测失效，应先 POST /gamer/role/list
#    （gameId=3，返回 userId/roleId/serverId 绑定关系）再改走 akiBox 系列。
# ③ ACTIVITY_LIST：初值 /gamer/aki/api/getActivityList 在 collection 中不存在，未核实；
#    已按 waves-plugin（erzaozi/waves-plugin components/Code.js，活跃维护）校准为
#    /forum/companyEvent/findEventList，body 为 gameId=3 + eventType
#    （0=全部，1=活动，2=资讯，3=公告），响应 data.list 含 postId/postTitle/publishTime/coverUrl。
# ④ ANNOUNCEMENT_LIST（/forum/list）：路径已确认（collection API/forum/list.md，
#    POST，token 认证）。文档参数为 forumId/gameId/pageIndex/pageSize/searchType/
#    timeType/topicId（鸣潮 gameId=3；鸣潮已知板块 forumId：推荐=9、天诚茶馆=10、同人=11），
#    故客户端 body 用 pageIndex/pageSize（初稿的 page/limit 系误记）。
#    公告分区 forumId 未被 collection 收录：初值 1602 未核实；waves-plugin 实际以
#    findEventList eventType=3 获取公告。若 1602 实测无效，可改用该方案。
BASE = "https://api.kurobbs.com"
ROLE_DATA = f"{BASE}/gamer/aki/api/getRoleData"
ACTIVITY_LIST = f"{BASE}/forum/companyEvent/findEventList"
ANNOUNCEMENT_LIST = f"{BASE}/forum/list"
