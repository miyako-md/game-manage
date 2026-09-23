"""ChampionCatalog：解析 / 7 天文件缓存 / 网络失败降级（2026-09-13 实测形状，id=-1 占位项）。"""
import json
import time

import httpx
import respx

from game_assistant.adapters.league_of_legends.champions import (
    CHAMPION_SUMMARY_URL, ChampionCatalog,
)

RAW = [
    {"id": -1, "name": "无", "alias": "None",
     "squarePortraitPath": "/lol-game-data/assets/v1/champion-icons/-1.png"},
    {"id": 1, "name": "黑暗之女", "alias": "Annie",
     "squarePortraitPath": "/lol-game-data/assets/v1/champion-icons/1.png"},
    {"id": 157, "name": "疾风剑豪", "alias": "Yasuo",
     "squarePortraitPath": "/lol-game-data/assets/v1/champion-icons/157.png"},
]


def _write_cache(path, champions, fetched_at=None):
    path.write_text(json.dumps({
        "fetched_at": time.time() if fetched_at is None else fetched_at,
        "champions": champions,
    }, ensure_ascii=False), encoding="utf-8")


@respx.mock
async def test_fetch_parses_and_skips_placeholder(tmp_path):
    route = respx.get(CHAMPION_SUMMARY_URL).mock(
        return_value=httpx.Response(200, json=RAW))
    cat = await ChampionCatalog(cache_path=str(tmp_path / "c.json")).get()
    assert route.call_count == 1
    assert sorted(cat) == [1, 157]  # id=-1 占位项跳过
    assert cat == {1: {"name": "黑暗之女"}, 157: {"name": "疾风剑豪"}}


def test_name_for():
    catalog = {1: {"name": "黑暗之女"}}
    assert ChampionCatalog.name_for(catalog, 1) == "黑暗之女"
    assert ChampionCatalog.name_for(catalog, 999) is None
    assert ChampionCatalog.name_for(catalog, None) is None


@respx.mock
async def test_cache_written_then_reused_without_network(tmp_path):
    cache_file = tmp_path / "c.json"
    route = respx.get(CHAMPION_SUMMARY_URL).mock(
        return_value=httpx.Response(200, json=RAW))
    cat1 = await ChampionCatalog(cache_path=str(cache_file)).get()
    assert cache_file.exists()
    # 新实例 + 新鲜缓存 → 不再发网络请求（respx 同 pattern 重复注册返回
    # 同一路由对象，重新 mock 为 500 后 call_count 仍应停在首次请求的 1）
    route.mock(return_value=httpx.Response(500, text="boom"))
    cat2 = await ChampionCatalog(cache_path=str(cache_file)).get()
    assert route.call_count == 1
    assert cat2 == cat1


@respx.mock
async def test_stale_cache_used_when_network_fails(tmp_path):
    cache_file = tmp_path / "c.json"
    _write_cache(cache_file, {"157": {"name": "疾风剑豪", "icon": "x"}},
                 fetched_at=time.time() - 8 * 24 * 3600)  # 过期 8 天
    respx.get(CHAMPION_SUMMARY_URL).mock(
        return_value=httpx.Response(500, text="boom"))
    cat = await ChampionCatalog(cache_path=str(cache_file)).get()
    assert cat == {157: {"name": "疾风剑豪", "icon": "x"}}


@respx.mock
async def test_no_cache_network_fail_returns_empty(tmp_path):
    respx.get(CHAMPION_SUMMARY_URL).mock(
        return_value=httpx.Response(500, text="boom"))
    cat = await ChampionCatalog(cache_path=str(tmp_path / "c.json")).get()
    assert cat == {}  # 降级为空表，不得抛异常


@respx.mock
async def test_corrupt_cache_falls_back_to_fetch(tmp_path):
    cache_file = tmp_path / "c.json"
    cache_file.write_text("not json{", encoding="utf-8")
    respx.get(CHAMPION_SUMMARY_URL).mock(
        return_value=httpx.Response(200, json=RAW))
    cat = await ChampionCatalog(cache_path=str(cache_file)).get()
    assert sorted(cat) == [1, 157]
