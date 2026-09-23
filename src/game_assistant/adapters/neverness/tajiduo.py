"""塔吉多响应解析（防御式 + 匿名公告实测校准）。

2026-09-13 匿名实测（见 endpoints.py ⑥'）：getAllCommunity 的 data 直接是
社区数组，异环社区 id=2，"官方资讯"栏目 id=4；getOfficialPostList 返回
data.posts，post 键 subject/createTime（毫秒）/postId（int）。
需凭据端点的版本化模型与解析器位于 data_models.py / parse.py，已于
2026-09-14 使用实际响应校准；此模块只负责匿名公告及历史工具函数。

解析函数对容器与键名仍做多级回退（data.list / data.posts / data /
顶层 posts / list；subject/sTitle/title/postTitle 等），保留对上游改版的防御。
"""
from game_assistant.adapters.neverness.endpoints import COMMUNITY_ID
from game_assistant.event_calendar import parse_ms_or_iso as _dt
from game_assistant.models import AnnouncementItem


def _extract_rows(raw) -> list:
    """容器形状防御式兼容：data.list / data.posts / data（数组）/
    顶层 posts / list / 顶层本身为数组。"""
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return []
    inner = raw.get("data")
    if isinstance(inner, dict):
        for key in ("list", "posts"):
            val = inner.get(key)
            if isinstance(val, list):
                return val
    elif isinstance(inner, list):
        return inner
    for key in ("posts", "list"):
        val = raw.get(key)
        if isinstance(val, list):
            return val
    return []


def _post_url(item: dict) -> str | None:
    """链接键回退：sUrl / url / jumpUrl；缺失时按 postId 拼社区详情页。

    实测 post 响应无任何 URL 键，只能按 postId 拼；bbs.tajiduo.com 帖子
    详情路由尚未验证（当时站点域名连接失败）。
    """
    for key in ("sUrl", "url", "jumpUrl"):
        url = item.get(key)
        if url:
            if url.startswith("//"):
                url = f"https:{url}"
            return url
    post_id = item.get("postId") or item.get("post_id") or item.get("id")
    if post_id:
        return f"https://bbs.tajiduo.com/forum/post/{post_id}"
    return None


def parse_official_posts(raw) -> list[AnnouncementItem]:
    """getOfficialPostList 响应 → AnnouncementItem 列表。

    实测形状：data.posts，标题键 subject，时间键 createTime（毫秒）。
    键名仍做多级回退：标题 subject/sTitle/title/postTitle；时间
    sIdxTime/publishTime/createTime（毫秒或 ISO）；摘要 sDesc/summary
    （实测 content 为帖子全文，不进摘要以免长文撑爆卡片）。
    """
    items = []
    for it in _extract_rows(raw):
        if not isinstance(it, dict):
            continue
        items.append(AnnouncementItem(
            title=it.get("subject") or it.get("sTitle") or it.get("title")
            or it.get("postTitle") or "",
            published_at=_dt(it.get("sIdxTime"), it.get("publishTime"),
                             it.get("createTime")),
            url=_post_url(it),
            summary=it.get("sDesc") or it.get("summary") or "",
        ))
    return items


def _iter_dicts(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _iter_dicts(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_dicts(v)


def _node_name(node: dict) -> str:
    return str(node.get("name") or node.get("title")
               or node.get("columnName") or node.get("communityName") or "")


def resolve_official_column_id(raw) -> str | None:
    """getAllCommunity 响应 → 异环社区"官方资讯"栏目 id。

    实测形状（2026-09-13，endpoints.py ⑥'）：data 为社区数组，异环社区
    name="异环"/id=2，栏目键 columnName/id（"官方资讯"→4）。仍保留深度
    遍历的防御式定位：① 名称含"异环"的节点优先，回退 id==COMMUNITY_ID
    （"2"）的节点；② 在该社区子树内找名称含"官方"且带 columnId/id 的节点。
    定位失败返回 None（调用方转为 TajiduoError，公告能力报明确错误）。
    """
    if not isinstance(raw, (dict, list)):
        return None
    community = None
    for node in _iter_dicts(raw):
        if "异环" in _node_name(node):
            community = node
            break
    if community is None:
        for node in _iter_dicts(raw):
            if str(node.get("id") or "") == COMMUNITY_ID:
                community = node
                break
    if community is None:
        return None
    for node in _iter_dicts(community):
        if "官方" not in _node_name(node):
            continue
        column_id = node.get("columnId") or node.get("id")
        if column_id:
            return str(column_id)
    return None
