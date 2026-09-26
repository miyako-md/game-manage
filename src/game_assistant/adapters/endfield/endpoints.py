# 明日方舟：终末地（官服）接口端点。
# 协议事实取自公开源码，未经本项目实测（见 docs/endfield-implementation-guide.md 的 M0）：
# - github.com/Loping151/EndUID 7781451（2026-09-23）utils/api/api.py、requests.py、end_gacha/；
# - github.com/bhaoo/endfield-gacha 72c526d（2026-08-23）app/composables/gacha/useGachaAuth.ts、
#   app/components/AddAccount.vue、app/types/gacha.d.ts。
# ① 鹰角通行证（as.hypergryph.com）与账号绑定（binding-api-account-prod）响应为
#    {status, msg, data}，status=0 成功；寻访记录（ef-webview）响应为 {code, msg, data}，code=0 成功。
# ② 短信登录：send_phone_code {phone, type:1} → token_by_phone_code {phone, code} → data.token
#    （通行证 token，无续期接口）。
# ③ 寻访链路：grant {token, appCode:GACHA_APP_CODE, type:1} → data.token（授权 token）；
#    binding_list?token=&appCode=endfield → data.list[].bindingList[].{uid, isOfficial, roles[]}；
#    u8_token_by_uid {uid, token} → data.token（u8_token，只在内存中使用）。
# ④ 寻访记录：record/char?token=&server_id=&pool_type=&lang=[&seq_id=]，每页 5 条，
#    data={list, hasMore}，按上一页最后一条 seqId 翻页；武器先取 record/weapon/pool 池列表，
#    再按 pool_id 请求 record/weapon。社区工具称官方只回溯约 90 天。
# ⑤ 以上链路均不使用森空岛与数美设备指纹（dId）。
HG_ACCOUNT = "https://as.hypergryph.com"
HG_BINDING = "https://binding-api-account-prod.hypergryph.com"
EF_WEBVIEW = "https://ef-webview.hypergryph.com"

SEND_PHONE_CODE = f"{HG_ACCOUNT}/general/v1/send_phone_code"
TOKEN_BY_PHONE_CODE = f"{HG_ACCOUNT}/user/auth/v1/token_by_phone_code"
OAUTH_GRANT = f"{HG_ACCOUNT}/user/oauth2/v2/grant"
BINDING_LIST = f"{HG_BINDING}/account/binding/v1/binding_list"
U8_TOKEN_BY_UID = f"{HG_BINDING}/account/binding/v1/u8_token_by_uid"

CHAR_RECORD = f"{EF_WEBVIEW}/api/record/char"
WEAPON_POOLS = f"{EF_WEBVIEW}/api/record/weapon/pool"
WEAPON_RECORD = f"{EF_WEBVIEW}/api/record/weapon"

# 公开协议常量（寻访记录授权的 appCode），不是用户凭据。
GACHA_APP_CODE = "be36d44aa36bfb5b"
BINDING_APP_CODE = "endfield"
OFFICIAL_SERVER_ID = "1"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")

# 角色寻访池类型（record/char 的 pool_type）。新卡池可能带来新类型，未知类型不会被静默丢弃：
# 同步只能查询已知类型，因此遇到新卡池时须在此补充并更新文档。
CHAR_POOL_TYPES = {
    "E_CharacterGachaPoolType_Special": "特许寻访",
    "E_CharacterGachaPoolType_Standard": "基础寻访",
    "E_CharacterGachaPoolType_Beginner": "启程寻访",
    "E_CharacterGachaPoolType_Joint": "辉光庆典",
}
