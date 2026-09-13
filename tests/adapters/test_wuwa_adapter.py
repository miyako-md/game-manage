import httpx
import respx

from game_assistant.adapters.wuthering_waves.adapter import WutheringWavesAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability

# 实测响应形状（2026-09-13），见 endpoints.py 注释
ROLE_LIST_RAW = {"code": 200, "msg": "success", "data": [{
    "roleId": "100000001", "serverId": "76402e5b20be2c39f095a152090afddc",
    "roleName": "测试漂泊者", "gameLevel": "80", "activeDay": 534,
    "achievementCount": 604, "roleNum": 46, "serverName": "鸣潮",
    "isDefault": True,
}]}
WIDGET_RAW = {"code": 200, "msg": "success", "data": {
    "energyData": {"name": "结晶波片", "cur": 180, "total": 240,
                   "refreshTimeStamp": 0, "expireTimeStamp": 0, "status": 0},
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
    route = respx.post(EVENT_URL).mock(
        return_value=httpx.Response(200, json=EVENT_RAW))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.ACTIVITY)
    assert r.ok is True
    assert r.payload[0].title == "2.6版本更新公告"
    assert r.payload[0].url == "https://img.kurobbs.com/upload/9001.jpg"
    assert "eventType=1" in route.calls.last.request.content.decode()


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
