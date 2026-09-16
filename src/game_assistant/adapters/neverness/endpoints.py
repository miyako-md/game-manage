# 异环（NTE / Neverness to Everness）塔吉多社区接口端点。
# API 事实全部取自参考项目 github.com/tyql688/NTEUID 公开源码（逐字引用），
# 2026-09-14 已以真实登录态校准私人数据结构，映射见 parse.py/data_models.py。
# 已知事实（Phase 2 校准时以本文件头注释为准逐条核对）：
# ① BASE=https://bbs-api.tajiduo.com；异环 gameId="1289"；塔吉多社区 id="2"。
# ② DS 签名（每个鉴权请求）：时间戳 int(time.time()) + 8 位随机 nonce（字母数字），
#    md5(时间戳 + nonce + "1.2.4" + "pUds3dfMkl")，头 "ds": "{ts},{nonce},{md5hex}"。
# ③ 默认头：User-Agent: okhttp/4.12.0、platform: android、deviceid（随机 UUID）、
#    appversion: 1.2.4、uid: "0"、authorization: <access_token>（鉴权请求）。
# ④ token 刷新：POST /usercenter/api/refreshToken，头 authorization=<refresh_token>，
#    无 body；返回新 access/refresh 对。
# ⑤ HTTP 401/402/403 = 会话失效；登录服务尝试续期，失败后在页面重新登录。
# ⑥ 官方公告走匿名 Web 客户端（UA Mozilla/5.0，无 DS 签名/authorization）：
#    - GET /apihub/wapi/getAllCommunity → 社区列表（异环社区 id=2 及其栏目）；
#    - GET /bbs/wapi/getOfficialPostList?columnId=<栏目id>&count=<n>
#      （"官方资讯"栏目的 columnId 通过社区数据定位，见 tajiduo.py 解析器）。
# ⑥' 2026-09-13 匿名实测校准（本机在线探针，后续联调以此为基线）：
#    - getAllCommunity：code=0/msg=ok/ok=true，data 直接是社区数组（非 data.list）；
#      异环社区 {"id": 2, "name": "异环", "gameId": 1289, "columns": [...]}，
#      栏目含 columnName/columnId→id/showType："官方资讯" id=4 (showType=3)、
#      "攻略互助" id=10、"同人二创" id=8、"综合闲聊" id=2；
#    - getOfficialPostList：columnId=4&count=5 → code=0，data = {column,
#      hasMore, page, posts:[...]}；post 实测键 subject（标题）/createTime
#      （毫秒时间戳）/postId（int）/content/type=3/uid/postStat；
#      version/officialType 传空串被拒（code=6 NumberFormatException，
#      officialType 需 int）——仅传 columnId+count（officialType=1 亦 200）。
# ⑦ 需鉴权端点（GET）：
#    - /usercenter/api/getUserFullInfo
#    - /usercenter/api/v2/getGameRoles?gameId=1289
#    - /apihub/api/getGameRecordCard?uid=<uid>
#    - /apihub/awapi/yh/roleHome?roleId=<rid>
#    - /apihub/awapi/yh/characters?roleId=<rid>
#    - /apihub/awapi/yh/achieveProgress?roleId=<rid>
#    - /apihub/awapi/yh/areaProgress?roleId=<rid>
#    - /apihub/awapi/yh/realestate?roleId=<rid>
#    - /apihub/awapi/yh/vehicles?roleId=<rid>
#    - /apihub/awapi/yh/gacha
# ⑧ roleHome 已包含 staminaValue/staminaMaxValue 与都市活力；无需独立体力端点。
#    当前无结构化活动日历；沿用手填和公告扫描。
BASE = "https://bbs-api.tajiduo.com"
GAME_ID = "1289"
COMMUNITY_ID = "2"
APP_VERSION = "1.2.4"

# ⑥ 官方公告（匿名 Web 客户端）
GET_ALL_COMMUNITY = f"{BASE}/apihub/wapi/getAllCommunity"
OFFICIAL_POST_LIST = f"{BASE}/bbs/wapi/getOfficialPostList"
# 帖子详情（匿名 GET，postId 参数；code=0 成功）：data.post.content 为正文
# （HTML 或明文），活动日历从版本公告正文解析用（2026-09-13 实测端点形状）
GET_POST_FULL = f"{BASE}/bbs/wapi/getPostFull"

# ④⑦ usercenter / apihub（鉴权客户端）
REFRESH_TOKEN = f"{BASE}/usercenter/api/refreshToken"
GET_USER_FULL_INFO = f"{BASE}/usercenter/api/getUserFullInfo"
GET_GAME_ROLES = f"{BASE}/usercenter/api/v2/getGameRoles"
GET_GAME_RECORD_CARD = f"{BASE}/apihub/api/getGameRecordCard"

# ⑦ yh 系列（角色面板/进度/资产，鉴权客户端）
YH_BASE = f"{BASE}/apihub/awapi/yh"
ROLE_HOME = f"{YH_BASE}/roleHome"
CHARACTERS = f"{YH_BASE}/characters"
ACHIEVE_PROGRESS = f"{YH_BASE}/achieveProgress"
AREA_PROGRESS = f"{YH_BASE}/areaProgress"
REALESTATE = f"{YH_BASE}/realestate"
VEHICLES = f"{YH_BASE}/vehicles"
GACHA = f"{YH_BASE}/gacha"
