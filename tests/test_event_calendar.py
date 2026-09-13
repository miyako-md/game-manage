"""event_calendar 解析测试（fixture 取自 2026-09-13 实测的鸣潮 3.6 版本公告）。

真实样本：postId 1539678546104307712「蜃云灯影，凡尘剑心」3.6版本内容说明，
去标签后的行序列含 6 个 `[名称]类型` 活动名行 + `✦活动时间：…（服务器时间）`
时间行，以及不含"活动时间"前缀的干扰行（维护补偿等，不得误报）。
"""
from datetime import datetime

from game_assistant.event_calendar import (
    BEIJING_TZ,
    find_version_post,
    parse_cn_date_range,
    parse_events_from_lines,
    strip_html,
)
from game_assistant.models import GameEvent

# 3.6 版本公告去标签后的关键行序列（实测样本节选，保留行序与行文）：
# 活动 1~5 为绝对区间；若梦仍有回声为"3.6版本更新后"相对开始变体（start=None）。
WUWA_36_LINES = [
    "「蜃云灯影，凡尘剑心」版本活动内容一览",
    "[群声共振模拟域]战斗活动",
    "活动说明：完成模拟域挑战可获得奖励。",
    "✦活动时间：2026年8月22日10:00 ~ 2026年9月29日11:59（服务器时间）",
    "[第二索拉・诡影迷踪]休闲活动",
    "与第二索拉一起解开谜题。",
    "✦活动时间：2026年8月29日10:00 ~ 2026年9月29日03:59（服务器时间）",
    "[清弦纪流年]休闲活动",
    "弹奏琴弦，记录流年。",
    "✦活动时间：2026年8月22日10:00 ~ 2026年9月12日23:59（服务器时间）",
    "[若梦仍有回声]限时联机战斗活动",
    "联机击败强敌，赢取回声奖励。",
    "✦活动时间：3.6版本更新后 ~ 2026年9月29日03:59（服务器时间）",
    "[潮汐觅闻]限时勘察活动——雾隐阁特别勘察",
    "前往雾隐阁完成特别勘察任务。",
    "✦活动时间：2026年9月5日10:00 ~ 2026年9月29日11:59（服务器时间）",
    "[烟云赠礼]七日签到活动",
    "每日登录领取签到奖励。",
    "✦活动时间：2026年8月22日10:00 ~ 2026年9月2日03:59（服务器时间）",
    "以下为维护补偿说明（干扰行，不含\"活动时间\"前缀）：",
    "维护补偿：2026年8月20日06:00 ~ 2026年8月20日12:00（服务器时间），",
    "补偿将在邮件中发放。",
    "[数据更新]停服更新期间无法登录游戏。",
]

WUWA_36_H5 = (
    "<div class=\"content\"><p>「蜃云灯影，凡尘剑心」版本活动内容一览</p>"
    "<p>[群声共振模拟域]战斗活动</p>"
    "<p>活动说明：完成模拟域挑战可获得奖励。</p>"
    "<p>✦活动时间：2026年8月22日10:00&nbsp;~&nbsp;2026年9月29日11:59（服务器时间）</p>"
    "<p>[烟云赠礼]七日签到活动</p><br/>"
    "<p>每日登录领取签到奖励。</p>"
    "<p>✦活动时间：2026年8月22日10:00 ~ 2026年9月2日03:59（服务器时间）</p>"
    "</div>"
)


def _dt(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=BEIJING_TZ)


async def test_strip_html_blocks_to_lines():
    lines = strip_html(WUWA_36_H5)
    # 块级标签/<br> 换行、&nbsp; 还原为空格、空行压缩
    assert lines[0] == "「蜃云灯影，凡尘剑心」版本活动内容一览"
    assert "[群声共振模拟域]战斗活动" in lines
    time_line = next(ln for ln in lines if "活动时间" in ln)
    assert "\xa0" not in time_line and "2026年8月22日10:00 ~ 2026年9月29日11:59" in time_line


