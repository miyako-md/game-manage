"""官网公告/资讯客户端与解析测试。

fixture 为 Task 7 Step 5 在线校准真实样本（2026-09-13 实测
apps.game.qq.com/cmc/zmMcnTargetContentList?target=24，即"公告"tab），见 endpoints.py 注释。
"""
import ssl
from datetime import datetime

import httpx
import pytest
import respx

from game_assistant.adapters.league_of_legends.endpoints import (
    NEWS_CATEGORY_IDS, NEWS_LIST_URL, NEWS_PAGE,
)
from game_assistant.adapters.league_of_legends.lol_news import (
    LoLNewsClient, LoLNewsError, parse_news_json,
)

# 校准真实样本（截取自 target=24 公告分类，字段原样保留）
RAW = {"status": 1, "msg": "OK", "data": {
    "resultTotal": 2582, "resultPage": 1, "resultNum": 3,
    "result": [
        {"sTitle": "26.18版本更新公告", "sIdxTime": "2026-09-09 19:40:48",
         "sRedirectURL": "https://lol.qq.com/gicp/news/410/37096116.html",
         "iDocID": "17021867528706072246", "sVID": None, "sDesc": "",
         "sTagIds": "1561,2821,2760,2122,1292", "iNewsId": "37096118"},
        {"sTitle": "幸运之门·海之歌活动开启", "sIdxTime": "2026-09-13 09:45:25",
         "sRedirectURL": "", "iDocID": "17083628231197355254",
         "sVID": None, "sDesc": "", "sTagIds": "1292", "iNewsId": "37096429"},
        {"sTitle": "峡谷之巅2026第二赛段奖励公告", "sIdxTime": "2026-09-11 10:58:07",
         "sRedirectURL": "", "iDocID": "16574079340694607129",
         "sVID": None, "sDesc": "", "sTagIds": "1292", "iNewsId": "37096249"},
    ],
}}

# respx 路由按无 query 的基础 URL 匹配（NEWS_LIST_URL 带 {page} 占位模板）
NEWS_LIST_BASE = "https://apps.game.qq.com/cmc/zmMcnTargetContentList"


def test_parse_news_json_calibrated():
    items = parse_news_json(RAW, "公告")
    assert len(items) == 3
    assert items[0].title == "26.18版本更新公告"
    assert items[0].published_at == datetime(2026, 9, 9, 19, 40, 48)
    assert items[0].url == "https://lol.qq.com/gicp/news/410/37096116.html"
    assert items[2].title == "峡谷之巅2026第二赛段奖励公告"
    assert items[2].published_at == datetime(2026, 9, 11, 10, 58, 7)


def test_parse_news_json_fallback_url_from_docid():
    # 校准：公告 tab 多数条目 sRedirectURL 为空串，官方前端回退拼 detail.shtml?docid=
    items = parse_news_json(RAW, "公告")
    assert items[1].url == "https://lol.qq.com/news/detail.shtml?docid=17083628231197355254"
    assert items[2].url == "https://lol.qq.com/news/detail.shtml?docid=16574079340694607129"


def test_parse_news_json_video_fallback_url():
    raw = {"data": {"result": [
        {"sTitle": "视频条目", "sIdxTime": "2026-09-10 08:00:00",
         "sRedirectURL": "", "sVID": "v123", "iDocID": "42"},
    ]}}
    items = parse_news_json(raw, "综合")
    assert items[0].url == "https://lol.qq.com/v/v2/detail.shtml?docid=42"


def test_parse_news_json_cross_items_shape():
    # 备用端点 cmc/cross/toc 的形状：data.items
    raw = {"msg": "success", "data": {"total": 2016, "items": [
        {"sTitle": "秒杀能力直线提升 Faker岚切克烈全解析",
         "sIdxTime": "2018-07-15 11:30:02", "sRedirectURL": "",
         "sVID": "", "iDocID": "14813918159521679375", "sDesc": "攻略解析"},
    ]}}
    items = parse_news_json(raw, "综合")
    assert len(items) == 1
    assert items[0].title == "秒杀能力直线提升 Faker岚切克烈全解析"
    assert items[0].published_at == datetime(2018, 7, 15, 11, 30, 2)
    assert items[0].url == "https://lol.qq.com/news/detail.shtml?docid=14813918159521679375"
    assert items[0].summary == "攻略解析"


def test_parse_news_json_legacy_assumed_shape():
    # Task 7 简报的假设形状（sDate/sUrl/title）仍需兼容
    raw = {"newsList": [
        {"title": "26.18版本更新公告", "sDate": "2026-09-11",
         "sUrl": "https://lol.qq.com/news/detail.shtml?nid=1"},
    ]}
    items = parse_news_json(raw, "公告")
    assert len(items) == 1
    assert items[0].title == "26.18版本更新公告"
    assert items[0].published_at == datetime(2026, 9, 11)
    assert items[0].url == "https://lol.qq.com/news/detail.shtml?nid=1"


