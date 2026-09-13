"""LeagueOfLegendsAdapter 组装测试。

LCU 走 127.0.0.1 respx mock，凭据发现 monkeypatch 为受控值（adapter 模块级导入名）；
官网公告/资讯走 CMC 接口 mock（分类过滤由端点 target 参数完成，见 test_lol_news.py）。
"""
import httpx
import respx

import game_assistant.adapters.league_of_legends.adapter as adapter_mod
from game_assistant.adapters.league_of_legends.adapter import LeagueOfLegendsAdapter
from game_assistant.config import Settings
from game_assistant.models import AnnouncementItem, Capability

BASE = "https://127.0.0.1:54321"
SUMMONER = {"puuid": "P1", "gameName": "峡谷小毕", "summonerLevel": 160}

# 校准真实样本（截取自 target=24 公告分类，字段原样保留，见 test_lol_news.py）
NEWS_RAW = {"status": 1, "msg": "OK", "data": {
    "resultTotal": 2582, "resultPage": 1, "resultNum": 1,
    "result": [
        {"sTitle": "26.18版本更新公告", "sIdxTime": "2026-09-09 19:40:48",
         "sRedirectURL": "", "iDocID": "17021867528706072246",
         "sVID": None, "sDesc": "", "sTagIds": "1292"},
    ],
}}
# respx 路由按无 query 的基础 URL 匹配
NEWS_LIST_BASE = "https://apps.game.qq.com/cmc/zmMcnTargetContentList"


async def test_client_not_running(monkeypatch):
    monkeypatch.setattr(adapter_mod, "discover_lcu_credentials", lambda: None)
    a = LeagueOfLegendsAdapter(Settings())
    assert a.credentials_configured is True  # 无存储凭据，恒 True
    r = await a.fetch(Capability.ACCOUNT)
    assert r.ok is False and "LOL 客户端未运行" in r.error


@respx.mock
async def test_fetch_account_ok(monkeypatch):
    monkeypatch.setattr(adapter_mod, "discover_lcu_credentials",
                        lambda: ("54321", "tok"))
    respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        return_value=httpx.Response(200, json=SUMMONER))
    respx.get(f"{BASE}/lol-ranked/v1/ranked-stats/P1").mock(
        return_value=httpx.Response(200, json={"queueMap": {}}))
    a = LeagueOfLegendsAdapter(Settings())
    r = await a.fetch(Capability.ACCOUNT)
    assert r.ok is True and r.payload.nickname == "峡谷小毕"


@respx.mock
async def test_fetch_match_ok(monkeypatch):
    monkeypatch.setattr(adapter_mod, "discover_lcu_credentials",
                        lambda: ("54321", "tok"))
    respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        return_value=httpx.Response(200, json=SUMMONER))
    respx.get(f"{BASE}/lol-match-history/v1/products/lol/P1/matches").mock(
        return_value=httpx.Response(200, json={"games": {"games": []}}))
    a = LeagueOfLegendsAdapter(Settings())
    r = await a.fetch(Capability.MATCH)
    assert r.ok is True and r.payload == []


@respx.mock
async def test_ranked_stats_failure_not_fatal(monkeypatch):
    # 排位接口失败不致命：LcuError 捕获后 ranked_raw=None，账号信息仍可用
    monkeypatch.setattr(adapter_mod, "discover_lcu_credentials",
                        lambda: ("54321", "tok"))
    respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        return_value=httpx.Response(200, json=SUMMONER))
    respx.get(f"{BASE}/lol-ranked/v1/ranked-stats/P1").mock(
        return_value=httpx.Response(500, text="boom"))
    a = LeagueOfLegendsAdapter(Settings())
    r = await a.fetch(Capability.ACCOUNT)
    assert r.ok is True and r.payload.nickname == "峡谷小毕"
    assert r.payload.extra["ranked_solo"] is None


@respx.mock
async def test_fetch_announcement_ok():
    route = respx.get(NEWS_LIST_BASE).mock(
        return_value=httpx.Response(200, json=NEWS_RAW))
    a = LeagueOfLegendsAdapter(Settings())
    r = await a.fetch(Capability.ANNOUNCEMENT)
    assert r.ok is True and len(r.payload) == 1
    assert isinstance(r.payload[0], AnnouncementItem)
    assert r.payload[0].title == "26.18版本更新公告"
    # sRedirectURL 为空串 → 官方前端回退拼 detail.shtml?docid=
    assert (r.payload[0].url ==
            "https://lol.qq.com/news/detail.shtml?docid=17021867528706072246")
    assert route.calls.last.request.url.params["target"] == "24"  # 公告分类


@respx.mock
async def test_fetch_news_ok():
    route = respx.get(NEWS_LIST_BASE).mock(
        return_value=httpx.Response(200, json=NEWS_RAW))
    a = LeagueOfLegendsAdapter(Settings())
    r = await a.fetch(Capability.NEWS)
    assert r.ok is True and len(r.payload) == 1
    assert r.payload[0].title == "26.18版本更新公告"
    assert route.calls.last.request.url.params["target"] == "23"  # 综合分类
