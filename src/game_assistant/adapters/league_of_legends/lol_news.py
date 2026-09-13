"""英雄联盟官网新闻/公告客户端与解析。

校准结论（Task 7 Step 5，2026-09-13 实测，证据与端点常量见 endpoints.py）：
- news/index.shtml 为 JS 动态渲染的 GBK 页面，HTML 内无新闻数据；
- 真实数据源是 /v3/js/newslist.js 引用的腾讯 CMC 内容接口，同一端点按 target
  参数区分分类（23=综合 24=公告，见 NEWS_CATEGORY_IDS）；
- 条目真实键名：sTitle / sIdxTime / sRedirectURL / iDocID / sVID / sDesc；
  sRedirectURL 为空时按官方前端逻辑回退拼 detail.shtml?docid={iDocID}。
解析函数对键名与响应形状做防御式兼容（含 Task 7 简报的假设形状）。
"""
import json
import re
from datetime import datetime

import httpx

from game_assistant.adapters.league_of_legends.endpoints import (
    NEWS_CATEGORY_IDS, NEWS_LIST_URL, NEWS_PAGE,
)
from game_assistant.models import AnnouncementItem

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Referer": "https://lol.qq.com/",
}

# r0=jsonp 时上游返回 callback({...}) 包裹（回调参数名 r1）
_JSONP_RE = re.compile(r"^\s*[\w$]+\((.*)\)\s*;?\s*$", re.S)


class LoLNewsError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class LoLNewsClient:
    """官网新闻客户端。公网请求走 httpx 默认 SSL 校验（与 LcuClient 的
    verify=False 完全隔离，不得复用其配置）。"""

    def __init__(self):
        self._client = httpx.AsyncClient(headers=_HEADERS, timeout=15)

    async def fetch_json(self, url: str) -> dict:
        try:
            resp = await self._client.get(url)
        except httpx.HTTPError as e:
            raise LoLNewsError(f"网络错误: {type(e).__name__}") from e
        if resp.status_code != 200:
            raise LoLNewsError(f"HTTP {resp.status_code}")
        try:
            data = json.loads(resp.text)
        except ValueError:
            m = _JSONP_RE.match(resp.text)
            if not m:
                raise LoLNewsError("响应非 JSON") from None
            try:
                data = json.loads(m.group(1))
            except ValueError as e:
                raise LoLNewsError("响应非 JSON") from e
        if not isinstance(data, dict):
            raise LoLNewsError("响应结构异常")
        return data

    async def fetch_page(self, url: str) -> str:
        """官网页面为 GBK 编码，按字节解码避免 charset 误判乱码。"""
        try:
            resp = await self._client.get(url)
        except httpx.HTTPError as e:
            raise LoLNewsError(f"网络错误: {type(e).__name__}") from e
        if resp.status_code != 200:
            raise LoLNewsError(f"HTTP {resp.status_code}")
        return resp.content.decode("gbk", errors="replace")

    async def fetch_news(self, category: str = "公告", page: int = 1,
                         num: int = 16) -> dict:
        """按分类拉取官网新闻列表（分类过滤由端点 target 参数完成）。"""
        try:
            target = NEWS_CATEGORY_IDS[category]
        except KeyError:
            raise LoLNewsError(
                f"未知分类: {category}，已知: {sorted(NEWS_CATEGORY_IDS)}") from None
        return await self.fetch_json(
            NEWS_LIST_URL.format(page=page, num=num, target=target))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "LoLNewsClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()


def _extract_list(data: dict) -> list:
    """兼容多种响应形状。校准真实形状为前两种，其余为防御式回退：
    - {"data": {"result": [...]}}   zmMcnTargetContentList（校准主路径）
    - {"data": {"items": [...]}}    cmc/cross/toc（备用端点）
    - {"data": {"newsList"/"list": [...]}}、{"newsList"/"list": [...]}、data 本身是 list
    """
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    inner = data.get("data")
    if isinstance(inner, dict):
        for key in ("result", "items", "newsList", "list"):
            val = inner.get(key)
            if isinstance(val, list):
                return val
    for key in ("newsList", "result", "items", "list"):
        val = data.get(key)
        if isinstance(val, list):
            return val
    return []


def _dt(*vals):
    for v in vals:
        if v:
            try:
                return datetime.fromisoformat(str(v))
            except ValueError:
                continue
    return None


def _detail_url(item: dict) -> str | None:
    """链接键防御式回退；sRedirectURL 为空时按官方前端逻辑用 iDocID 拼详情页。"""
    for key in ("sRedirectURL", "sUrl", "url", "jumpUrl", "link"):
        url = item.get(key)
        if url:
            if url.startswith("//"):
                url = f"https:{url}"
            return url
    doc_id = item.get("iDocID") or item.get("docId") or item.get("nid")
    if doc_id:
        if item.get("sVID"):
            return f"https://lol.qq.com/v/v2/detail.shtml?docid={doc_id}"
        return f"https://lol.qq.com/news/detail.shtml?docid={doc_id}"
    return None


def parse_news_json(data: dict, category: str = "公告") -> list[AnnouncementItem]:
    """解析官网新闻列表响应为 AnnouncementItem。

    category（"公告"/"综合"等，映射见 NEWS_CATEGORY_IDS）：校准确认分类过滤由端点
    target 参数在服务端完成（公告条目 sTagIds 中并不含分类 id，无法客户端过滤），
    此参数仅为保持调用签名，不做二次过滤。
    """
    items = []
    for it in _extract_list(data):
        if not isinstance(it, dict):
            continue
        title = it.get("sTitle") or it.get("title") or ""
        published_at = _dt(it.get("sIdxTime"), it.get("l_time"),
                           it.get("sDate"), it.get("createDate"),
                           it.get("date"), it.get("time"))
        items.append(AnnouncementItem(
            title=title,
            published_at=published_at,
            url=_detail_url(it),
            summary=it.get("sDesc") or it.get("summary") or "",
        ))
    return items