async def test_strip_html_plain_text_passthrough():
    text = "第一行\n\n\n第二行  \n第三行"
    assert strip_html(text) == ["第一行", "第二行", "第三行"]
    assert strip_html("") == []


async def test_parse_cn_date_range_basic_and_utc8():
    start, end = parse_cn_date_range(
        "✦活动时间：2026年8月22日10:00 ~ 2026年9月29日11:59（服务器时间）")
    assert start == _dt(2026, 8, 22, 10, 0)
    assert end == _dt(2026, 9, 29, 11, 59)
    assert start.tzinfo is not None and start.utcoffset().total_seconds() == 8 * 3600


async def test_parse_cn_date_range_single_digit_fields():
    # 单位数月/日/时 + 前导零分钟均兼容
    start, end = parse_cn_date_range("2026年9月5日9:05 ~ 2026年10月1日23:59")
    assert start == _dt(2026, 9, 5, 9, 5)
    assert end == _dt(2026, 10, 1, 23, 59)


async def test_parse_cn_date_range_first_start_last_end():
    # 段内 3 个日期：分隔符前第一个为开始、其后最后一个为结束（中间值忽略）
    seg = "2026年1月1日00:00、2026年1月15日12:00 至 2026年2月1日23:59"
    start, end = parse_cn_date_range(seg)
    assert start == _dt(2026, 1, 1, 0, 0)
    assert end == _dt(2026, 2, 1, 23, 59)


async def test_parse_cn_date_range_relative_start_is_none():
    # 变体：开始为相对描述、仅结束有日期 → (None, end)
    start, end = parse_cn_date_range(
        "✦活动时间：3.6版本更新后 ~ 2026年9月29日03:59（服务器时间）")
    assert start is None
    assert end == _dt(2026, 9, 29, 3, 59)


async def test_parse_cn_date_range_single_date_no_separator():
    # 无分隔符单日期：start=end=该日期
    start, end = parse_cn_date_range("活动时间：2026年1月1日00:00 起")
    assert start == end == _dt(2026, 1, 1, 0, 0)


async def test_parse_cn_date_range_open_end_is_none():
    # 分隔符后侧无日期（"待定"）：end=None
    start, end = parse_cn_date_range("2026年1月1日00:00 ~ 待定")
    assert start == _dt(2026, 1, 1, 0, 0)
    assert end is None


async def test_parse_cn_date_range_no_date_returns_none_pair():
    assert parse_cn_date_range("✦活动时间：敬请期待") == (None, None)


async def test_parse_events_real_36_announcement():
    events = parse_events_from_lines(
        WUWA_36_LINES, source_post_id="1539678546104307712",
        source_title="蜃云灯影，凡尘剑心")
    assert [e.name for e in events] == [
        "群声共振模拟域", "第二索拉・诡影迷踪", "清弦纪流年",
        "若梦仍有回声", "潮汐觅闻", "烟云赠礼"]
    assert all(isinstance(e, GameEvent) for e in events)
    by_name = {e.name: e for e in events}
    first = by_name["群声共振模拟域"]
    assert first.category == "战斗活动"
    assert first.start_at == _dt(2026, 8, 22, 10, 0)
    assert first.end_at == _dt(2026, 9, 29, 11, 59)
    assert first.source_post_id == "1539678546104307712"
    assert first.source_title == "蜃云灯影，凡尘剑心"
    assert by_name["第二索拉・诡影迷踪"].category == "休闲活动"
    assert by_name["若梦仍有回声"].category == "限时联机战斗活动"
    assert by_name["潮汐觅闻"].category == "限时勘察活动"  # 破折号副标题不并入
    assert by_name["清弦纪流年"].end_at == _dt(2026, 9, 12, 23, 59)
    assert by_name["潮汐觅闻"].end_at == _dt(2026, 9, 29, 11, 59)
    assert by_name["烟云赠礼"].end_at == _dt(2026, 9, 2, 3, 59)


