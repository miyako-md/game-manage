from datetime import datetime

from game_assistant.adapters.wuthering_waves.events import parse_activity_list

RAW = {"code": 200, "data": [
    {"title": "版本限时活动", "startTime": "2026-09-01 10:00:00",
     "endTime": "2026-09-30 23:59:59", "url": "https://www.kurobbs.com/event/1"},
    {"title": "无时间条目"},
]}


def test_parse_activities():
    items = parse_activity_list(RAW)
    assert len(items) == 2
    assert items[0].title == "版本限时活动"
    assert items[0].end_at == datetime(2026, 9, 30, 23, 59, 59)
    assert items[1].end_at is None
