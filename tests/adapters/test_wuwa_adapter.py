import json

import httpx
import respx

from game_assistant.adapters.wuthering_waves.adapter import WutheringWavesAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability, GameEvent, ProgressItem
from game_assistant.models import CalabashData, ExplorationData

# 实测响应形状（2026-09-13），见 endpoints.py 注释
ROLE_LIST_RAW = {"code": 200, "msg": "success", "data": [{
    "roleId": "100000001", "serverId": "76402e5b20be2c39f095a152090afddc",
    "roleName": "测试漂泊者", "gameLevel": "80", "activeDay": 534,
    "achievementCount": 604, "roleNum": 46, "serverName": "鸣潮",
    "isDefault": True,
}]}
# widget getData 的 data 字段实测形状（activityData + 周期进度，见 widget.py）
WIDGET_RAW = {"code": 200, "msg": "success", "data": {
    "energyData": {"name": "结晶波片", "cur": 180, "total": 240,
                   "refreshTimeStamp": 0, "expireTimeStamp": 0, "status": 0},
    "activityData": {"enabled": True, "title": "身赴三途", "endTime": 1790654399,
                     "coreRewards": [{"name": "若梦仍有回声", "cur": 0, "total": 0,
                                      "status": 0, "refreshTimeStamp": 1790625599}]},
    "towerData": {"name": "逆境深塔·深境区", "cur": 36, "total": 36,
                  "refreshTimeStamp": 1789329600},
    "weeklyData": {"name": "战歌重奏", "cur": 0, "total": 3, "refreshTimeStamp": 0},
    "battlePassData": [{"name": "本周经验", "cur": 8600, "total": 12000,
                        "refreshTimeStamp": 0}],
    "hasSignIn": True, "roleName": "测试漂泊者",
}}
EVENT_RAW = {"code": 200, "msg": "success", "data": {"list": [{
    "id": "100", "postTitle": "2.6版本更新公告", "publishTime": 1789182000000,
    "postId": "9001", "coverUrl": "https://img.kurobbs.com/upload/9001.jpg",
    "firstPublishTime": 1789182000000, "eventType": 3,
}]}}
# 活动日历链路 fixture：公告列表（含干扰帖 + 版本公告）+ 版本公告详情 H5 正文
# （正文行文按 2026-09-13 实测 3.6 公告样本：[名称]类型 行 + ✦活动时间 行）
EVENTS_LIST_RAW = {"code": 200, "msg": "success", "data": {"list": [
    {"id": "101", "postTitle": "维护完成公告", "publishTime": 1789959600000,
     "postId": "9002", "eventType": 3},
    {"id": "100", "postTitle": "「蜃云灯影，凡尘剑心」3.6版本内容说明",
     "publishTime": 1789182000000, "postId": "9001", "eventType": 3},
]}}
EVENTS_LIST_NO_VERSION_RAW = {"code": 200, "msg": "success", "data": {"list": [
    {"id": "101", "postTitle": "维护完成公告", "publishTime": 1789959600000,
     "postId": "9002", "eventType": 3},
]}}
EVENTS_H5_CONTENT = (
    "<p>「蜃云灯影，凡尘剑心」版本活动内容一览</p>"
    "<p>[群声共振模拟域]战斗活动</p>"
    "<p>完成模拟域挑战可获得奖励。</p>"
    "<p>✦活动时间：2026年8月22日10:00&nbsp;~&nbsp;2026年9月29日11:59（服务器时间）</p>"
    "<p>[若梦仍有回声]限时联机战斗活动</p>"
    "<p>联机击败强敌。</p>"
    "<p>✦活动时间：3.6版本更新后 ~ 2026年9月29日03:59（服务器时间）</p>"
    "<p>维护补偿：2026年8月20日06:00 ~ 2026年8月20日12:00（服务器时间）。</p>"
)
EVENTS_POST_DETAIL_RAW = {"code": 200, "msg": "success", "data": {"postDetail": {
    "postId": "9001",
    "postTitle": "「蜃云灯影，凡尘剑心」3.6版本内容说明",
    "postH5Content": EVENTS_H5_CONTENT,
}}}
DETAIL_URL = "https://api.kurobbs.com/forum/getPostDetail"

ROLE_LIST_URL = "https://api.kurobbs.com/gamer/role/list"
WIDGET_URL = "https://api.kurobbs.com/gamer/widget/game3/getData"
WIDGET_REFRESH_URL = "https://api.kurobbs.com/gamer/widget/game3/refresh"
EVENT_URL = "https://api.kurobbs.com/forum/companyEvent/findEventList"
ROLEBOX_BASE_URL = "https://api.kurobbs.com/aki/roleBox/akiBox"

