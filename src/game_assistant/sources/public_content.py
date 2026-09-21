"""Mobile-game public content: source-backed dates and Bilibili-first merging.

No network or private account state; native snapshots remain untouched.
"""
import re
import unicodedata
from datetime import datetime, timezone

from game_assistant.event_calendar import BEIJING_TZ as BJ

MOBILE_GAMES = {'nte', 'wuthering_waves'}
VERSION = re.compile(r'(\d+\.\d+)\s*版本')
DATE = re.compile(r'(?<![\d.])(?:(20\d{2})[年/.-])?(\d{1,2})(?:月|/|-)(\d{1,2})(?:日)?\s*(?:(\d{1,2})[:：](\d{2})(?::(\d{2}))?)?')
RELATIVE = re.compile(r'(?:版本)?更新后|维护(?:完成|结束)?后')
TIME_LABEL = re.compile(r'(?:活动|开放|开启|唤取)时间')


def content_title(post):
    for line in (post.get('body') or post.get('title') or '').splitlines():
        line = re.sub(r'#[^#]*#', '', line).strip(' \u200b\ufeff')
        if line and line not in ('互动抽奖',):
            return line[:160]
    return post.get('title', '')


def key(text):
    return re.sub(r'[^\w\u4e00-\u9fff]', '', unicodedata.normalize('NFKC', text or '')).lower()


def event_key(name):
    return key(re.sub(r'(?:盲盒|签到|限时活动|活动)$', '', name or ''))


def _dt(match, year):
    y, m, d, h, minute, second = match.groups()
    return datetime(int(y or year), int(m), int(d), int(h or 0), int(minute or 0), int(second or 0), tzinfo=BJ)


def _times(text, year):
    matches = list(DATE.finditer(text))
    if not matches or len(matches) > 2 or '永久' in text:
        return None
    try:
        last = matches[-1]
        end = _dt(last, year)
        if last.group(4) is None:
            return None  # Never fabricate a deadline at midnight from a date alone.
        relative = RELATIVE.search(text)
        if len(matches) == 1 and not relative:
            return None
        first = matches[0] if len(matches) > 1 else None
        start = _dt(first, year) if first else None
        if start and not last.group(1) and end < start and start.month == 12 and end.month == 1:
            end = end.replace(year=end.year + 1)
        if start and end < start:
            return None
        uncertain = bool(relative or (first and first.group(4) is None))
        start_date = start.date().isoformat() if start else None
        # Separate display-day metadata from exact instants.
        split_at = last.start()
        start_text = text[:split_at].strip(' ✦:：~-–—～至') if relative else (first.group().strip() if first else '')
        return dict(start_at=start.isoformat() if start and not uncertain else None,
                    end_at=end.isoformat(), start_date=start_date,
                    start_text=start_text, time_text=text, start_precision='relative' if relative else 'day' if uncertain else 'minute')
    except (ValueError, OverflowError):
        return None


def _heading(line, game):
    if game == 'wuthering_waves':
        m = re.match(r'^\[([^\]]+)\]([^\s]*)', line)
        if m: return m[1], m[2].split('——')[0] or '限时活动'
        m = re.match(r'^「([^」]+)」.*?(角色|武器)活动唤取', line)
        return (m[1], m[2] + '活动唤取') if m else None
    # Only heading-like lines. Excludes activity description paragraphs and tasks.
    if not re.match(r'^(?:●|[一二三四五六七八九十]+[、.]|「|轨外之境|全新|限定)', line):
        return None
    m = re.search(r'「([^」]+)」', line)
    if not m:
        return None
    suffix = line[m.end():].split('，')[0].split('、')[0]
    if '限定棋盘' in suffix: category = '角色卡池'
    elif '弧盘研募' in suffix: category = '弧盘研募'
    elif '盲盒' in line: category = '盲盒'
    elif '赏令' in line: category = '版本赏令'
    elif '签到' in line: category = '签到活动'
    elif '弧盘' in line or '研募' in line: category = '弧盘研募'
    elif '角色' in line or '棋盘' in line: category = '角色卡池'
    elif '路线' in line: category = '轨外之境'
    elif '活动' in line: category = '限时活动'
    else: return None
    return m[1], category


def parse_post_events(post, game, version):
    if game not in MOBILE_GAMES or post.get('decision') != 'accepted':
        return []
    lines = [s.strip() for s in post.get('body', '').splitlines() if s.strip()]
    year = datetime.fromisoformat(post['published_at']).astimezone(BJ).year
    events = []
    for i, line in enumerate(lines):
        heading = _heading(line, game)
        if not heading:
            continue
        for j in range(i + 1, min(i + 8, len(lines))):
            if _heading(lines[j], game):
                break
            label = TIME_LABEL.search(lines[j])
            if not label:
                continue
            time_text = lines[j][label.end():].strip(' ✦:：')
            if not DATE.search(time_text) and j + 1 < len(lines) and not _heading(lines[j+1], game):
                time_text += lines[j+1]
            for phase_text in re.split(r'[；;]', time_text):
                dates = _times(phase_text, year)
                if dates:
                    headings = [heading]
                    if game == 'wuthering_waves' and line.startswith('「'):
                        headings = [(name, category+'活动唤取') for names, category in re.findall(r'((?:「[^」]+」[、]?)+)(角色|武器)活动唤取', line)
                                    for name in re.findall(r'「([^」]+)」', names)] or headings
                    elif game == 'nte' and line.startswith('「'):
                        headings = [(name, '角色卡池' if kind == '限定棋盘' else '弧盘研募') for name,kind in re.findall(r'「([^」]+)」(限定棋盘|弧盘研募)', line)] or headings
                    for name, category in headings:
                        context = '\n'.join(lines[i:j])
                        entity = '角色' if category == '角色卡池' else '弧盘' if category == '弧盘研募' else None
                        aliases = re.findall(r'(?:限定)?S级'+entity+r'「([^」]+)」', context) if entity else []
                        events.append(dict(name=name, category=category, aliases=[name, *aliases], version=version, **dates,
                        source='bilibili', source_name='B站官方动态', source_url=post['url'],
                        source_post_id=post['id'], source_title=content_title(post),
                        published_at=post['published_at'], fetched_at=post.get('fetched_at'),
                        source_stale=post.get('source_stale', False)))
    return events


