from datetime import datetime, timezone

from game_assistant.adapters.wuthering_waves.announcements import parse_announcement_list

# 实测 findEventList(eventType=3) 响应形状（2026-09-13）：
# data.list 含 postTitle/publishTime（毫秒时间戳）/postId/coverUrl
RAW = {"code": 200, "msg": "success", "data": {"list": [
    {"id": "100", "postTitle": "2.6版本更新公告",
     "publishTime": 1789182000000, "firstPublishTime": 1789182000000,
     "postId": "123", "coverUrl": "https://img.kurobbs.com/upload/9001.jpg",
     "eventType": 3},
    {"id": "101", "postTitle": "维护完成公告", "publishTime": 0,
     "postId": "456", "eventType": 3},
]}}


def test_parse_announcements():
    items = parse_announcement_list(RAW)
    assert len(items) == 2
    assert items[0].title == "2.6版本更新公告"
    # 毫秒时间戳统一转 aware UTC（events._dt 口径）
    assert items[0].published_at == datetime.fromtimestamp(1789182000, tz=timezone.utc)
    assert items[0].url == "https://www.kurobbs.com/forum/post/123"
    # publishTime=0 视为缺失，且无 firstPublishTime 兜底 → published_at 为 None
    assert items[1].published_at is None
    assert items[1].url == "https://www.kurobbs.com/forum/post/456"


def test_parse_announcements_data_as_list():
    # data 也可能直接是数组（events.py 同款双形状兼容）
    raw = {"code": 200, "data": [{"postTitle": "数组形式公告", "postId": "789"}]}
    items = parse_announcement_list(raw)
    assert len(items) == 1
    assert items[0].title == "数组形式公告"
    assert items[0].published_at is None
    assert items[0].url == "https://www.kurobbs.com/forum/post/789"