# roleBox 响应 data 是 JSON 字符串（实测形状，2026-09-13 完整响应校准），
# 需二次解析；exploreIndex 为 exploreList 国家分组 + detectionInfoList 结构
EXPLORE_RAW = {"code": 200, "msg": "success", "data": json.dumps({
    "detectionInfoList": [
        {"detectionName": "嗷呜", "levelName": "轻波级", "level": 1},
        {"detectionName": "咔咔", "levelName": "巨浪级", "level": 2},
    ],
    "exploreList": [
        {"country": {"countryId": 1, "countryName": "瑝珑"},
         "countryProgress": 67.06,
         "areaInfoList": [{"areaId": 1, "areaName": "云陵谷", "areaProgress": 100,
                           "itemList": [{"icon": "", "name": "信标",
                                         "progress": 100, "type": 2}]}]},
        {"country": {"countryId": 2, "countryName": "黑海岸"},
         "countryProgress": "60.00", "areaInfoList": []},
    ],
    "open": True,
}, ensure_ascii=False)}
CALABASH_RAW = {"code": 200, "msg": "success", "data": json.dumps({
    "level": 30, "baseCatch": "20%", "catchQuality": 5,
    "curExp": 1375, "maxCount": 724,
})}
ROLE_DATA_RAW = {"code": 200, "msg": "success", "data": json.dumps({
    "roleList": [
        {"roleId": 1501, "roleName": "长离", "level": 90, "attributeName": "热熔",
         "breach": 6, "chainUnlockNum": 0, "starLevel": 5,
         "weaponTypeName": "迅刀", "isMainRole": False},
        {"roleId": 1402, "roleName": "散华", "level": 90, "attributeName": "衍射",
         "breach": 6, "chainUnlockNum": 6, "starLevel": 5,
         "weaponTypeName": "迅刀", "isMainRole": True,
         "roleIconUrl": "https://web-static.kurobbs.com/a.png"},
    ], "showToGuest": True,
}, ensure_ascii=False)}


def _unconfigured():
    return WutheringWavesAdapter(Settings(wuwa_enabled=True))


def _rolebox_configured():
    # roleBox 三件套（b-at/devCode/did）全非空才启用探索度/数据坞
    return WutheringWavesAdapter(Settings(
        wuwa_token="tok", wuwa_user_id="123",
        wuwa_b_at="ticket0123456789abcdef0123456789",
        wuwa_dev_code="192.0.2.10, ua KuroGameBox/3.3.1",
        wuwa_did="00000000-0000-4000-8000-000000000001"))


async def test_unconfigured_reports_error():
    a = _unconfigured()
    assert a.credentials_configured is False
    for cap in a.capabilities:
        r = await a.fetch(cap)
        assert r.ok is False and "未配置凭据" in r.error


@respx.mock
async def test_fetch_account_ok():
    route = respx.post(ROLE_LIST_URL).mock(
        return_value=httpx.Response(200, json=ROLE_LIST_RAW))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.ACCOUNT)
    assert r.ok is True
    assert r.payload.nickname == "测试漂泊者"
    assert r.payload.level == 80  # gameLevel 字符串 "80" → int
    assert r.payload.extra["role_id"] == "100000001"


@respx.mock
async def test_fetch_stamina_ok():
    # fetch_stamina 两段调用：先 role/list 取默认角色 roleId/serverId，再查 widget；
    # 体力走 refresh 端点（getData 为缓存值，实测 26/240 vs refresh 33/240），
    # respx 按路径区分路由，请求体必须携带 role/list 返回的标识
    respx.post(ROLE_LIST_URL).mock(
        return_value=httpx.Response(200, json=ROLE_LIST_RAW))
    refresh_route = respx.post(WIDGET_REFRESH_URL).mock(
        return_value=httpx.Response(200, json=WIDGET_RAW))
    get_route = respx.post(WIDGET_URL).mock(
        return_value=httpx.Response(200, json=WIDGET_RAW))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.STAMINA)
    assert r.ok is True
    assert r.payload.current == 180 and r.payload.maximum == 240
    body = refresh_route.calls.last.request.content.decode()
    assert "roleId=100000001" in body
    assert "serverId=76402e5b20be2c39f095a152090afddc" in body
    assert "type=2" in body and "sizeType=1" in body
    assert get_route.calls.call_count == 0  # 体力不走 getData


def test_capabilities_events_after_stamina_no_activity():
    # 版本活动卡（ACTIVITY）已删除，活动日历（EVENTS）上移到体力卡之后
    caps = WutheringWavesAdapter.capabilities
    assert caps == [Capability.ACCOUNT, Capability.STAMINA, Capability.EVENTS,
                    Capability.PROGRESS, Capability.ANNOUNCEMENT,
                    Capability.EXPLORATION, Capability.CALABASH,
                    Capability.ROLES]
    assert not hasattr(Capability, "ACTIVITY")


