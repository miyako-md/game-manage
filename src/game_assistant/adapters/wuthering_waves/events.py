from datetime import datetime, timezone

from game_assistant.models import ActivityItem


def _dt(*vals):
    for v in vals:
        if v:
            # findEventList 的 publishTime 是毫秒整数时间戳（2026-09-13 实测）：
            # int 或纯数字字符串且位数 >= 12 视为毫秒，放 ISO 解析之前；
            # ISO 字符串（含 -/: 等分隔符）不受影响，仍走 fromisoformat
            if isinstance(v, int) or (isinstance(v, str) and v.isdigit()
                                      and len(v) >= 12):
                return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc)
            try:
                return datetime.fromisoformat(str(v))
            except ValueError:
                continue
    return None


def parse_activity_list(raw: dict) -> list[ActivityItem]:
    # 兼容两种 schema：活动接口 title/startTime/endTime/url 与
    # findEventList 帖子流 postId/postTitle/publishTime/coverUrl（见 endpoints.py 校准注释）
    data = raw.get("data") or []
    if isinstance(data, dict):
        data = data.get("list") or []
    items = []
    for it in data:
        url = it.get("url") or it.get("postUrl") or it.get("coverUrl")
        if not url and it.get("postId"):
            url = f"https://www.kurobbs.com/forum/post/{it['postId']}"
        items.append(ActivityItem(
            title=it.get("title") or it.get("postTitle") or "",
            start_at=_dt(it.get("startTime"), it.get("beginTime"),
                         it.get("publishTime")),
            end_at=_dt(it.get("endTime"), it.get("overTime"),
                       it.get("publishTime")),
            url=url,
        ))
    return items
