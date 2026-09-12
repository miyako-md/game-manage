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


def test_parse_forum_post_schema():
    # Task 11 校准结论：findEventList 响应 data.list 含
    # postId/postTitle/publishTime/coverUrl（endpoints.py 注释）
    raw = {"code": 200, "data": {"list": [
        {"postId": "9001", "postTitle": "版本前瞻特别节目",
         "publishTime": "2026-09-10 19:30:00",
         "coverUrl": "https://img.kurobbs.com/upload/9001.jpg"},
        {"postId": "9002", "postTitle": "调频共鸣玩法说明",
         "publishTime": "2026-09-11 10:00:00"},
    ]}}
    items = parse_activity_list(raw)
    assert len(items) == 2
    assert items[0].title == "版本前瞻特别节目"
    assert items[0].start_at == datetime(2026, 9, 10, 19, 30, 0)
    assert items[0].url == "https://img.kurobbs.com/upload/9001.jpg"
    assert items[1].title == "调频共鸣玩法说明"
    assert items[1].url == "https://www.kurobbs.com/forum/post/9002"
