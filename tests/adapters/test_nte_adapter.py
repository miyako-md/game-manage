"""NteAdapter 组装测试（respx 离线）。

公告走匿名 Web 客户端（社区列表定位"官方资讯"栏目 → 栏目帖列表，
fixture 为 2026-09-13 匿名实测校准的形状，见 endpoints.py ⑥'）；
角色/进度/抽卡/战绩需塔吉多凭据，Phase 1 透传原始 dict payload
（解析器等真实响应校准后 Phase 2 补充）。
"""
import httpx
import respx

import game_assistant.adapters.neverness.adapter as adapter_mod
from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.adapters.neverness.adapter import NteAdapter
from game_assistant.config import Settings
from game_assistant.models import AnnouncementItem, Capability
from game_assistant.registry import build_default_registry
from game_assistant.scheduler import interval_for

BASE = "https://bbs-api.tajiduo.com"

# getAllCommunity 实测形状（2026-09-13，截取异环社区，字段原样保留）
COMMUNITY_RAW = {"code": 0, "msg": "ok", "ok": True, "data": [
    {"id": 2, "name": "异环", "gameId": 1289, "state": 0,
     "columns": [
         {"columnName": "官方资讯", "communityId": 2, "id": 4, "showType": 3},
         {"columnName": "攻略互助", "communityId": 2, "id": 10, "showType": 2},
     ]},
    {"id": 1, "name": "幻塔",
     "columns": [{"columnName": "海嘉德资讯", "communityId": 1, "id": 5}]},
]}
# getOfficialPostList 实测形状（2026-09-13，截取，字段原样保留）
POSTS_RAW = {"code": 0, "msg": "ok", "ok": True, "data": {
    "column": {"columnName": "官方资讯", "communityId": 2, "id": 4,
               "showType": 3},
    "hasMore": True, "page": 0,
    "posts": [
        {"ai": False, "columnId": 4, "communityId": 2,
         "content": "《异环》1.3版本「雾中朔望星回」现已开启，全新限定S级角色「灵可」登场！\n",
         "createTime": 1789184890182, "postId": 485925,
         "subject": "《异环》1.3版本「雾中朔望星回」现已开启",
         "type": 3, "uid": 10100006},
        {"ai": False, "columnId": 4, "communityId": 2,
         "createTime": 1789012000000, "postId": 483001,
         "sUrl": "https://bbs.tajiduo.com/a/2",
         "subject": "维护完成公告", "type": 3},
    ],
}}
ROLES_RAW = {"code": 0, "data": {"list": [
    {"roleId": "77", "serverName": "异环一区", "level": 60},
]}}
CHARACTERS_RAW = {"code": 0, "data": {"list": [{"name": "角色甲", "level": 80}]}}
ACHIEVE_RAW = {"code": 0, "data": {"achieveNum": 120, "achieveTotal": 300}}
GACHA_RAW = {"code": 0, "data": {"list": [{"gachaId": "g1", "count": 42}]}}
FULL_INFO_RAW = {"code": 0, "data": {"uid": "900001", "nickname": "玩家"}}
RECORD_RAW = {"code": 0, "data": {"uid": "900001", "hasRole": True}}


def _configured():
    return NteAdapter(Settings(nte_enabled=True, nte_access_token="acc",
                               nte_refresh_token="ref"))


async def test_unconfigured_reports_error_for_authed_capabilities():
    a = NteAdapter(Settings(nte_enabled=True))
    assert a.credentials_configured is False
    for cap in (Capability.ROLES, Capability.PROGRESS,
                Capability.GACHA, Capability.RECORD):
        r = await a.fetch(cap)
        assert r.ok is False and r.error == "未配置塔吉多凭据"


@respx.mock
async def test_unconfigured_announcement_still_available():
    # 公告为匿名接口：未配置凭据时公告能力不受影响
    respx.get(f"{BASE}/apihub/wapi/getAllCommunity").mock(
        return_value=httpx.Response(200, json=COMMUNITY_RAW))
    respx.get(f"{BASE}/bbs/wapi/getOfficialPostList").mock(
        return_value=httpx.Response(200, json=POSTS_RAW))
    a = NteAdapter(Settings())
    r = await a.fetch(Capability.ANNOUNCEMENT)
    assert r.ok is True and len(r.payload) == 2


@respx.mock
async def test_fetch_announcement_ok():
    comm = respx.get(f"{BASE}/apihub/wapi/getAllCommunity").mock(
        return_value=httpx.Response(200, json=COMMUNITY_RAW))
    route = respx.get(f"{BASE}/bbs/wapi/getOfficialPostList").mock(
        return_value=httpx.Response(200, json=POSTS_RAW))
    a = _configured()
    r = await a.fetch(Capability.ANNOUNCEMENT)
    assert r.ok is True
    assert isinstance(r.payload, list)
    assert [i.title for i in r.payload] == \
        ["《异环》1.3版本「雾中朔望星回」现已开启", "维护完成公告"]
    assert isinstance(r.payload[0], AnnouncementItem)
    assert r.payload[0].published_at is not None
    assert r.payload[0].url == "https://bbs.tajiduo.com/forum/post/485925"
    assert r.payload[1].url == "https://bbs.tajiduo.com/a/2"
    # 栏目 id 来自社区数据中的异环"官方资讯"（4 而非幻塔社区栏目）
    assert comm.calls.call_count == 1
    req = route.calls.last.request
    assert req.url.params["columnId"] == "4"
    assert req.url.params["count"] == "20"
    # 实测：空串 version/officialType 被服务端拒绝，必须不传
    assert "version" not in req.url.params
    assert "officialType" not in req.url.params
    # 匿名请求：无 authorization / 无 ds
    assert "authorization" not in req.headers and "ds" not in req.headers


