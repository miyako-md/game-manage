from datetime import datetime, timezone

from game_assistant.models import AnnouncementItem


def _dt(*vals):
    # findEventList 的 publishTime 是毫秒整数时间戳（2026-09-13 实测）：
    # int 或纯数字字符串且位数 >= 12 视为毫秒，放 ISO 解析之前；
    # ISO 字符串（含 -/: 等分隔符）不受影响，仍走 fromisoformat
    for v in vals:
        if v:
            if isinstance(v, int) or (isinstance(v, str) and v.isdigit()
                                      and len(v) >= 12):
                return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc)
            try:
                return datetime.fromisoformat(str(v))
            except ValueError:
                continue
    return None


def parse_announcement_list(raw: dict) -> list[AnnouncementItem]:
    """findEventList(eventType=3) 响应 → 公告列表（2026-09-13 实测校准）。

    data.list（data 也可能直接是数组）含 postTitle/publishTime（毫秒时间戳，经
    _dt 统一转 aware UTC）/postId/coverUrl；url 按 postId 拼论坛详情页。
    旧 /forum/list 论坛形状已废弃（鸣潮板块为社区板块，公告不走该接口）。
    """
    data = raw.get("data") or {}
    rows = data.get("list") if isinstance(data, dict) else data
    items = []
    for it in rows or []:
        items.append(AnnouncementItem(
            title=it.get("postTitle") or "",
            published_at=_dt(it.get("publishTime"), it.get("firstPublishTime")),
            url=f"https://www.kurobbs.com/forum/post/{it.get('postId')}"
            if it.get("postId") else None,
        ))
    return items
