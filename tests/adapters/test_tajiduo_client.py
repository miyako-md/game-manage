"""塔吉多客户端测试（respx 离线）。

匿名客户端断言无 authorization/ds 头；鉴权客户端断言 APP 形态头 +
DS 签名（可由 ds_sign 复算）+ 401/402/403 会话失效提示。
"""
import uuid

import httpx
import pytest
import respx

from game_assistant.adapters.neverness.tajiduo_client import (
    TajiduoClient, TajiduoError, TajiduoWebClient, ds_sign, make_ds_header,
)

BASE = "https://bbs-api.tajiduo.com"

COMMUNITY_RAW = {"code": 0, "msg": "ok", "ok": True, "data": [
    {"id": 2, "name": "异环", "gameId": 1289,
     "columns": [{"columnName": "官方资讯", "communityId": 2, "id": 4,
                  "showType": 3}]},
]}
POST_LIST_RAW = {"code": 0, "msg": "ok", "ok": True, "data": {
    "column": {"columnName": "官方资讯", "communityId": 2, "id": 4,
               "showType": 3},
    "hasMore": True, "page": 0,
    "posts": [{"postId": 485925, "subject": "1.3版本「雾中朔望星回」现已开启",
               "createTime": 1789184890182, "type": 3}],
}}
# getPostFull（匿名 GET，code=0）：data.post.content 为正文（HTML 或明文）
POST_FULL_RAW = {"code": 0, "msg": "ok", "ok": True, "data": {"post": {
    "postId": 485925, "subject": "《异环》1.5版本内容说明",
    "content": "<p>[演练演习]战斗活动</p>"
               "<p>活动时间：2026年9月20日10:00 ~ 2026年10月8日03:59（服务器时间）</p>",
    "type": 3,
}}}


def test_ds_sign_deterministic():
    # 固定 ts/nonce → 可预期 md5（ts + nonce + appversion + 盐，
    # 期望值实现前用 hashlib 独立计算，防实现自证）
    assert ds_sign(1700000000, "ab12cd34") == "17d853a80aaeb6cdd9e7274756890cb7"


def test_make_ds_header_format():
    ts, nonce, sign = make_ds_header().split(",")
    assert ts.isdigit() and len(nonce) == 8 and nonce.isalnum()
    assert len(sign) == 32
    # ds 头三段可由 ds_sign 复算还原
    assert ds_sign(int(ts), nonce) == sign


@respx.mock
async def test_get_all_communities_anonymous():
    route = respx.get(f"{BASE}/apihub/wapi/getAllCommunity").mock(
        return_value=httpx.Response(200, json=COMMUNITY_RAW))
    async with TajiduoWebClient() as web:
        data = await web.get_all_communities()
    assert data == COMMUNITY_RAW
    req = route.calls.last.request
    assert "authorization" not in req.headers and "ds" not in req.headers
    assert req.headers["User-Agent"].startswith("Mozilla/5.0")


@respx.mock
async def test_get_official_post_list_anonymous_headers():
    route = respx.get(f"{BASE}/bbs/wapi/getOfficialPostList").mock(
        return_value=httpx.Response(200, json=POST_LIST_RAW))
    async with TajiduoWebClient() as web:
        data = await web.get_official_post_list("4", count=5)
    assert data["data"]["posts"][0]["postId"] == 485925
    req = route.calls.last.request
    # 匿名 Web 客户端：无 authorization / 无 ds / UA Mozilla/5.0
    assert "authorization" not in req.headers and "ds" not in req.headers
    assert req.headers["User-Agent"].startswith("Mozilla/5.0")
    params = req.url.params
    assert params["columnId"] == "4" and params["count"] == "5"
    # 2026-09-13 实测：空串 version/officialType 被服务端拒绝（code=6），
    # 必须不传（回归护栏）
    assert "version" not in params and "officialType" not in params


@respx.mock
async def test_get_post_full_anonymous():
    route = respx.get(f"{BASE}/bbs/wapi/getPostFull").mock(
        return_value=httpx.Response(200, json=POST_FULL_RAW))
    async with TajiduoWebClient() as web:
        post = await web.get_post_full("485925")
    # 返回 data.post 本体（dict）
    assert post["subject"] == "《异环》1.5版本内容说明"
    assert "content" in post
    req = route.calls.last.request
    assert req.url.params["postId"] == "485925"
    # 匿名请求：无 authorization / 无 ds
    assert "authorization" not in req.headers and "ds" not in req.headers


@respx.mock
async def test_get_post_full_bad_shape_raises():
    respx.get(f"{BASE}/bbs/wapi/getPostFull").mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"post": None}}))
    async with TajiduoWebClient() as web:
        with pytest.raises(TajiduoError) as ei:
            await web.get_post_full("1")
    assert "帖子详情响应结构异常" in ei.value.message


AUTHED_CASES = [
    ("get_user_full_info", (), f"{BASE}/usercenter/api/getUserFullInfo", {}),
    ("get_game_roles", (), f"{BASE}/usercenter/api/v2/getGameRoles",
     {"gameId": "1289"}),
    ("get_game_record_card", ("900001",),
     f"{BASE}/apihub/api/getGameRecordCard", {"uid": "900001"}),
    ("get_role_home", ("77",), f"{BASE}/apihub/awapi/yh/roleHome",
     {"roleId": "77"}),
    ("get_role_characters", ("77",), f"{BASE}/apihub/awapi/yh/characters",
     {"roleId": "77"}),
    ("get_role_achievement_progress", ("77",),
     f"{BASE}/apihub/awapi/yh/achieveProgress", {"roleId": "77"}),
    ("get_role_area_progress", ("77",), f"{BASE}/apihub/awapi/yh/areaProgress",
     {"roleId": "77"}),
    ("get_role_realestate", ("77",), f"{BASE}/apihub/awapi/yh/realestate",
     {"roleId": "77"}),
    ("get_role_vehicles", ("77",), f"{BASE}/apihub/awapi/yh/vehicles",
     {"roleId": "77"}),
    ("get_gacha_summary", (), f"{BASE}/apihub/awapi/yh/gacha", {}),
]


