"""NteAdapter 标准化数据组装测试（respx 离线）。

公告走匿名 Web 客户端（社区列表定位"官方资讯"栏目 → 栏目帖列表，
fixture 为 2026-09-13 匿名实测校准的形状，见 endpoints.py ⑥'）；
角色/成就/抽卡/社区名片使用塔吉多凭据，成功返回版本化 Pydantic 数据。
"""
import httpx
import respx
from datetime import datetime

import game_assistant.adapters.neverness.adapter as adapter_mod
from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.adapters.neverness.adapter import NteAdapter
from game_assistant.config import Settings
from game_assistant.event_calendar import BEIJING_TZ
from game_assistant.models import AnnouncementItem, Capability, GameEvent
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
# getPostFull（活动日历链路）：data.post.content 为正文（2026-09-13 实测端点形状，
# 正文行文按鸣潮同类版本公告的中文日期区间模式，待异环真实版本公告出现后校准）
EVENTS_POSTS_RAW = {"code": 0, "msg": "ok", "ok": True, "data": {
    "column": {"columnName": "官方资讯", "communityId": 2, "id": 4},
    "hasMore": True, "page": 0,
    "posts": [
        {"postId": 486000, "subject": "《异环》1.5版本内容说明",
         "createTime": 1789990000000, "type": 3},
        {"postId": 485925, "subject": "《异环》1.3版本「雾中朔望星回」现已开启",
         "createTime": 1789184890182, "type": 3},
    ],
}}
EVENTS_POST_FULL_RAW = {"code": 0, "msg": "ok", "ok": True, "data": {"post": {
    "postId": 486000, "subject": "《异环》1.5版本内容说明",
    "content": "<p>[演练演习]战斗活动</p>"
               "<p>活动时间：2026年9月20日10:00 ~ 2026年10月8日03:59（服务器时间）</p>"
               "<p>[签到赠礼]七日签到活动</p>"
               "<p>活动时间：1.5版本更新后 ~ 2026年10月8日03:59（服务器时间）</p>",
    "type": 3,
}}}
ROLES_RAW = {"code": 0, "data": {"list": [
    {"roleId": "77", "serverName": "异环一区", "level": 60},
]}}
CHARACTERS_RAW = {"code": 0, "data": [{"id": "1019", "name": "角色甲", "alev": 80}]}
ACHIEVE_RAW = {"code": 0, "data": {"achievementCnt": 120, "total": 300, "detail": []}}
GACHA_RAW = {"code": 0, "data": {"gachaDetails": [{"tab": "限定卡池", "drawCount": 42,
                                                   "rareCount": 1, "details": []}]}}
FULL_INFO_RAW = {"code": 0, "data": {"uid": "900001", "nickname": "玩家"}}
RECORD_RAW = {"code": 0, "data": [{"gameId": 1289, "gameName": "异环",
                                  "bindRoleInfo": {"roleId": "77", "roleName": "玩家", "lev": 40}}]}


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
async def test_fetch_events_ok():
    # 活动日历：官方栏目帖列表筛版本公告（subject 匹配，干扰帖不选中）
    # → getPostFull 正文 → 行级解析活动列表（匿名 Web 客户端）
    respx.get(f"{BASE}/apihub/wapi/getAllCommunity").mock(
        return_value=httpx.Response(200, json=COMMUNITY_RAW))
    list_route = respx.get(f"{BASE}/bbs/wapi/getOfficialPostList").mock(
        return_value=httpx.Response(200, json=EVENTS_POSTS_RAW))
    detail_route = respx.get(f"{BASE}/bbs/wapi/getPostFull").mock(
        return_value=httpx.Response(200, json=EVENTS_POST_FULL_RAW))
    a = _configured()
    r = await a.fetch(Capability.EVENTS)
    assert r.ok is True and isinstance(r.payload, list)
    assert all(isinstance(e, GameEvent) for e in r.payload)
    assert [e.name for e in r.payload] == ["演练演习", "签到赠礼"]
    first, second = r.payload
    assert first.category == "战斗活动"
    assert first.start_at is not None and first.end_at is not None
    assert second.start_at is None            # "1.5版本更新后" 相对开始
    assert {e.source_post_id for e in r.payload} == {"486000"}
    assert {e.source_title for e in r.payload} == {"《异环》1.5版本内容说明"}
    req = detail_route.calls.last.request
    assert req.url.params["postId"] == "486000"
    assert "authorization" not in req.headers and "ds" not in req.headers
    assert list_route.calls.last.request.url.params["columnId"] == "4"


