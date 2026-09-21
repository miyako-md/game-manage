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


HISTORY_GAME = {
    "gameId": 111, "queueId": 450, "gameMode": "ARAM",
    "gameCreation": 1788525600000, "gameDuration": 1234,
    "teams": [{"teamId": 100, "win": "Win"}],
    "participantIdentities": [
        {"participantId": 1, "player": {"puuid": "P1"}}],
    "participants": [
        {"participantId": 1, "championId": 157, "teamId": 100,
         "stats": {"kills": 22, "deaths": 3, "assists": 10, "win": True,
                   "totalDamageDealtToChampions": 50000}}],
}


class _FakeCatalog:
    """替身 ChampionCatalog：返回受控目录，不碰网络/缓存文件。"""

    catalog: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def get(self) -> dict:
        return type(self).catalog


async def test_stats_capability_registered(monkeypatch):
    a = LeagueOfLegendsAdapter(Settings())
    assert Capability.STATS in a.capabilities
    # dispatch 走 fetch_stats（客户端未运行路径），而非"不支持该能力"
    monkeypatch.setattr(adapter_mod, "discover_lcu_credentials", lambda: None)
    r = await a.fetch(Capability.STATS)
    assert r.ok is False and "LOL 客户端未运行" in r.error


@respx.mock
async def test_fetch_stats_ok(monkeypatch):
    monkeypatch.setattr(adapter_mod, "discover_lcu_credentials",
                        lambda: ("54321", "tok"))
    monkeypatch.setattr(adapter_mod, "ChampionCatalog", _FakeCatalog)
    _FakeCatalog.catalog = {157: {"name": "疾风剑豪", "icon": None}}
    respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        return_value=httpx.Response(200, json=SUMMONER))
    respx.get(f"{BASE}/lol-match-history/v1/products/lol/P1/matches").mock(
        return_value=httpx.Response(200, json={"games": {"games": [HISTORY_GAME]}}))
    a = LeagueOfLegendsAdapter(Settings())
    r = await a.fetch(Capability.STATS)
    assert r.ok is True
    s = r.payload
    assert (s.total_games, s.wins, s.winrate) == (1, 1, 100.0)
    assert s.avg_kills == 22 and s.avg_deaths == 3 and s.avg_assists == 10
    assert s.top_champions[0].champion_name == "疾风剑豪"  # catalog 命名
    assert s.records[0] == {"label": "单场最高击杀", "value": "22", "match_id": "111"}


@respx.mock
async def test_fetch_stats_catalog_degrades_to_empty(monkeypatch):
    # 英雄目录失败降级 {} → 常用英雄显示"英雄 #id"，统计仍成功
    monkeypatch.setattr(adapter_mod, "discover_lcu_credentials",
                        lambda: ("54321", "tok"))
    monkeypatch.setattr(adapter_mod, "ChampionCatalog", _FakeCatalog)
    _FakeCatalog.catalog = {}
    respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        return_value=httpx.Response(200, json=SUMMONER))
    respx.get(f"{BASE}/lol-match-history/v1/products/lol/P1/matches").mock(
        return_value=httpx.Response(200, json={"games": {"games": [HISTORY_GAME]}}))
    a = LeagueOfLegendsAdapter(Settings())
    r = await a.fetch(Capability.STATS)
    assert r.ok is True
    assert r.payload.top_champions[0].champion_name == "英雄 #157"


@respx.mock
async def test_fetch_match_detail_ok(monkeypatch):
    monkeypatch.setattr(adapter_mod, "discover_lcu_credentials",
                        lambda: ("54321", "tok"))
    monkeypatch.setattr(adapter_mod, "ChampionCatalog", _FakeCatalog)
    _FakeCatalog.catalog = {}
    respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        return_value=httpx.Response(200, json=SUMMONER))
    respx.get(f"{BASE}/lol-match-history/v1/games/987654321").mock(
        return_value=httpx.Response(200, json={
            "gameId": 987654321, "gameMode": "CLASSIC",
            "gameCreation": 1788525600000, "gameDuration": 2135,
            "teams": [{"teamId": 100, "win": "Win"},
                      {"teamId": 200, "win": "Fail"}],
            "participantIdentities": [
                {"participantId": 1, "player": {"puuid": "P1", "gameName": "峡谷小毕"}},
                {"participantId": 2, "player": {"puuid": "P2", "gameName": "对手"}}],
            "participants": [
                {"participantId": 1, "championId": 157, "teamId": 100,
                 "stats": {"kills": 8, "deaths": 3, "assists": 10, "win": True,
                           "champLevel": 18, "goldEarned": 12000,
                           "item0": 1001, "item1": 0, "item2": 3003,
                           "item3": 0, "item4": 0, "item5": 0, "item6": 3340,
                           "totalDamageDealtToChampions": 20030}},
                {"participantId": 2, "championId": 22, "teamId": 200,
                 "stats": {"kills": 2, "deaths": 8, "assists": 4, "win": False,
                           "champLevel": 15, "goldEarned": 9000}},
            ]}))
    a = LeagueOfLegendsAdapter(Settings())
    r = await a.fetch_match_detail("987654321")
    assert r.ok is True
    d = r.payload
    assert d.match_id == "987654321" and d.mode == "CLASSIC"
    assert [t.team_id for t in d.teams] == [100, 200]  # 我方在前
    me = d.teams[0].participants[0]
    assert me.is_own is True and me.role_name == "峡谷小毕"
    assert me.items == [1001, 3003, 3340] and me.damage == 20030
    assert me.champion_name is None  # catalog 为空 → 前端回退"英雄 #id"


@respx.mock
async def test_fetch_match_detail_client_not_running(monkeypatch):
    monkeypatch.setattr(adapter_mod, "discover_lcu_credentials", lambda: None)
    a = LeagueOfLegendsAdapter(Settings())
    r = await a.fetch_match_detail("987654321")
    assert r.ok is False and "LOL 客户端未运行" in r.error
