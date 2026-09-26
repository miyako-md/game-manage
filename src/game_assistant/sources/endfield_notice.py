"""终末地官方公告 → 活动日历。B站全文动态与官网公告使用同一格式。

和鸣潮、异环不同：版本用「版本名」标识，条目标题形如 `1.「冬猎」特许寻访`，时间行形如
`开放时间：<开始> - <结束>（服务器时间）`。结束时间常写作“版本更新维护前”或依附于其他寻访，
只有下个版本的维护预告给出具体时刻后才补全，不虚构截止时间。样本见 tests/test_endfield_notice.py。
"""
import re
from datetime import datetime, timezone

from .public_content import BJ, _same_event, content_title

VERSION_POST = re.compile(r'「([^」]+)」版本更新说明')
MAINTENANCE_NOTICE = re.compile(r'「([^」]+)」版本(?:更新维护预告|预下载与更新预告)')
DECLARED_VERSION = re.compile(r'「([^」]+)」版本(?:更新|开启|期间)')
DATE_TIME = re.compile(r'(20\d{2})\s*[/年.-]\s*(\d{1,2})\s*[/月.-]\s*(\d{1,2})\s*日?\s*(\d{1,2})[:：](\d{2})')
NUMBERED = re.compile(r'^\d+\s*[.、．]\s*「([^」]+)」\s*(.*)$')
STANDALONE = re.compile(r'^▼//\s*「([^」]+)」\s*(.*)$')
NESTED = re.compile(r'^○\s*「([^」]+)」\s*(.*)$')
ALONGSIDE = re.compile(r'^同时.{0,30}?开放「([^」]+)」\s*(.*)$')
TIME_LINE = re.compile(r'^[·•・]?\s*(.{0,20}?)(开放时间|活动时间|赛季更新|更新时间)\s*[：:]\s*(.*)$')
OUT_OF_SCOPE = re.compile(r'^▼//\s*(?:更新维护|优化|调整|问题修复|修复)')
RELATIVE_START = re.compile(r'版本(?:更新|开启)后|公测开启后')
DEPENDENT_END = re.compile(r'于[^，,]*后结束.*$')
UP_ITEM = re.compile(r'6星(?:干员|武器)为?【([^】]+)】')
PARENTHESES = re.compile(r'（[^）]*）|\([^)]*\)')
RANGE_SEPARATORS = '-~～—–至'


def _lines(post):
    return [line.strip() for line in (post.get('body') or '').splitlines() if line.strip()]


def _dt(match):
    year, month, day, hour, minute = (int(value) for value in match.groups())
    return datetime(year, month, day, hour, minute, tzinfo=BJ)


def _category(name, suffix, section):
    if '申领' in name + suffix or '限时特卖' in suffix:
        return '武器申领'
    if '寻访' in suffix:
        return '角色寻访'
    if '签到' in name + suffix:
        return '签到活动'
    if '活动' in suffix:
        return '限时活动'
    return '玩法更新' if '玩法' in section + suffix else '限时活动'


def _items(lines):
    """行序列 → [{name, category, lines}]；标题之间的行归前一个条目。"""
    items, current, parent, section, in_scope = [], None, '', '', True
    for line in lines:
        if line.startswith('▼//') and not STANDALONE.match(line):
            in_scope, current, section = not OUT_OF_SCOPE.match(line), None, ''
            continue
        if line.startswith('■'):
            current, parent, section = None, '', line
            continue
        if not in_scope:
            continue
        name = suffix = None
        for pattern in (NUMBERED, STANDALONE, ALONGSIDE):
            match = pattern.match(line)
            if match:
                name, suffix = match[1], match[2]
                parent = name if pattern is NUMBERED else parent
                break
        nested = NESTED.match(line)
        if nested and parent:
            name, suffix = f'{parent}·{nested[1]}', nested[2]
        if name:
            current = dict(name=name, category=_category(name, suffix, section), lines=[])
            items.append(current)
        elif current is not None:
            current['lines'].append(line)
    return items


def _split_range(text):
    depth = 0
    for index, char in enumerate(text):
        if char == '「':
            depth += 1
        elif char == '」':
            depth = max(0, depth - 1)
        elif depth == 0 and char in RANGE_SEPARATORS:
            if char == '-' and 0 < index < len(text) - 1 and text[index - 1].isdigit() and text[index + 1].isdigit():
                continue
            return text[:index].strip(), text[index + 1:].strip()
    return text.strip(), None


def _times(text):
    """单段时间 → 事件时间字段；开始或结束任一无法确认时返回 None（不进日历）。"""
    original = text.strip(' ·')
    clean = PARENTHESES.sub('', original).strip()
    if not clean or '常驻' in clean:
        return None
    dependent = DEPENDENT_END.search(clean)
    if clean.endswith('版本期间'):
        left, right = clean, '版本更新维护前'
    elif dependent:
        left, right = clean[:dependent.start()].rstrip('，, '), dependent.group()
    else:
        left, right = _split_range(clean)
    if right is None:
        return None
    start_match = DATE_TIME.search(left)
    if start_match:
        start = _dt(start_match)
        start_fields = dict(start_at=start.isoformat(), start_date=start.date().isoformat(),
                            start_text=start_match.group(), start_precision='minute')
    elif RELATIVE_START.search(left) or left.endswith('版本期间'):
        start_fields = dict(start_at=None, start_date=None, start_text=left, start_precision='relative')
    else:
        return None
    end_match = DATE_TIME.search(right)
    if '版本更新维护前' in right:
        end_fields = dict(end_at=None, end_text='版本更新维护前', end_precision='version_end')
    elif end_match:
        end_fields = dict(end_at=_dt(end_match).isoformat(), end_text=end_match.group(), end_precision='minute')
    elif DEPENDENT_END.search(right):
        end_fields = dict(end_at=None, end_text=right, end_precision='dependent')
    else:
        return None
    if start_fields['start_at'] and end_fields['end_at'] and end_fields['end_at'] < start_fields['start_at']:
        return None
    return dict(**start_fields, **end_fields, time_text=original)