@respx.mock
async def test_fetch_events_no_version_post_preserves_previous_calendar():
    # 官方栏目无版本公告（POSTS_RAW 仅有开启公告/维护完成公告）：
    # 返回来源问题，不请求帖子详情；保留上次成功日历。
    respx.get(f"{BASE}/apihub/wapi/getAllCommunity").mock(
        return_value=httpx.Response(200, json=COMMUNITY_RAW))
    respx.get(f"{BASE}/bbs/wapi/getOfficialPostList").mock(
        return_value=httpx.Response(200, json=POSTS_RAW))
    detail_route = respx.get(f"{BASE}/bbs/wapi/getPostFull").mock(
        return_value=httpx.Response(200, json=EVENTS_POST_FULL_RAW))
    a = NteAdapter(Settings(nte_enabled=True))
    r = await a.fetch(Capability.EVENTS)
    assert r.ok is False and r.error_kind == 'source_error'
    assert detail_route.calls.call_count == 0


# ---------- 手填活动（config [[nte_events]]，可靠主路径） ----------

MANUAL_EVENTS = [
    {"name": "第二索拉·诡影迷踪", "category": "休闲活动",
     "start": "2026-08-27 04:00", "end": "2026-09-14 03:59"},
    {"name": "烟云赠礼", "start": "2026-08-27 04:00",
     "end": "2026-09-14 03:59"},
]


@respx.mock
async def test_fetch_events_manual_config_takes_priority():
    # 手填非空 → 直接解析为 payload，不再请求塔吉多（可靠主路径）
    comm = respx.get(f"{BASE}/apihub/wapi/getAllCommunity").mock(
        return_value=httpx.Response(200, json=COMMUNITY_RAW))
    a = NteAdapter(Settings(nte_enabled=True, nte_events=MANUAL_EVENTS))
    r = await a.fetch(Capability.EVENTS)
    assert r.ok is True and isinstance(r.payload, list)
    assert [e.name for e in r.payload] == ["第二索拉·诡影迷踪", "烟云赠礼"]
    first = r.payload[0]
    assert isinstance(first, GameEvent)
    assert first.category == "休闲活动"
    # 字符串时间 → aware UTC+8 datetime（服务器时间）
    assert first.start_at == datetime(2026, 8, 27, 4, 0, tzinfo=BEIJING_TZ)
    assert first.end_at == datetime(2026, 9, 14, 3, 59, tzinfo=BEIJING_TZ)
    assert comm.calls.call_count == 0                # 不走塔吉多扫描


@respx.mock
async def test_fetch_events_manual_bad_entries_skipped_no_fallback():
    # 坏时间戳项跳过并告警，好项保留；配置非空即手填主路径（不回退扫描，
    # 避免配置错误被自动扫描静默掩盖）
    comm = respx.get(f"{BASE}/apihub/wapi/getAllCommunity").mock(
        return_value=httpx.Response(200, json=COMMUNITY_RAW))
    a = NteAdapter(Settings(nte_enabled=True, nte_events=[
        {"name": "坏项", "start": "2026/08/27 04:00",
         "end": "2026-09-14 03:59"},
        MANUAL_EVENTS[0],
    ]))
    r = await a.fetch(Capability.EVENTS)
    assert r.ok is True
    assert [e.name for e in r.payload] == ["第二索拉·诡影迷踪"]
    assert comm.calls.call_count == 0


