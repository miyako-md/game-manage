"""从版本公告正文解析游戏内活动（名称/起止时间）。

鸣潮与异环公告的日期写法一致：YYYY年M月D日HH:MM ~ YYYY年M月D日HH:MM
（服务器时间=UTC+8），共用本模块的行级扫描与日期解析。

- 鸣潮：findEventList(eventType=3) 找版本公告 → getPostDetail →
  postH5Content（H5 HTML）；
- 异环：getOfficialPostList(columnId=4) 找版本公告 → getPostFull →
  content（HTML 或明文，strip_html 对明文原样按行拆分）。

活动名行为 `[名称]类型`（如 `[群声共振模拟域]战斗活动`），其后 ≤6 行内
含"活动时间"的行提供起止区间；2026-09-13 实测样本见
tests/test_event_calendar.py 的 WUWA_36_LINES fixture。
"""
import html as _html
import re
from datetime import datetime, timedelta, timezone

from game_assistant.models import GameEvent

BEIJING_TZ = timezone(timedelta(hours=8))

# YYYY年M月D日HH:MM（月/日允许单位数；时:分固定 HH:MM 写法）
CN_DATE_RANGE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2}):(\d{1,2})")

# 活动名行：`[名称]类型`（类型紧随右括号、无空白；可为空 → category=None）
ACTIVITY_NAME_RE = re.compile(r"\[([^\]]+)\](\S*)")

# 活动名行之后、匹配"活动时间"行的回看窗口（实测样本间隔 ≤4 行，留余量）
EVENT_TIME_WINDOW = 6

_BLOCK_TAG_RE = re.compile(
    r"</?(?:p|div|section|article|li|tr|table|ul|ol|h[1-6]|blockquote)[^>]*>",
    re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(html: str) -> list[str]:
    """HTML/明文正文 → 非空行列表。

    块级标签与 <br> 转换行、去残余标签、&nbsp;/U+00A0 还原为空格、
    其余实体经 html.unescape 还原；空行压缩。
    """
    text = (html or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _BR_RE.sub("\n", text)
    text = _BLOCK_TAG_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = text.replace("&nbsp;", " ").replace("\xa0", " ")
    text = _html.unescape(text)
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def _cn_datetime(m: re.Match) -> datetime:
    y, mo, d, h, mi = (int(g) for g in m.groups())
    return datetime(y, mo, d, h, mi, tzinfo=BEIJING_TZ)


# 起止分隔符（实测为全角/半角波浪线；兼容"至/到"）
_RANGE_SEP_RE = re.compile(r"\s*[~～]|至|到")


def parse_cn_date_range(segment: str) -> tuple[datetime | None, datetime | None]:
    """从文本段解析 `起 ~ 止` 中文日期区间 → (start, end)，均为 aware UTC+8。

    按首个分隔符切分：分隔符前第一个日期=start，其后最后一个日期=end；
    开始为相对描述（"版本更新后"）时前半段无日期 → start=None；分隔符后
    侧无日期（如"待定"）→ end=None；无分隔符时整段视为一侧（单日期 →
    start=end=该日期）。
    """
    parts = _RANGE_SEP_RE.split(segment, maxsplit=1)
    left = list(CN_DATE_RANGE_RE.finditer(parts[0])) if parts else []
    right = (list(CN_DATE_RANGE_RE.finditer(parts[1]))
             if len(parts) > 1 else None)
    start = _cn_datetime(left[0]) if left else None
    if right is None:                     # 无分隔符
        end = _cn_datetime(left[-1]) if left else None
    elif right:                           # 分隔符后侧有日期
        end = _cn_datetime(right[-1])
    else:                                 # 分隔符后侧无日期
        end = None
    return start, end


def _category(suffix: str) -> str | None:
    # "限时勘察活动——雾隐阁特别勘察" 的破折号后半段是副标题，不是活动类型
    head = suffix.split("——", 1)[0]
    return head or None


def parse_events_from_lines(lines: list[str], source_post_id: str | None = None,
                            source_title: str | None = None) -> list[GameEvent]:
    """行序列扫描 → GameEvent 列表（互斥配对）。

    - 行首匹配 `[名称]类型` 视为活动名行；同名活动只产出一次；
    - 名行之后 EVENT_TIME_WINDOW 行内的第一个含"活动时间"行提供起止
      （该行被消费后不再配给其它活动名）；
    - 窗口内无"活动时间"行的活动名不产出事件（干扰行不含该前缀，不会被扫描）。
    """
    events: list[GameEvent] = []
    seen_names: set[str] = set()
    used_time_lines: set[int] = set()
    for i, line in enumerate(lines):
        m = ACTIVITY_NAME_RE.match(line)
        if not m or m.group(1) in seen_names:
            continue
        name = m.group(1)
        for j in range(i + 1, min(i + 1 + EVENT_TIME_WINDOW, len(lines))):
            if j in used_time_lines or "活动时间" not in lines[j]:
                continue
            seen_names.add(name)
            used_time_lines.add(j)
            start, end = parse_cn_date_range(lines[j])
            events.append(GameEvent(
                name=name, category=_category(m.group(2)),
                start_at=start, end_at=end,
                source_post_id=source_post_id, source_title=source_title))
            break
    return events


def _post_ts(value) -> int:
    # 列表时间的强弱比较用：毫秒整数/纯数字字符串优先，其余按 0（保序回退）
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def find_version_post(posts: list[dict], title_keys, id_key: str = "postId",
                      title_key: str = "postTitle",
                      time_key: str = "publishTime") -> dict | None:
    """帖子列表 → 版本公告帖（标题含任一关键词，取发布时间最新），无则 None。

    title_keys 传可迭代的关键词（也兼容单个字符串）；鸣潮传 id_key="postId"/
    title_key="postTitle"/time_key="publishTime"，异环传 "postId"/"subject"/
    "createTime"。
    """
    if isinstance(title_keys, str):
        title_keys = (title_keys,)
    pattern = re.compile("|".join(re.escape(k) for k in title_keys))
    best: dict | None = None
    best_ts = -1
    for it in posts or []:
        if not isinstance(it, dict):
            continue
        title = str(it.get(title_key) or "")
        if not pattern.search(title):
            continue
        ts = _post_ts(it.get(time_key))
        if ts > best_ts:
            best, best_ts = it, ts
    return best