@respx.mock
async def test_column_unresolved_reports_error():
    respx.get(f"{BASE}/apihub/wapi/getAllCommunity").mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"list": []}}))
    a = _configured()
    r = await a.fetch(Capability.ANNOUNCEMENT)
    assert r.ok is False and "官方资讯栏目" in r.error


@respx.mock
async def test_fetch_roles_returns_raw_payload():
    respx.get(f"{BASE}/usercenter/api/v2/getGameRoles").mock(
        return_value=httpx.Response(200, json=ROLES_RAW))
    route = respx.get(f"{BASE}/apihub/awapi/yh/characters").mock(
        return_value=httpx.Response(200, json=CHARACTERS_RAW))
    a = _configured()
    assert a.credentials_configured is True
    r = await a.fetch(Capability.ROLES)
    assert r.ok is True
    assert r.payload == CHARACTERS_RAW  # Phase 1：原始 dict payload
    req = route.calls.last.request
    assert req.headers["authorization"] == "acc"
    assert "ds" in req.headers
    assert req.url.params["roleId"] == "77"


@respx.mock
async def test_no_bound_role_reports_error():
    respx.get(f"{BASE}/usercenter/api/v2/getGameRoles").mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"list": []}}))
    a = _configured()
    r = await a.fetch(Capability.ROLES)
    assert r.ok is False and "未找到绑定的异环角色" in r.error


@respx.mock
async def test_fetch_progress_ok():
    respx.get(f"{BASE}/usercenter/api/v2/getGameRoles").mock(
        return_value=httpx.Response(200, json=ROLES_RAW))
    route = respx.get(f"{BASE}/apihub/awapi/yh/achieveProgress").mock(
        return_value=httpx.Response(200, json=ACHIEVE_RAW))
    a = _configured()
    r = await a.fetch(Capability.PROGRESS)
    assert r.ok is True
    assert r.payload == ACHIEVE_RAW
    assert route.calls.last.request.url.params["roleId"] == "77"


@respx.mock
async def test_fetch_gacha_ok():
    route = respx.get(f"{BASE}/apihub/awapi/yh/gacha").mock(
        return_value=httpx.Response(200, json=GACHA_RAW))
    a = _configured()
    r = await a.fetch(Capability.GACHA)
    assert r.ok is True
    assert r.payload == GACHA_RAW
    assert route.calls.last.request.headers["authorization"] == "acc"


@respx.mock
async def test_fetch_record_ok():
    respx.get(f"{BASE}/usercenter/api/getUserFullInfo").mock(
        return_value=httpx.Response(200, json=FULL_INFO_RAW))
    route = respx.get(f"{BASE}/apihub/api/getGameRecordCard").mock(
        return_value=httpx.Response(200, json=RECORD_RAW))
    a = _configured()
    r = await a.fetch(Capability.RECORD)
    assert r.ok is True
    assert r.payload == RECORD_RAW
    assert route.calls.last.request.url.params["uid"] == "900001"


@respx.mock
async def test_session_expired_maps_to_recapture_hint():
    # 401 → "会话已失效"提示（402/403 同，客户端层已参数化覆盖）
    respx.get(f"{BASE}/usercenter/api/v2/getGameRoles").mock(
        return_value=httpx.Response(401))
    a = _configured()
    r = await a.fetch(Capability.ROLES)
    assert r.ok is False and "会话已失效，请重新抓取 token" in r.error


@respx.mock
async def test_parser_exception_isolated(monkeypatch):
    # 解析器异常不得穿透 fetch 破坏失效隔离
    def boom(raw):
        raise RuntimeError("解析炸了")

    monkeypatch.setattr(adapter_mod.tajiduo, "parse_official_posts", boom)
    respx.get(f"{BASE}/apihub/wapi/getAllCommunity").mock(
        return_value=httpx.Response(200, json=COMMUNITY_RAW))
    respx.get(f"{BASE}/bbs/wapi/getOfficialPostList").mock(
        return_value=httpx.Response(200, json=POSTS_RAW))
    a = _configured()
    r = await a.fetch(Capability.ANNOUNCEMENT)
    assert r.ok is False and "数据处理异常" in r.error


def test_registry_includes_nte():
    reg = build_default_registry(Settings(wuwa_enabled=False,
                                          lol_enabled=False,
                                          nte_enabled=True))
    adapter = reg.get("nte")
    assert adapter.display_name == "异环" and adapter.section == "mobile"
    assert adapter.capabilities == [Capability.ANNOUNCEMENT, Capability.ROLES,
                                    Capability.PROGRESS, Capability.GACHA,
                                    Capability.RECORD]


def test_registry_nte_disabled_skips_registration():
    reg = build_default_registry(Settings(wuwa_enabled=False,
                                          lol_enabled=False,
                                          nte_enabled=False))
    assert "nte" not in {a.game_id for a in reg.all()}


def test_gacha_record_intervals_reuse_news_seconds():
    assert interval_for(Capability.GACHA, Settings()) == 14400
    assert interval_for(Capability.RECORD, Settings()) == 14400
    assert interval_for(Capability.GACHA, Settings(news_seconds=60)) == 60


async def test_base_dispatch_defaults_for_gacha_record():
    # base dispatch map 含新能力，默认实现报"适配器未实现该能力"
    class Dummy(BaseGameAdapter):
        game_id = "dummy"
        capabilities = [Capability.GACHA, Capability.RECORD]

    d = Dummy()
    d.credentials_configured = True
    for cap in (Capability.GACHA, Capability.RECORD):
        r = await d.fetch(cap)
        assert r.ok is False and "适配器未实现该能力" in r.error