async def test_parse_events_relative_start_variant_start_is_none():
    events = parse_events_from_lines(WUWA_36_LINES)
    ev = next(e for e in events if e.name == "若梦仍有回声")
    assert ev.start_at is None                     # "3.6版本更新后" 无具体日期
    assert ev.end_at == _dt(2026, 9, 29, 3, 59)


async def test_parse_events_interference_lines_not_matched():
    # 维护补偿/数据更新行含日期或方括号，但不得产出活动
    events = parse_events_from_lines(WUWA_36_LINES)
    names = [e.name for e in events]
    assert len(names) == len(set(names)) == 6
    assert "数据更新" not in names
    assert all("维护补偿" not in n for n in names)


async def test_parse_events_mutual_exclusion():
    # 活动名重复出现只配对一次；活动时间行被消费后不再复用
    lines = [
        "[活动甲]战斗活动",
        "✦活动时间：2026年1月1日00:00 ~ 2026年1月2日00:00",
        "[活动甲]战斗活动",  # 同名复现：不再产出第二条
        "再提一下活动甲的时间：2026年1月3日00:00 ~ 2026年1月4日00:00",
        "[活动乙]休闲活动",
        "[活动丙]休闲活动",  # 与乙共享的时间行：不重复消费
        "✦活动时间：2026年2月1日00:00 ~ 2026年2月2日00:00",
    ]
    events = parse_events_from_lines(lines)
    assert [e.name for e in events] == ["活动甲", "活动乙"]
    assert events[1].end_at == _dt(2026, 2, 2, 0, 0)


async def test_parse_events_name_without_time_window_skipped():
    # 活动名后 6 行内无"活动时间"行 → 不产出事件
    lines = [
        "[无时间活动]休闲活动",
        "描述一", "描述二", "描述三", "描述四", "描述五", "描述六",
        "✦活动时间：2026年1月1日00:00 ~ 2026年1月2日00:00",
    ]
    assert parse_events_from_lines(lines) == []


async def test_find_version_post_picks_latest():
    posts = [
        {"postId": "1", "postTitle": "2.6版本更新公告", "publishTime": 100},
        {"postId": "2", "postTitle": "蜃云灯影，凡尘剑心3.6版本内容说明",
         "publishTime": 300},
        {"postId": "3", "postTitle": "维护完成公告", "publishTime": 999},
    ]
    got = find_version_post(posts, ("版本内容说明", "版本更新公告"),
                            id_key="postId", title_key="postTitle",
                            time_key="publishTime")
    assert got is not None and got["postId"] == "2"


async def test_find_version_post_none_when_absent():
    posts = [{"postId": "3", "postTitle": "维护完成公告", "publishTime": 999}]
    assert find_version_post(posts, ("版本内容说明", "版本更新公告"),
                             title_key="postTitle", time_key="publishTime") is None
    assert find_version_post([], ("版本内容说明")) is None


async def test_find_version_post_tolerates_missing_time():
    # 时间键全部缺失按 0 处理：返回按列表顺序的第一个匹配；
    # 带时间戳的帖子优先于缺时间戳的帖子
    posts = [{"postId": "9", "subject": "1.5版本内容说明"},
             {"postId": "8", "subject": "1.4版本内容说明"}]
    got = find_version_post(posts, ("版本内容说明",), id_key="postId",
                            title_key="subject", time_key="createTime")
    assert got is not None and got["postId"] == "9"
    posts2 = [{"postId": "9", "subject": "1.5版本内容说明"},
              {"postId": "8", "subject": "1.4版本内容说明", "createTime": 50}]
    got2 = find_version_post(posts2, ("版本内容说明",), id_key="postId",
                             title_key="subject", time_key="createTime")
    assert got2 is not None and got2["postId"] == "8"