@respx.mock
async def test_fetch_progress_ok():
    respx.post(ROLE_LIST_URL).mock(
        return_value=httpx.Response(200, json=ROLE_LIST_RAW))
    respx.post(WIDGET_URL).mock(
        return_value=httpx.Response(200, json=WIDGET_RAW))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.PROGRESS)
    assert r.ok is True
    assert all(isinstance(p, ProgressItem) for p in r.payload)
    by_name = {p.name: p for p in r.payload}
    tower = by_name["逆境深塔·深境区"]
    assert (tower.cur, tower.total) == (36, 36)
    assert tower.refresh_at is not None
    weekly = by_name["战歌重奏"]
    assert (weekly.cur, weekly.total) == (0, 3)
    assert weekly.refresh_at is None          # refreshTimeStamp=0 → None
    assert by_name["本周经验"].total == 12000  # battlePassData 扁平化


@respx.mock
async def test_no_bound_role_reports_error():
    # role/list 返回空数组：widget 系能力统一报"未找到绑定的鸣潮角色"
    respx.post(ROLE_LIST_URL).mock(
        return_value=httpx.Response(200, json={"code": 200, "data": []}))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.PROGRESS)
    assert r.ok is False and "未找到绑定的鸣潮角色" in r.error


@respx.mock
async def test_fetch_announcement_ok():
    route = respx.post(EVENT_URL).mock(
        return_value=httpx.Response(200, json=EVENT_RAW))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.ANNOUNCEMENT)
    assert r.ok is True
    assert r.payload[0].title == "2.6版本更新公告"
    assert r.payload[0].url == "https://www.kurobbs.com/forum/post/9001"
    assert "eventType=3" in route.calls.last.request.content.decode()


@respx.mock
async def test_fetch_events_ok():
    # 活动日历：公告列表（eventType=3）筛版本公告（标题匹配，干扰帖不选中）
    # → getPostDetail H5 正文 → 行级解析活动列表
    list_route = respx.post(EVENT_URL).mock(
        return_value=httpx.Response(200, json=EVENTS_LIST_RAW))
    detail_route = respx.post(DETAIL_URL).mock(
        return_value=httpx.Response(200, json=EVENTS_POST_DETAIL_RAW))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.EVENTS)
    assert r.ok is True and isinstance(r.payload, list)
    assert all(isinstance(e, GameEvent) for e in r.payload)
    assert [e.name for e in r.payload] == ["群声共振模拟域", "若梦仍有回声"]
    first, second = r.payload
    assert first.category == "战斗活动"
    assert first.start_at is not None and first.end_at is not None
    assert first.start_at.tzinfo is not None  # aware UTC+8（序列化后本地化展示）
    assert second.start_at is None            # "3.6版本更新后" 相对开始
    assert second.end_at is not None
    # 来源帖信息随事件带出
    assert {e.source_post_id for e in r.payload} == {"9001"}
    assert {e.source_title for e in r.payload} == \
        {"「蜃云灯影，凡尘剑心」3.6版本内容说明"}
    # 列表请求 eventType=3；详情请求仅 postId（实测形状）
    assert "eventType=3" in list_route.calls.last.request.content.decode()
    detail_body = detail_route.calls.last.request.content.decode()
    assert "postId=9001" in detail_body


@respx.mock
async def test_fetch_events_no_version_post_returns_empty():
    # 公告列表无版本公告（滚出/未发布）：空列表 + 不请求详情（优雅降级）
    respx.post(EVENT_URL).mock(
        return_value=httpx.Response(200, json=EVENTS_LIST_NO_VERSION_RAW))
    detail_route = respx.post(DETAIL_URL).mock(
        return_value=httpx.Response(200, json=EVENTS_POST_DETAIL_RAW))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.EVENTS)
    assert r.ok is True and r.payload == []
    assert detail_route.calls.call_count == 0


@respx.mock
async def test_fetch_events_detail_error_wrapped():
    # 版本公告详情接口失败 → _guarded_run 包裹为失败结果
    respx.post(EVENT_URL).mock(
        return_value=httpx.Response(200, json=EVENTS_LIST_RAW))
    respx.post(DETAIL_URL).mock(
        return_value=httpx.Response(200, json={"code": -1, "msg": "帖子不存在"}))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.EVENTS)
    assert r.ok is False and r.error


@respx.mock
async def test_kuro_error_wrapped():
    respx.post(ROLE_LIST_URL).mock(
        return_value=httpx.Response(200, json={"code": 220, "msg": "登录失效"}))
    a = WutheringWavesAdapter(Settings(wuwa_token="bad", wuwa_user_id="1"))
    r = await a.fetch(Capability.STAMINA)
    assert r.ok is False and "登录失效" in r.error


