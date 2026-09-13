import httpx
import pytest
import respx

from game_assistant.adapters.wuthering_waves.kuro_client import KuroClient, KuroError

# 实测响应形状（2026-09-13 首次真实连接校准），见 endpoints.py 注释
ROLE_LIST_RAW = {"code": 200, "msg": "success", "data": [{
    "roleId": "100000001", "serverId": "76402e5b20be2c39f095a152090afddc",
    "roleName": "测试漂泊者", "gameLevel": "80", "activeDay": 534,
    "achievementCount": 604, "roleNum": 46, "serverName": "鸣潮",
    "isDefault": True,
}]}
WIDGET_RAW = {"code": 200, "msg": "success", "data": {
    "energyData": {"name": "结晶波片", "cur": 240, "total": 240,
                   "refreshTimeStamp": 0, "expireTimeStamp": 0, "status": 0},
    "hasSignIn": True, "roleName": "测试漂泊者",
}}
EVENT_RAW = {"code": 200, "msg": "success", "data": {"list": [{
    "id": "100", "postTitle": "2.6版本更新公告", "publishTime": 1789182000000,
    "postId": "9001", "coverUrl": "https://img.kurobbs.com/upload/9001.jpg",
    "firstPublishTime": 1789182000000, "eventType": 3,
}]}}


@respx.mock
async def test_role_list_ok():
    route = respx.post("https://api.kurobbs.com/gamer/role/list").mock(
        return_value=httpx.Response(200, json=ROLE_LIST_RAW))
    client = KuroClient(token="tok", user_id="123456")
    data = await client.role_list()
    assert data["data"][0]["roleId"] == "100000001"
    req = route.calls.last.request
    assert req.headers["token"] == "tok"
    assert b"gameId=3" in req.content  # form-urlencoded，仅 gameId（token 即身份）
    assert b"userId" not in req.content


@respx.mock
async def test_widget_data_ok():
    route = respx.post("https://api.kurobbs.com/gamer/widget/game3/getData").mock(
        return_value=httpx.Response(200, json=WIDGET_RAW))
    client = KuroClient(token="tok", user_id="1")
    data = await client.widget_data("100000001", "76402e5b20be2c39f095a152090afddc")
    assert data["data"]["energyData"]["cur"] == 240
    body = route.calls.last.request.content.decode()
    assert "gameId=3" in body and "roleId=100000001" in body
    assert "serverId=76402e5b20be2c39f095a152090afddc" in body
    assert "type=2" in body and "sizeType=1" in body


@respx.mock
async def test_widget_data_refresh_uses_refresh_endpoint():
    # refresh=True 走同族 refresh 端点（参数与 getData 相同，实测数据更新鲜，
    # 体力专用，见 endpoints.py ⑧）；默认 False 保持 getData
    route = respx.post("https://api.kurobbs.com/gamer/widget/game3/refresh").mock(
        return_value=httpx.Response(200, json=WIDGET_RAW))
    client = KuroClient(token="tok", user_id="1")
    data = await client.widget_data("100000001",
                                    "76402e5b20be2c39f095a152090afddc",
                                    refresh=True)
    assert data["data"]["energyData"]["cur"] == 240
    body = route.calls.last.request.content.decode()
    assert "gameId=3" in body and "type=2" in body and "sizeType=1" in body


@respx.mock
async def test_find_event_list_ok():
    route = respx.post(
        "https://api.kurobbs.com/forum/companyEvent/findEventList").mock(
        return_value=httpx.Response(200, json=EVENT_RAW))
    client = KuroClient(token="tok", user_id="1")
    data = await client.find_event_list(3)
    assert data["data"]["list"][0]["postTitle"] == "2.6版本更新公告"
    body = route.calls.last.request.content.decode()
    assert "gameId=3" in body and "eventType=3" in body


@respx.mock
async def test_error_raises_kuro_error():
    respx.post("https://api.kurobbs.com/gamer/role/list").mock(
        return_value=httpx.Response(200, json={"code": 220, "msg": "登录失效"}))
    client = KuroClient(token="bad", user_id="1")
    with pytest.raises(KuroError) as ei:
        await client.role_list()
    assert ei.value.code == 220