@respx.mock
async def test_fetch_roles_returns_normalized_payload():
    respx.get(f"{BASE}/usercenter/api/v2/getGameRoles").mock(
        return_value=httpx.Response(200, json=ROLES_RAW))
    route = respx.get(f"{BASE}/apihub/awapi/yh/characters").mock(
        return_value=httpx.Response(200, json=CHARACTERS_RAW))
    a = _configured()
    assert a.credentials_configured is True
    r = await a.fetch(Capability.ROLES)
    assert r.ok is True
    assert r.payload.entries[0].name == '角色甲'
    assert r.payload.entries[0].level == 80
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
    assert r.payload.completed == 120 and r.payload.total == 300
    assert route.calls.last.request.url.params["roleId"] == "77"


@respx.mock
async def test_fetch_gacha_ok():
    respx.get(f"{BASE}/usercenter/api/v2/getGameRoles").mock(
        return_value=httpx.Response(200, json=ROLES_RAW))
    respx.get(f"{BASE}/apihub/awapi/yh/characters").mock(
        return_value=httpx.Response(200, json=CHARACTERS_RAW))
    route = respx.get(f"{BASE}/apihub/awapi/yh/gacha").mock(
        return_value=httpx.Response(200, json=GACHA_RAW))
    a = _configured()
    r = await a.fetch(Capability.GACHA)
    assert r.ok is True
    assert r.payload.total_draws == 42 and r.payload.total_s == 1
    assert route.calls.last.request.headers["authorization"] == "acc"


@respx.mock
async def test_fetch_record_ok():
    respx.get(f"{BASE}/usercenter/api/v2/getGameRoles").mock(
        return_value=httpx.Response(200, json=ROLES_RAW))
    respx.get(f"{BASE}/usercenter/api/getUserFullInfo").mock(
        return_value=httpx.Response(200, json=FULL_INFO_RAW))
    route = respx.get(f"{BASE}/apihub/api/getGameRecordCard").mock(
        return_value=httpx.Response(200, json=RECORD_RAW))
    a = _configured()
    r = await a.fetch(Capability.RECORD)
    assert r.ok is True
    assert r.payload.cards[0].nickname == '玩家'
    assert route.calls.last.request.url.params["uid"] == "900001"


@respx.mock
async def test_session_expired_maps_to_recapture_hint():
    # 401 → "会话已失效"提示（402/403 同，客户端层已参数化覆盖）
    respx.get(f"{BASE}/usercenter/api/v2/getGameRoles").mock(
        return_value=httpx.Response(401))
    a = _configured()
    r = await a.fetch(Capability.ROLES)
    assert r.ok is False and "会话已失效，请在「社区账号」重新登录异环" in r.error


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
    assert adapter.capabilities == [Capability.ACCOUNT, Capability.STAMINA,
                                    Capability.ROLES, Capability.PROGRESS, Capability.EXPLORATION,
                                    Capability.GACHA, Capability.RECORD, Capability.EVENTS, Capability.ANNOUNCEMENT,
                                    Capability.REALESTATE, Capability.VEHICLES, Capability.TEAMS]


def test_registry_nte_disabled_skips_registration():
    reg = build_default_registry(Settings(wuwa_enabled=False,
                                          lol_enabled=False,
                                          nte_enabled=False))
    assert "nte" not in {a.game_id for a in reg.all()}


def test_gacha_record_intervals_reuse_news_seconds():
    assert interval_for(Capability.GACHA, Settings()) == 14400
    assert interval_for(Capability.RECORD, Settings()) == 14400
    assert interval_for(Capability.GACHA, Settings(news_seconds=60)) == 60


def test_events_interval_reuses_announcement_seconds():
    # 活动日历与公告同源（版本公告解析），轮询间隔复用 announcement_seconds
    assert interval_for(Capability.EVENTS, Settings()) == 3600
    assert interval_for(Capability.EVENTS, Settings(announcement_seconds=60)) == 60


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


async def test_base_dispatch_default_for_events():
    # EVENTS 进 dispatch map：未实现的适配器报"适配器未实现该能力"而非 KeyError
    class Dummy(BaseGameAdapter):
        game_id = "dummy"
        capabilities = [Capability.EVENTS]

    d = Dummy()
    d.credentials_configured = True
    r = await d.fetch(Capability.EVENTS)
    assert r.ok is False and "适配器未实现该能力" in r.error
