import httpx
import respx

from game_assistant.adapters.wuthering_waves.adapter import WutheringWavesAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability
from game_assistant.models import ProgressItem, VersionActivity

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

ROLE_LIST_URL = "https://api.kurobbs.com/gamer/role/list"
WIDGET_URL = "https://api.kurobbs.com/gamer/widget/game3/getData"
EVENT_URL = "https://api.kurobbs.com/forum/companyEvent/findEventList"


def _unconfigured():
    return WutheringWavesAdapter(Settings(wuwa_enabled=True))


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
    # respx 按路径区分路由，widget 请求体必须携带 role/list 返回的标识
    respx.post(ROLE_LIST_URL).mock(
        return_value=httpx.Response(200, json=ROLE_LIST_RAW))
    widget_route = respx.post(WIDGET_URL).mock(
        return_value=httpx.Response(200, json=WIDGET_RAW))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.STAMINA)
    assert r.ok is True
    assert r.payload.current == 180 and r.payload.maximum == 240
    body = widget_route.calls.last.request.content.decode()
    assert "roleId=100000001" in body
    assert "serverId=76402e5b20be2c39f095a152090afddc" in body


@respx.mock
async def test_fetch_activity_ok():
    # 版本活动改走 widget getData（activityData），不再是 findEventList 活动列表
    respx.post(ROLE_LIST_URL).mock(
        return_value=httpx.Response(200, json=ROLE_LIST_RAW))
    respx.post(WIDGET_URL).mock(
        return_value=httpx.Response(200, json=WIDGET_RAW))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.ACTIVITY)
    assert r.ok is True
    assert isinstance(r.payload, VersionActivity)
    assert r.payload.title == "身赴三途"
    assert r.payload.end_at is not None
    assert r.payload.core_rewards[0].name == "若梦仍有回声"


@respx.mock
async def test_fetch_activity_without_activity_data_returns_none_payload():
    respx.post(ROLE_LIST_URL).mock(
        return_value=httpx.Response(200, json=ROLE_LIST_RAW))
    respx.post(WIDGET_URL).mock(return_value=httpx.Response(
        200, json={"code": 200, "data": {"energyData": WIDGET_RAW["data"]["energyData"]}}))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.ACTIVITY)
    assert r.ok is True and r.payload is None


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