def _time_entries(lines):
    """条目内的时间行 → [(子项名, 时间字段)]；“及”连接或标签下逐行列出的多段各算一段。"""
    entries = []
    for index, line in enumerate(lines):
        match = TIME_LINE.match(line)
        if not match:
            continue
        prefix, value = match[1].strip(), match[3].strip()
        sub = '' if prefix in ('', '活动') else (re.search(r'「([^」]+)」', prefix) or [None, prefix])[1]
        if not value:
            follow = []
            for next_line in lines[index + 1:index + 5]:
                if TIME_LINE.match(next_line) or not DATE_TIME.search(next_line):
                    break
                follow.append(next_line)
            value = '及'.join(follow)
        for phase in re.split(r'及|[；;]', value):
            times = _times(phase)
            if times:
                entries.append((sub, times))
    return entries


def parse_post_events(post, version):
    if post.get('decision') != 'accepted':
        return []
    events = []
    for item in _items(_lines(post)):
        aliases = [item['name'], *UP_ITEM.findall('\n'.join(item['lines'][:6]))]
        entries = _time_entries(item['lines'])
        phases = sum(1 for sub, _ in entries if not sub)
        phase = 0
        for sub, times in entries:
            name = f"{item['name']}·{sub}" if sub else item['name']
            extra = {}
            if not sub and phases > 1:
                phase += 1
                extra = dict(phase=phase)
            events.append(dict(
                name=name, category=item['category'], aliases=aliases if not sub else [name], version=version,
                **times, **extra, source='bilibili', source_name='B站官方动态', source_url=post.get('url'),
                source_post_id=post['id'], source_title=content_title(post), published_at=post['published_at'],
                fetched_at=post.get('fetched_at'), source_stale=post.get('source_stale', False)))
    return events


def maintenance_window(post):
    """更新维护时间 → (开始, 结束)；维护预告只写开始时刻时结束为 None。"""
    lines = _lines(post)
    for index, line in enumerate(lines):
        if '维护时间' in line:
            for candidate in lines[index:index + 2]:
                dates = [_dt(match) for match in DATE_TIME.finditer(candidate)]
                if dates:
                    return dates[0], dates[1] if len(dates) > 1 else None
    planned = re.search(r'计划(?:将)?于(.{0,40}?)开始', post.get('body') or '')
    if planned and DATE_TIME.search(planned[1]):
        return _dt(DATE_TIME.search(planned[1])), None
    return None


def calendar_from_posts(posts, now=None):
    now = now or datetime.now(timezone.utc)
    accepted = [post for post in posts if post.get('decision') == 'accepted']
    bases = []
    for post in accepted:
        version = VERSION_POST.search(content_title(post))
        if not version:
            continue
        window = maintenance_window(post)
        started = window[0] if window else datetime.fromisoformat(post['published_at'])
        if started > now:
            continue  # 下个版本的说明不能替代当前版本
        bases.append((started, post, version[1]))
    if not bases:
        return dict(version=None, events=[])
    started, base, version = max(bases, key=lambda item: item[0])
    release_day = started.astimezone(BJ).date().isoformat()
    next_start = None
    for post in accepted:
        title = content_title(post)
        notice = MAINTENANCE_NOTICE.search(title) or VERSION_POST.search(title)
        window = maintenance_window(post) if notice and notice[1] != version else None
        if window and window[0] > started and (next_start is None or window[0] < next_start):
            next_start = window[0]
    relevant = []
    for post in accepted:
        if post['id'] == base['id']:
            continue
        title = content_title(post)
        if VERSION_POST.search(title) or MAINTENANCE_NOTICE.search(title):
            continue
        declared = DECLARED_VERSION.search(title) or DECLARED_VERSION.search((post.get('body') or '')[:400])
        if declared and declared[1] != version:
            continue
        if not declared and post.get('published_at', '') < base['published_at']:
            continue
        relevant += [event for event in parse_post_events(post, version)
                     if event['end_at'] is None or event['end_at'][:10] >= release_day]
    result = []
    # 较新的单独公告优先于版本说明里的同名条目。
    for event in sorted(relevant + parse_post_events(base, version), key=lambda e: e['published_at'], reverse=True):
        if event['start_precision'] == 'relative' and not event['start_date']:
            event['start_date'] = release_day
        if event['end_precision'] == 'version_end' and next_start:
            event['end_at'] = next_start.isoformat()
        if not any(_same_event(kept, event) for kept in result):
            result.append(event)
    return dict(version=version, events=result, source_post_id=base['id'])
