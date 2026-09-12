from datetime import datetime

from game_assistant.models import AnnouncementItem


def parse_announcement_list(raw: dict) -> list[AnnouncementItem]:
    data = raw.get("data") or {}
    rows = data.get("list") if isinstance(data, dict) else data
    items = []
    for it in rows or []:
        published = None
        if it.get("createTime"):
            try:
                published = datetime.fromisoformat(str(it["createTime"]))
            except ValueError:
                pass
        items.append(AnnouncementItem(
            title=it.get("title") or "",
            published_at=published,
            url=f"https://www.kurobbs.com/forum/post/{it.get('postId')}"
            if it.get("postId") else None,
        ))
    return items