@respx.mock
async def test_malformed_payload_returns_fetch_error():
    # 200 但 widget data 是非法 JSON 字符串：json.loads 抛 JSONDecodeError（非 KuroError），
    # 解析异常必须被 _guarded_run 拦下转为失败结果，而不是穿透 fetch 破坏失效隔离
    respx.post(ROLE_LIST_URL).mock(
        return_value=httpx.Response(200, json=ROLE_LIST_RAW))
    respx.post(WIDGET_URL).mock(return_value=httpx.Response(
        200, json={"code": 200, "data": "{not-json}"}))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="1"))
    r = await a.fetch(Capability.STAMINA)
    assert r.ok is False and "数据解析异常" in r.error


@respx.mock
async def test_fetch_exploration_ok():
    # dispatch → fetch_exploration：role_list 取角色 → roleBox exploreIndex
    respx.post(ROLE_LIST_URL).mock(
        return_value=httpx.Response(200, json=ROLE_LIST_RAW))
    route = respx.post(f"{ROLEBOX_BASE_URL}/exploreIndex").mock(
        return_value=httpx.Response(200, json=EXPLORE_RAW))
    a = _rolebox_configured()
    r = await a.fetch(Capability.EXPLORATION)
    assert r.ok is True
    assert isinstance(r.payload, ExplorationData)
    assert r.payload.detections.total == 2
    assert r.payload.detections.by_level == {"轻波级": 1, "巨浪级": 1}
    assert [g.name for g in r.payload.country_groups] == ["瑝珑", "黑海岸"]
    assert r.payload.country_groups[0].progress == 67.06
    assert r.payload.country_groups[0].areas[0].name == "云陵谷"
    body = route.calls.last.request.content.decode()
    assert "roleId=100000001" in body and "channelId=19" in body
    # b-at 票据随请求头转发
    assert route.calls.last.request.headers["b-at"] == \
        "ticket0123456789abcdef0123456789"


@respx.mock
async def test_fetch_calabash_ok():
    respx.post(ROLE_LIST_URL).mock(
        return_value=httpx.Response(200, json=ROLE_LIST_RAW))
    respx.post(f"{ROLEBOX_BASE_URL}/calabashData").mock(
        return_value=httpx.Response(200, json=CALABASH_RAW))
    a = _rolebox_configured()
    r = await a.fetch(Capability.CALABASH)
    assert r.ok is True
    assert isinstance(r.payload, CalabashData)
    assert (r.payload.level, r.payload.base_catch) == (30, "20%")
    assert r.payload.max_count == 724


@respx.mock
async def test_fetch_roles_ok():
    # 角色练度墙：role_list 取角色 → roleBox roleData，按 level/chain 降序
    respx.post(ROLE_LIST_URL).mock(
        return_value=httpx.Response(200, json=ROLE_LIST_RAW))
    route = respx.post(f"{ROLEBOX_BASE_URL}/roleData").mock(
        return_value=httpx.Response(200, json=ROLE_DATA_RAW))
    a = _rolebox_configured()
    r = await a.fetch(Capability.ROLES)
    assert r.ok is True
    assert isinstance(r.payload, list)
    assert [e.name for e in r.payload] == ["散华", "长离"]  # 同级按 chain 降序
    assert r.payload[0].chain == 6 and r.payload[0].is_main is True
    body = route.calls.last.request.content.decode()
    assert "roleId=100000001" in body and "channelId" not in body


@respx.mock
async def test_rolebox_invalid_ticket_reports_recapture_hint():
    # b-at 过期（10901 禁止访问）→ 适配器透出明确的重新抓包提示
    respx.post(ROLE_LIST_URL).mock(
        return_value=httpx.Response(200, json=ROLE_LIST_RAW))
    respx.post(f"{ROLEBOX_BASE_URL}/exploreIndex").mock(
        return_value=httpx.Response(200, json={"code": 10901, "msg": "禁止访问"}))
    a = _rolebox_configured()
    r = await a.fetch(Capability.EXPLORATION)
    assert r.ok is False
    assert "b-at 已失效或角色不可见，请按 README 重新抓包" in r.error


@respx.mock
async def test_rolebox_unconfigured_reports_hint():
    # 网页 token 已配置但 roleBox 三件套缺失：role_list 成功后，
    # 探索度/数据坞给出明确指引（不触发 roleBox 请求）
    respx.post(ROLE_LIST_URL).mock(
        return_value=httpx.Response(200, json=ROLE_LIST_RAW))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    for cap in (Capability.EXPLORATION, Capability.CALABASH, Capability.ROLES):
        r = await a.fetch(cap)
        assert r.ok is False and "未配置 b-at" in r.error
