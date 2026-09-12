from game_assistant.adapters.wuthering_waves.announcements import parse_announcement_list

RAW = {"code": 200, "data": {"list": [
    {"postId": "123", "title": "2.6版本更新公告", "createTime": "2026-09-10 12:00:00"},
    {"postId": "456", "title": "维护完成公告"},
]}}


def test_parse_announcements():
    items = parse_announcement_list(RAW)
    assert len(items) == 2
    assert items[0].url == "https://www.kurobbs.com/forum/post/123"
    assert items[0].published_at is not None
    assert items[1].published_at is None