def test_parse_news_json_root_list_and_bad_date():
    raw = [{"sTitle": "残缺条目", "sIdxTime": "not-a-date", "iDocID": "42"}]
    items = parse_news_json(raw, "公告")
    assert len(items) == 1
    assert items[0].published_at is None
    assert items[0].url == "https://lol.qq.com/news/detail.shtml?docid=42"


def test_parse_news_json_empty_shape_returns_empty():
    assert parse_news_json({}, "公告") == []
    assert parse_news_json({"data": "garbage"}, "公告") == []


def test_parse_news_json_protocol_relative_url():
    raw = {"data": {"result": [
        {"sTitle": "协议相对链接", "sIdxTime": "2026-09-10 08:00:00",
         "sRedirectURL": "//lol.qq.com/act/foo/index.html"},
    ]}}
    items = parse_news_json(raw, "公告")
    assert items[0].url == "https://lol.qq.com/act/foo/index.html"


@respx.mock
async def test_fetch_json_ok():
    route = respx.get(NEWS_LIST_BASE).mock(
        return_value=httpx.Response(200, json=RAW))
    async with LoLNewsClient() as client:
        data = await client.fetch_json(NEWS_LIST_URL)
    assert data["data"]["result"][0]["sTitle"] == "26.18版本更新公告"
    req = route.calls.last.request
    assert req.headers["Referer"] == "https://lol.qq.com/"
    assert "Mozilla/5.0" in req.headers["User-Agent"]


@respx.mock
async def test_fetch_json_unwraps_jsonp():
    # 带 r0=jsonp 时上游返回 callback({...}) 包裹（校准实测，回调参数名 r1）
    body = 'callback(' + httpx.Response(200, json=RAW).text + ')'
    respx.get(NEWS_LIST_BASE).mock(
        return_value=httpx.Response(200, text=body,
                                    headers={"content-type": "text/javascript"}))
    async with LoLNewsClient() as client:
        data = await client.fetch_json(NEWS_LIST_URL)
    assert data["data"]["resultNum"] == 3


@respx.mock
async def test_fetch_json_500_raises_lol_news_error():
    respx.get(NEWS_LIST_BASE).mock(
        return_value=httpx.Response(500, text="Internal Server Error"))
    async with LoLNewsClient() as client:
        with pytest.raises(LoLNewsError):
            await client.fetch_json(NEWS_LIST_URL)


@respx.mock
async def test_fetch_json_non_dict_raises_lol_news_error():
    respx.get(NEWS_LIST_BASE).mock(
        return_value=httpx.Response(200, json=["unexpected"]))
    async with LoLNewsClient() as client:
        with pytest.raises(LoLNewsError) as ei:
            await client.fetch_json(NEWS_LIST_URL)
    assert "结构" in ei.value.message


@respx.mock
async def test_fetch_json_network_error_raises_lol_news_error():
    respx.get(NEWS_LIST_BASE).mock(side_effect=httpx.ConnectError("boom"))
    async with LoLNewsClient() as client:
        with pytest.raises(LoLNewsError):
            await client.fetch_json(NEWS_LIST_URL)


@respx.mock
async def test_fetch_page_gbk_decode():
    respx.get(NEWS_PAGE).mock(return_value=httpx.Response(
        200, content="英雄联盟官方公告".encode("gbk"),
        headers={"content-type": "text/html; charset=gbk"}))
    async with LoLNewsClient() as client:
        html = await client.fetch_page(NEWS_PAGE)
    assert "英雄联盟官方公告" in html


@respx.mock
async def test_fetch_news_builds_category_url():
    route = respx.get(NEWS_LIST_BASE).mock(
        return_value=httpx.Response(200, json=RAW))
    async with LoLNewsClient() as client:
        await client.fetch_news("公告")
        params = route.calls.last.request.url.params
        assert params["target"] == NEWS_CATEGORY_IDS["公告"] == "24"
        assert params["page"] == "1"
        assert params["num"] == "16"
        assert params["source"] == "web_pc"
        await client.fetch_news("综合", page=2, num=5)
        params = route.calls.last.request.url.params
        assert params["target"] == NEWS_CATEGORY_IDS["综合"] == "23"
        assert params["page"] == "2"
        assert params["num"] == "5"


async def test_fetch_news_unknown_category_raises():
    async with LoLNewsClient() as client:
        with pytest.raises(LoLNewsError):
            await client.fetch_news("不存在的分类")


def test_ssl_verification_enabled():
    # 公网请求必须走正常 SSL 校验，与 LcuClient 的 verify=False 完全隔离
    client = LoLNewsClient()  # 未发请求，无连接需释放
    ctx = client._client._transport._pool._ssl_context
    assert ctx.verify_mode == ssl.CERT_REQUIRED