def _overlap(a, b):
    # Same deadline identifies a revision; disjoint known ranges are phases.
    if a.get('end_at') == b.get('end_at'):
        return True
    try:
        start_a, end_a, start_b, end_b = [datetime.fromisoformat(x).replace(tzinfo=BJ) if len(x) == 10 else datetime.fromisoformat(x) for x in
            (a.get('start_at') or a.get('start_date'), a.get('end_at'), b.get('start_at') or b.get('start_date'), b.get('end_at'))]
        return start_a < end_b and start_b < end_a
    except (TypeError, ValueError):
        return False


def _same_event(a, b):
    names_a = {event_key(n) for n in a.get('aliases', [a['name']])}
    names_b = {event_key(n) for n in b.get('aliases', [b['name']])}
    return bool(names_a & names_b) and _overlap(a, b)


def _maintenance_day(post):
    lines = [s.strip() for s in post['body'].splitlines() if s.strip()]
    for i, line in enumerate(lines):
        if not re.search(r'(?:更新)?维护时间', line): continue
        match = DATE.search(line) or (DATE.search(lines[i+1]) if i+1 < len(lines) else None)
        if match:
            try: return _dt(match, datetime.fromisoformat(post['published_at']).year)
            except ValueError: return None
    return None


def calendar_from_posts(posts, game, now=None):
    now = now or datetime.now(timezone.utc)
    if game not in MOBILE_GAMES:
        return dict(version=None, events=[])
    bases = []
    for post in posts:
        title = content_title(post)
        version = VERSION.search(title)
        if post.get('decision') != 'accepted' or not version or not re.search(r'版本.*(?:内容说明|更新公告)', title):
            continue
        parsed = parse_post_events(post, game, version[1])
        if not parsed:
            continue
        # Future patch notes must not replace the active version.
        release = _maintenance_day(post)
        if release:
            if release > now: continue
        else:
            known = [e.get('start_at') or e.get('start_date') for e in parsed if e.get('start_at') or e.get('start_date')]
            if not known or min(known) > now.astimezone(BJ).isoformat(): continue
        bases.append((post, version[1], parsed))
    if not bases:
        return dict(version=None, events=[])
    base, version, baseline = max(bases, key=lambda b: tuple(int(n) for n in b[1].split('.')))
    release = _maintenance_day(base)
    release_day = release.date().isoformat() if release else None
    version_end = max(e['end_at'][:10] for e in baseline)
    version_start = min((e.get('start_at') or e.get('start_date') or base['published_at'])[:10] for e in baseline)
    relevant = []
    for post in posts:
        if post['id'] == base['id']:
            continue
        declared = VERSION.search(content_title(post)) or VERSION.search(post.get('body', '')[:700])
        if declared and declared[1] != version:
            continue
        if not declared and post.get('published_at', '') < base['published_at']:
            continue
        for event in parse_post_events(post, game, version):
            if event['end_at'][:10] >= version_start and (declared or event['end_at'][:10] <= version_end):
                relevant.append(event)
    # Newer independent notices take precedence over baseline dates.
    result = []
    for event in sorted(relevant + baseline, key=lambda e: e['published_at'], reverse=True):
        if not event.get('start_date') and event.get('start_precision') == 'relative' and re.search(re.escape(version) + r'版本更新后', event.get('start_text', '')):
            event['start_date'] = release_day
        if not any(_same_event(e, event) for e in result):
            result.append(event)
    return dict(version=version, events=result, source_post_id=base['id'])


def merge_events(primary, community, version):
    result = [dict(e) for e in primary]
    for row in community:
        item = {**row, 'source': 'community', 'source_name': '社区补充'}
        same = next((e for e in result if _same_event(e, item)), None)
        if same:
            same.setdefault('supplement_sources', []).append({k: item.get(k) for k in ('source_name', 'source_title', 'source_post_id')})
            if any(same.get(k) != item.get(k) for k in ('start_at', 'end_at')):
                same['source_note'] = '社区时间与主来源不同，采用B站公告；相对开始时间保留原文。'
            continue
        if primary:
            declared = VERSION.search(row.get('source_title') or '')
            if not declared or declared[1] != version:
                continue
        result.append(item)
    return result


def merge_news(primary, community):
    result, seen = [], set()
    ordered = sorted(primary, key=lambda p: p.get('published_at') or '', reverse=True)
    ordered += [{**r, 'source': 'community', 'source_name': '社区补充'} for r in community]
    for row in ordered:
        row = dict(row)
        row['title'] = content_title(row) if row.get('source') == 'bilibili' else row.get('title', '')
        ident = key(row['title'])
        if ident in seen:
            continue
        seen.add(ident)
        result.append(row)
    return result