@pytest.mark.parametrize(("method_name", "args", "url", "params"), AUTHED_CASES)
@respx.mock
async def test_authed_endpoints_headers_paths_params(method_name, args, url,
                                                     params):
    route = respx.get(url).mock(return_value=httpx.Response(
        200, json={"code": 0, "data": {"ok": method_name}}))
    async with TajiduoClient("acc-token", "ref-token",
                             device_id="DEV-UUID") as client:
        data = await getattr(client, method_name)(*args)
    assert data["data"]["ok"] == method_name
    req = route.calls.last.request
    # APP 形态默认头 + DS 签名（endpoints.py ③）
    assert req.headers["authorization"] == "acc-token"
    assert req.headers["User-Agent"] == "okhttp/4.12.0"
    assert req.headers["platform"] == "android"
    assert req.headers["deviceid"] == "DEV-UUID"
    assert req.headers["appversion"] == "1.2.4"
    assert req.headers["uid"] == "0"
    ts, nonce, sign = req.headers["ds"].split(",")
    assert ds_sign(int(ts), nonce) == sign
    for k, v in params.items():
        assert req.url.params[k] == v


def test_client_default_device_id_is_uuid():
    client = TajiduoClient("acc", "ref")
    uuid.UUID(client._device_id)  # 合法 UUID（不抛异常）
    assert client.access_token == "acc" and client.refresh_token == "ref"


@respx.mock
async def test_refresh_session_updates_tokens():
    route = respx.post(f"{BASE}/usercenter/api/refreshToken").mock(
        return_value=httpx.Response(200, json={
            "code": 0, "data": {"accessToken": "new-acc",
                                "refreshToken": "new-ref"}}))
    client = TajiduoClient("old-acc", "old-ref")
    access, refresh = await client.refresh_session()
    await client.aclose()
    assert (access, refresh) == ("new-acc", "new-ref")
    assert client.access_token == "new-acc"
    assert client.refresh_token == "new-ref"
    req = route.calls.last.request
    # 刷新请求头 authorization=refresh_token，无 body（endpoints.py ④）
    assert req.headers["authorization"] == "old-ref"
    assert req.content == b""


@respx.mock
async def test_refresh_session_top_level_token_fallback():
    # data 容器缺失时回退顶层键；未返回 refreshToken 时保留旧值
    respx.post(f"{BASE}/usercenter/api/refreshToken").mock(
        return_value=httpx.Response(200, json={"code": 0,
                                               "accessToken": "a2"}))
    client = TajiduoClient("a1", "r1")
    access, refresh = await client.refresh_session()
    await client.aclose()
    assert access == "a2" and refresh == "r1"


@respx.mock
async def test_refresh_without_new_token_raises():
    respx.post(f"{BASE}/usercenter/api/refreshToken").mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {}}))
    client = TajiduoClient("a1", "r1")
    with pytest.raises(TajiduoError) as ei:
        await client.refresh_session()
    await client.aclose()
    assert "未找到新 token" in ei.value.message


@pytest.mark.parametrize("status", [401, 402, 403])
@respx.mock
async def test_auth_session_expired_reports_recapture_hint(status):
    respx.get(f"{BASE}/usercenter/api/v2/getGameRoles").mock(
        return_value=httpx.Response(status, json={"message": "unauthorized"}))
    client = TajiduoClient("acc", "ref")
    with pytest.raises(TajiduoError) as ei:
        await client.get_game_roles()
    await client.aclose()
    assert "塔吉多会话已失效，请在「社区账号」重新登录异环" == ei.value.message
    assert ei.value.status_code == status


@respx.mock
async def test_auth_other_http_error_is_generic():
    # 非 401/402/403 不误报会话失效
    respx.get(f"{BASE}/usercenter/api/getUserFullInfo").mock(
        return_value=httpx.Response(500))
    client = TajiduoClient("acc", "ref")
    with pytest.raises(TajiduoError) as ei:
        await client.get_user_full_info()
    await client.aclose()
    assert ei.value.message == "HTTP 500"


@respx.mock
async def test_business_code_error_raises():
    respx.get(f"{BASE}/usercenter/api/getUserFullInfo").mock(
        return_value=httpx.Response(200,
                                    json={"code": 1001, "message": "请先登录"}))
    client = TajiduoClient("acc", "ref")
    with pytest.raises(TajiduoError) as ei:
        await client.get_user_full_info()
    await client.aclose()
    assert "code=1001" in ei.value.message and "请先登录" in ei.value.message


@respx.mock
async def test_network_error_wrapped():
    respx.get(f"{BASE}/usercenter/api/getUserFullInfo").mock(
        side_effect=httpx.ConnectError("boom"))
    client = TajiduoClient("acc", "ref")
    with pytest.raises(TajiduoError) as ei:
        await client.get_user_full_info()
    await client.aclose()
    assert "网络错误" in ei.value.message


@respx.mock
async def test_web_client_401_is_generic_not_session_message():
    # 会话失效提示只用于鉴权请求（匿名公告请求 401 走通用 HTTP 错误）
    respx.get(f"{BASE}/bbs/wapi/getOfficialPostList").mock(
        return_value=httpx.Response(401))
    async with TajiduoWebClient() as web:
        with pytest.raises(TajiduoError) as ei:
            await web.get_official_post_list("4")
    assert ei.value.message == "HTTP 401"
