import httpx
import pytest
import respx

from game_assistant.adapters.wuthering_waves.rolebox_client import (
    RoleBoxClient, RoleBoxError, USER_AGENT,
)

# 头三件套样例（2026-09-13 实测；devCode 格式 = "客户端公网IP, 空格+完整UA"）
B_AT = "0123456789abcdef0123456789abcdef"
DEV_CODE = ("192.0.2.10, Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko)  KuroGameBox/3.3.1")
DID = "00000000-0000-4000-8000-000000000001"

BASE_URL = "https://api.kurobbs.com/aki/roleBox/akiBox"
ROLE_ID = "100000001"
SERVER_ID = "76402e5b20be2c39f095a152090afddc"

# roleBox 响应 data 是 JSON 字符串（与 widget 不同），需二次解析
BASE_DATA_RAW = {"code": 200, "msg": "success",
                 "data": "{\"energy\":240,\"level\":80,\"activeDay\":534}"}
EXPLORE_RAW = {"code": 200, "msg": "success",
               "data": "{\"countryProgress\":\"85%\",\"areaInfoList\":[],"
                       "\"detectionInfoList\":[]}"}
CALABASH_RAW = {"code": 200, "msg": "success",
                "data": "{\"level\":30,\"baseCatch\":\"20%\",\"catchQuality\":5,"
                        "\"curExp\":1375,\"maxCount\":724}"}


def _client() -> RoleBoxClient:
    return RoleBoxClient(b_at=B_AT, dev_code=DEV_CODE, did=DID)


def _assert_common_headers(req: httpx.Request) -> None:
    # 必需头逐字断言（httpx.Headers 大小写不敏感）
    assert req.headers["b-at"] == B_AT
    assert req.headers["devCode"] == DEV_CODE
    assert req.headers["source"] == "ios"
    assert req.headers["did"] == DID
    assert req.headers["Origin"] == "https://web-static.kurobbs.com"
    assert req.headers["Content-Type"] == "application/x-www-form-urlencoded"
    # UA 常量与 devCode 内 UA 一致（KuroGameBox 前两个空格，逐字保留）
    assert req.headers["User-Agent"] == USER_AGENT
    assert "  KuroGameBox/3.3.1" in req.headers["User-Agent"]


@respx.mock
async def test_base_data_ok_parses_string_data():
    route = respx.post(f"{BASE_URL}/baseData").mock(
        return_value=httpx.Response(200, json=BASE_DATA_RAW))
    async with _client() as client:
        data = await client.base_data(ROLE_ID, SERVER_ID)
    assert data["energy"] == 240 and data["level"] == 80
    req = route.calls.last.request
    _assert_common_headers(req)
    body = req.content.decode()
    assert "gameId=3" in body and "roleId=100000001" in body
    assert "serverId=76402e5b20be2c39f095a152090afddc" in body


@respx.mock
async def test_explore_index_ok_and_body_has_channel():
    route = respx.post(f"{BASE_URL}/exploreIndex").mock(
        return_value=httpx.Response(200, json=EXPLORE_RAW))
    async with _client() as client:
        data = await client.explore_index(ROLE_ID, SERVER_ID)
    assert data["countryProgress"] == "85%"
    _assert_common_headers(route.calls.last.request)
    body = route.calls.last.request.content.decode()
    # exploreIndex body 比 baseData 多 channelId=19 & countryCode=1（实测必需）
    assert "channelId=19" in body and "countryCode=1" in body


@respx.mock
async def test_calabash_data_ok():
    route = respx.post(f"{BASE_URL}/calabashData").mock(
        return_value=httpx.Response(200, json=CALABASH_RAW))
    async with _client() as client:
        data = await client.calabash_data(ROLE_ID, SERVER_ID)
    assert data["level"] == 30 and data["maxCount"] == 724
    _assert_common_headers(route.calls.last.request)


@respx.mock
async def test_invalid_ticket_maps_to_recapture_hint():
    # code=10901 msg 含"禁止访问"（b-at 过期/无效实测形状）→ 明确重新抓包提示
    respx.post(f"{BASE_URL}/baseData").mock(
        return_value=httpx.Response(200, json={"code": 10901, "msg": "禁止访问"}))
    async with _client() as client:
        with pytest.raises(RoleBoxError) as ei:
            await client.base_data(ROLE_ID, SERVER_ID)
    assert ei.value.message == "b-at 已失效或角色不可见，请按 README 重新抓包"


@respx.mock
async def test_role_query_failure_maps_to_recapture_hint():
    respx.post(f"{BASE_URL}/exploreIndex").mock(
        return_value=httpx.Response(200, json={"code": 10900, "msg": "角色查询失败"}))
    async with _client() as client:
        with pytest.raises(RoleBoxError) as ei:
            await client.explore_index(ROLE_ID, SERVER_ID)
    assert "重新抓包" in ei.value.message


@respx.mock
async def test_other_error_exposes_msg():
    respx.post(f"{BASE_URL}/calabashData").mock(
        return_value=httpx.Response(200, json={"code": 500, "msg": "服务器繁忙"}))
    async with _client() as client:
        with pytest.raises(RoleBoxError) as ei:
            await client.calabash_data(ROLE_ID, SERVER_ID)
    assert ei.value.message == "服务器繁忙"


@respx.mock
async def test_network_error_wrapped():
    respx.post(f"{BASE_URL}/baseData").mock(
        side_effect=httpx.ConnectError("boom"))
    async with _client() as client:
        with pytest.raises(RoleBoxError) as ei:
            await client.base_data(ROLE_ID, SERVER_ID)
    assert "网络错误" in ei.value.message


@respx.mock
async def test_http_error_status():
    respx.post(f"{BASE_URL}/baseData").mock(
        return_value=httpx.Response(502))
    async with _client() as client:
        with pytest.raises(RoleBoxError) as ei:
            await client.base_data(ROLE_ID, SERVER_ID)
    assert ei.value.message == "HTTP 502"


@respx.mock
async def test_non_dict_data_raises_structure_error():
    respx.post(f"{BASE_URL}/baseData").mock(
        return_value=httpx.Response(200, json={"code": 200, "data": "[1,2]"}))
    async with _client() as client:
        with pytest.raises(RoleBoxError) as ei:
            await client.base_data(ROLE_ID, SERVER_ID)
    assert ei.value.message == "响应结构异常"


@respx.mock
async def test_bad_string_data_raises_structure_error():
    respx.post(f"{BASE_URL}/baseData").mock(
        return_value=httpx.Response(200, json={"code": 200, "data": "{not-json}"}))
    async with _client() as client:
        with pytest.raises(RoleBoxError) as ei:
            await client.base_data(ROLE_ID, SERVER_ID)
    assert ei.value.message == "响应结构异常"
