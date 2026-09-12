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
    data = raw.get("data") or []
    if isinstance(data, dict):
        data = data.get("list") or []
    items = []
    for it in data:
        items.append(ActivityItem(
            title=it.get("title") or "",
            start_at=_dt(it.get("startTime"), it.get("beginTime")),
            end_at=_dt(it.get("endTime"), it.get("overTime")),
            url=it.get("url") or it.get("postUrl"),
        ))
    return items
