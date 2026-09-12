from datetime import datetime

from game_assistant.models import ActivityItem


def _dt(*vals):
    for v in vals:
        if v:
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
