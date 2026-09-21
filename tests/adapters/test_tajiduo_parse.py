"""塔吉多解析器测试（匿名公告实测校准 + 防御式用例）。

2026-09-13 匿名实测（endpoints.py ⑥'）：getAllCommunity 的 data 直接是
社区数组，异环社区 id=2，"官方资讯"栏目 id=4；getOfficialPostList 返回
data.posts，post 键 subject/createTime（毫秒）/postId（int）。
防御式用例保留容器与键名回退（data.list / data.posts / data / 顶层
posts / list / 顶层本身数组；sTitle/title/postTitle 等），防上游改版。
"""
from datetime import datetime, timezone

from game_assistant.adapters.neverness.tajiduo import (
    parse_official_posts, resolve_official_column_id,
)

MS = 1789182000000  # 2026-09-12 前后（毫秒时间戳样例）


def test_parse_official_posts_calibrated_shape():
    # 实测形状（2026-09-13 在线校准，字段原样保留）：data.posts +
    # subject 标题 + createTime 毫秒时间戳 + postId（int，无 URL 键）
    raw = {"code": 0, "msg": "ok", "ok": True, "data": {
        "column": {"columnName": "官方资讯", "id": 4},
        "hasMore": True, "page": 0,
        "posts": [
            {"ai": False, "columnId": 4, "communityId": 2,
             "content": "《异环》1.3版本「雾中朔望星回」现已开启\n",
             "createTime": 1789184890182, "postId": 485925,
             "subject": "《异环》1.3版本「雾中朔望星回」现已开启",
             "type": 3, "uid": 10100006},
        ],
    }}
    items = parse_official_posts(raw)
    assert len(items) == 1
    assert items[0].title == "《异环》1.3版本「雾中朔望星回」现已开启"
    assert items[0].published_at == datetime.fromtimestamp(
        1789184890182 / 1000, tz=timezone.utc)
    assert items[0].url == "https://bbs.tajiduo.com/forum/post/485925"
    assert items[0].summary == ""  # content 全文不进摘要


def test_parse_official_posts_ms_timestamps_and_post_id_url():
    raw = {"code": 0, "data": {"list": [
        {"sTitle": "1.2版本更新公告", "sIdxTime": MS, "postId": "9001"},
        # 字符串毫秒时间戳同样处理；sUrl 直链优先于 postId 拼 URL
        {"sTitle": "维护完成公告", "sIdxTime": str(MS),
         "sUrl": "https://bbs.tajiduo.com/a/1"},
    ]}}
    items = parse_official_posts(raw)
    assert len(items) == 2
    assert items[0].title == "1.2版本更新公告"
    assert items[0].published_at == datetime.fromtimestamp(
        MS / 1000, tz=timezone.utc)
    assert items[0].url == "https://bbs.tajiduo.com/forum/post/9001"
    assert items[1].published_at == items[0].published_at
    assert items[1].url == "https://bbs.tajiduo.com/a/1"


def test_parse_official_posts_iso_and_key_fallback():
    raw = {"code": 0, "data": {"posts": [
        {"title": "ISO 空格时间", "publishTime": "2026-09-13 10:00:00",
         "jumpUrl": "//bbs.tajiduo.com/x"},
        {"postTitle": "createTime 回退", "createTime": "2026-09-12T08:30:00",
         "url": "https://bbs.tajiduo.com/y"},
        {"title": "无时间无链接", "postId": "7007"},
    ]}}
    items = parse_official_posts(raw)
    assert [i.title for i in items] == \
        ["ISO 空格时间", "createTime 回退", "无时间无链接"]
    assert items[0].published_at == datetime.fromisoformat("2026-09-13 10:00:00")
    assert items[0].url == "https://bbs.tajiduo.com/x"  # // 前缀补 https:
    assert items[1].published_at == datetime.fromisoformat("2026-09-12T08:30:00")
    assert items[1].url == "https://bbs.tajiduo.com/y"
    assert items[2].published_at is None
    assert items[2].url == "https://bbs.tajiduo.com/forum/post/7007"


def test_parse_official_posts_container_fallbacks():
    # data 即数组
    assert parse_official_posts(
        {"code": 0, "data": [{"title": "data 即数组"}]})[0].title == "data 即数组"
    # 顶层 posts / list / 顶层本身数组
    assert parse_official_posts(
        {"code": 0, "posts": [{"title": "顶层 posts"}]})[0].title == "顶层 posts"
    assert parse_official_posts(
        {"code": 0, "list": [{"title": "顶层 list"}]})[0].title == "顶层 list"
    assert parse_official_posts([{"title": "顶层本身数组"}])[0].title == "顶层本身数组"
    # 已知容器全缺失 → 空列表；raw 非 dict/list → 空列表
    assert parse_official_posts({"code": 0, "data": {"other": 1}}) == []
    assert parse_official_posts(None) == []
    assert parse_official_posts("bad") == []
    # 非 dict 行跳过
    rows = parse_official_posts(
        {"code": 0, "data": {"list": ["bad", None, {"title": "跳过非 dict"}]}})
    assert [r.title for r in rows] == ["跳过非 dict"]


def test_parse_official_posts_summary_fallback():
    raw = {"code": 0, "data": {"list": [
        {"title": "带摘要", "sDesc": "版本更新说明"},
        {"title": "无摘要"},
    ]}}
    items = parse_official_posts(raw)
    assert items[0].summary == "版本更新说明"
    assert items[1].summary == ""


def test_resolve_official_column_id_calibrated_shape():
    # 实测形状（2026-09-13）：data 为社区数组，栏目键为 columnName/id
    # （"官方资讯"→id=4），取异环社区子树而非幻塔社区
    raw = {"code": 0, "msg": "ok", "ok": True, "data": [
        {"id": 2, "name": "异环", "gameId": 1289, "state": 0,
         "columns": [
             {"columnName": "官方资讯", "communityId": 2, "id": 4,
              "showType": 3},
             {"columnName": "攻略互助", "communityId": 2, "id": 10,
              "showType": 2},
             {"columnName": "综合闲聊", "communityId": 2, "id": 2,
              "showType": 1},
         ]},
        {"id": 1, "name": "幻塔",
         "columns": [{"columnName": "海嘉德资讯", "communityId": 1, "id": 5}]},
    ]}
    assert resolve_official_column_id(raw) == "4"


def test_resolve_official_column_id_by_community_name():
    raw = {"code": 0, "data": {"list": [
        {"id": 1, "name": "其它社区",
         "columns": [{"columnId": 99, "name": "官方资讯"}]},
        {"id": 2, "name": "异环",
         "columns": [{"columnId": 12, "name": "官方资讯"},
                     {"columnId": 13, "name": "同人创作"}]},
    ]}}
    # 名称定位到异环社区，栏目取该社区下的"官方"（而非首个社区的 99）
    assert resolve_official_column_id(raw) == "12"


def test_resolve_official_column_id_by_id_fallback():
    # 社区名不含"异环"时回退 id==2（塔吉多社区 id）
    raw = {"code": 0, "data": {"list": [
        {"id": 2, "name": "NTE", "forums": [{"id": 31, "name": "官方公告"}]},
    ]}}
    assert resolve_official_column_id(raw) == "31"


def test_resolve_official_column_id_not_found():
    assert resolve_official_column_id({"code": 0, "data": {"list": [
        {"id": 1, "name": "别的游戏",
         "columns": [{"columnId": 9, "name": "官方资讯"}]}]}}) is None
    assert resolve_official_column_id({"code": 0}) is None
    assert resolve_official_column_id(None) is None
