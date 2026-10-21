"""Mobile-game public content: source-backed dates and Bilibili-first merging.

No network or private account state; native snapshots remain untouched.
"""
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from game_assistant.event_calendar import BEIJING_TZ as BJ, nearest_year

MOBILE_GAMES = {'nte', 'wuthering_waves', 'endfield'}
VERSION = re.compile(r'(\d+\.\d+)\s*版本')
DATE = re.compile(r'(?<![\d.])(?:(20\d{2})[年/.-])?(\d{1,2})(?:月|/|-)(\d{1,2})(?:日)?\s*(?:(\d{1,2})[:：](\d{2})(?::(\d{2}))?)?')
RELATIVE = re.compile(r'(?:版本)?更新后|维护(?:完成|结束)?后')
TIME_LABEL = re.compile(r'(?:活动|开放|开启|唤取)时间')
OFFICIAL_CALENDAR_SOURCES = {'B站官方动态', '库街区官方公告', '塔吉多官方公告'}
ADVERTISED_POOL = re.compile(r'可通过(?:\[([^\]]+)\]|「([^」]+)」)(角色|武器)活动唤取获得')


def _official_version_source(post, version):
    declared = VERSION.search(post.get('title') or post.get('source_title') or '') or VERSION.search((post.get('body') or '')[:4000])
    return bool(declared and declared[1] == version and
                (post.get('source') == 'official' or post.get('source_name') in OFFICIAL_CALENDAR_SOURCES))


def content_title(post):
    for line in (post.get('body') or post.get('title') or '').splitlines():
        line = re.sub(r'#[^#]*#', '', line).strip(' \u200b\ufeff')
        if line and line not in ('互动抽奖',):
            return line[:160]
    return post.get('title', '')


def visible_article(post):
    """Editorial scope for the list; never change calendar acceptance decisions."""
    if post.get('decision') == 'accepted':
        return True
    # Dateless official posts and character/operator intel are news only;
    # calendar parsers still require an accepted decision.
    if post.get('reason') in ('no_date', 'intel'):
        return bool(post.get('body'))
    if post.get('reason') not in ('promotion', 'lottery', 'not_ingame'):
        return False
    return bool(post.get('body') and re.search(
        r'网页活动|创作(?:征集|激励)|同人(?:征集|创作|活动)|线下活动|漫展|参展|ChinaJoy|社区活动',
        content_title(post), re.I))


def key(text):
    return re.sub(r'[^\w\u4e00-\u9fff]', '', unicodedata.normalize('NFKC', text or '')).lower()


def event_key(name):
    return key(re.sub(r'(?:盲盒|签到|限时活动|活动)$', '', name or ''))


def _dt(match, year, near=None):
    y, m, d, h, minute, second = match.groups()
    parts = int(m), int(d), int(h or 0), int(minute or 0), int(second or 0)
    if y or near is None:
        return datetime(int(y or year), *parts, tzinfo=BJ)
    return nearest_year(*parts, near=near)


def _times(text, year, published=None):
    matches = list(DATE.finditer(text))
    relative = RELATIVE.search(text)
    if (not matches and not relative) or len(matches) > 2 or '永久' in text:
        return None
    try:
        # A lone date before "维护后" is an opening day, not a deadline.
        # Relative openings without any date remain unresolved for source binding.
        if relative and (not matches or len(matches) == 1 and matches[0].start() < relative.start()):
            start = _dt(matches[0], year, published) if matches else None
            return dict(start_at=None, start_date=start.date().isoformat() if start else None,
                        start_precision='relative', start_text=text, end_at=None,
                        end_date=None, end_precision='unknown', time_text=text)
        last = matches[-1]
        if len(matches) == 1 and not relative:
            return None
        first = matches[0] if len(matches) > 1 else None
        start = _dt(first, year, published) if first else None
        if start and not last.group(1):
            # A year-less end is the first such date after the start; a range that
            # still runs backwards half a year later is a typo, not an event.
            end = _dt(last, start.year)
            if end < start:
                later = _dt(last, start.year + 1)
                if later - start <= timedelta(days=185):
                    end = later
        else:
            end = _dt(last, year, published)
        if start and end < start:
            return None
        uncertain = bool(relative or (first and first.group(4) is None))
        start_date = start.date().isoformat() if start else None
        # Separate display-day metadata from exact instants.
        split_at = last.start()
        start_text = text[:split_at].strip(' ✦:：~-–—～至') if relative else (first.group().strip() if first else '')
        return dict(start_at=start.isoformat() if start and not uncertain else None,
                    end_at=end.isoformat() if last.group(4) is not None else None,
                    end_date=end.date().isoformat(), end_precision='minute' if last.group(4) else 'day',
                    start_date=start_date, start_text=start_text, time_text=text,
                    start_precision='relative' if relative else 'day' if uncertain else 'minute')
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
    if '网页活动' in suffix: category = '网页活动'
    elif '限定棋盘' in suffix: category = '角色卡池'
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
    if game == 'endfield':
        from .endfield_notice import parse_post_events as parse_endfield
        return parse_endfield(post, version)
    if game not in MOBILE_GAMES:
        return []
    from .bilibili import PROMOTION
    official_version = _official_version_source(post, version)
    # A version-linked official web notice may have been conservatively tagged
    # promotion by the ingame-feed classifier. Other promotions stay excluded.
    official_web = (official_version and '网页活动' in post.get('body', '')
                    and not PROMOTION.search((post.get('title') or '').replace('网页活动', '')))
    if post.get('decision') != 'accepted' and not (official_web and post.get('reason') == 'promotion'):
        return []
    lines = [s.strip() for s in post.get('body', '').splitlines() if s.strip()]
    published = post.get('published_at')
    posted = datetime.fromisoformat(published) if published else None
    if posted:
        year = posted.astimezone(BJ).year
    else:
        explicit = next((m[1] for m in DATE.finditer(post.get('body', '')) if m[1]), None)
        year = int(explicit) if explicit else None
    events = []
    for i, line in enumerate(lines):
        heading = _heading(line, game)
        # Mixed version notes can mention external promotions. They still
        # delimit sections below, so their dates cannot leak to another event.
        if not heading or PROMOTION.search(line.replace('网页活动', '') if official_version else line):
            continue
        found = False
        permanent = False
        original_time = ''
        for j in range(i + 1, min(i + 8, len(lines))):
            if _heading(lines[j], game) or re.match(r'^(?:【[^】]+】|[一二三四五六七八九十]+[、.])', lines[j]):
                break
            label = TIME_LABEL.search(lines[j])
            if not label:
                continue
            time_text = lines[j][label.end():].strip(' ✦:：')
            if not DATE.search(time_text) and j + 1 < len(lines) and not _heading(lines[j+1], game):
                time_text += lines[j+1]
            original_time = time_text
            if '永久' in time_text and '永久开放' not in time_text:
                permanent = True
                continue
            permanent = '永久开放' in time_text
            for phase_text in re.split(r'[；;]', time_text):
                dates = _times(phase_text.replace('永久开放', ''), year, posted) if year else None
                if dates:
                    if permanent:
                        dates.update(permanent=True, end_at=None, end_date=None,
                                     end_precision='permanent', end_text='永久开放', time_text=phase_text)
                    found = True
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
                        events.append(dict(name=name, category=category, aliases=[name, *aliases], version=version, phase=phase_text, **dates,
                        source=post.get('source') or 'bilibili', source_name=post.get('source_name') or 'B站官方动态', source_url=post['url'],
                        source_post_id=post['id'], source_title=post.get('title') if post.get('source') == 'community' else content_title(post),
                        published_at=published, fetched_at=post.get('fetched_at'),
                        source_stale=post.get('source_stale', False)))
        if not found and not permanent:
            # Keep announced headings even when dates are missing or malformed.
            events.append(dict(name=heading[0], category=heading[1], version=version,
                start_at=None, end_at=None, start_precision='unknown', end_precision='unknown',
                start_text=original_time or '公告未提供活动时间', end_text=original_time or '公告未提供活动时间',
                time_text=original_time, source=post.get('source') or 'bilibili',
                source_name=post.get('source_name') or 'B站官方动态', source_url=post['url'],
                source_post_id=post['id'], source_title=post.get('title') or content_title(post),
                published_at=published, fetched_at=post.get('fetched_at'), source_stale=post.get('source_stale', False)))
    if game == 'wuthering_waves' and official_version:
        for line in lines:
            for match in ADVERTISED_POOL.finditer(line):
                name, category = match[1] or match[2], match[3]+'活动唤取'
                if any(e['name'] == name and e['category'] == category for e in events):
                    continue
                events.append(dict(name=name, category=category, version=version, announced_pool=True,
                    start_at=None, end_at=None, start_precision='unknown', end_precision='unknown',
                    start_text='分项唤取公告时间待确认', end_text='分项唤取公告时间待确认',
                    source=post.get('source'), source_name=post.get('source_name'), source_url=post['url'],
                    source_post_id=post['id'], source_title=post.get('title') or content_title(post),
                    time_text=line, published_at=published, fetched_at=post.get('fetched_at'),
                    source_stale=post.get('source_stale', False)))
    from .article_content import article_images
    images = article_images(post.get('images'))
    events = [{**event, 'image_urls': images} for event in events]
    events = resolve_relative_starts(events, [post], game, version)
    return [e for e in events if e.get('start_at') or e.get('start_date') or e.get('end_at') or e.get('end_date')
            or not any(other['name'] == e['name'] and other['category'] == e['category']
                       and (other.get('start_at') or other.get('start_date') or other.get('end_at') or other.get('end_date'))
                       for other in events)]


def _overlap(a, b):
    # Same deadline identifies a revision; disjoint known ranges are phases.
    if (a.get('end_at') or a.get('end_date')) == (b.get('end_at') or b.get('end_date')):
        return True
    try:
        start_a, end_a, start_b, end_b = [datetime.fromisoformat(x).replace(tzinfo=BJ) if len(x) == 10 else datetime.fromisoformat(x) for x in
            (a.get('start_at') or a.get('start_date'), a.get('end_at') or a.get('end_date'),
             b.get('start_at') or b.get('start_date'), b.get('end_at') or b.get('end_date'))]
        if not a.get('end_at'):
            end_a += timedelta(days=1)
        if not b.get('end_at'):
            end_b += timedelta(days=1)
        return start_a < end_b and start_b < end_a
    except (TypeError, ValueError):
        return False


def _same_event(a, b):
    for field in ('version','category','game','game_id','server','server_id','region'):
        if a.get(field) and b.get(field) and a[field] != b[field]:
            return False
    # Tajiduo rows carry aliases=[] when a heading names no character; fall back to the name then too.
    names_a = {event_key(n) for n in a.get('aliases') or [a['name']]}
    names_b = {event_key(n) for n in b.get('aliases') or [b['name']]}
    announced = any(row.get('announced_pool') and not any(row.get(k) for k in ('start_at','end_at','start_date','end_date'))
                    for row in (a,b)) and a.get('category') == b.get('category')
    return bool(names_a & names_b) and (announced or _overlap(a, b))


def _resolve_undated_placeholders(events):
    """Absorb a source-proven teaser only into one exact activity identity.

    Dated phases/conflicts are never collapsed here. An ambiguous or untrusted
    unknown remains an independent row; advertised future pools stay visible.
    """
    bounds = ('start_at','start_date','end_at','end_date')

    def identity(row):
        meta = row.get('version_metadata') or {}
        return (str(row.get('name') or '').strip(), row.get('version'), row.get('category'),
                row.get('game') or row.get('game_id') or meta.get('game'),
                row.get('server') or row.get('server_id') or meta.get('server'), row.get('region'))

    result = [dict(row) for row in events]
    removed = set()
    for index, row in enumerate(result):
        if (any(row.get(k) for k in bounds) or row.get('announced_pool') or row.get('phase')
                or row.get('time_text') or not row.get('version') or not row.get('category')
                or not _official_version_source(row, row['version'])):
            continue
        candidates = [other for other in result if any(other.get(k) for k in bounds)
                      and identity(other) == identity(row)]
        if len(candidates) != 1:
            continue
        chosen = candidates[0]
        sources = [dict(item) for item in chosen.get('supplement_sources', [])]
        evidence = {k:row.get(k) for k in ('source_name','source_title','source_post_id','source_url',
                    'published_at','version','category','start_at','start_date','end_at','end_date',
                    'start_precision','end_precision','time_text')}
        if evidence not in sources:
            sources.append(evidence)
        chosen['supplement_sources'] = sources
        removed.add(index)
    return [row for index, row in enumerate(result) if index not in removed]


def _maintenance_day(post):
    lines = [s.strip() for s in post['body'].splitlines() if s.strip()]
    for i, line in enumerate(lines):
        if not re.search(r'(?:更新)?维护时间', line): continue
        match = DATE.search(line) or (DATE.search(lines[i+1]) if i+1 < len(lines) else None)
        if match:
            published = datetime.fromisoformat(post['published_at'])
            try: return _dt(match, published.astimezone(BJ).year, published)
            except ValueError: return None
    return None


def _maintenance_opening_day(post):
    """Expected opening day is the scheduled end day, including overnight work."""
    lines = [s.strip() for s in post.get('body', '').splitlines() if s.strip()]
    for index, line in enumerate(lines):
        label = re.search(r'(?:更新)?维护时间', line)
        if not label:
            continue
        text = line[label.end():].strip(' ：:')
        if not DATE.search(text) and index + 1 < len(lines):
            text += lines[index + 1]
        matches = list(DATE.finditer(text))
        if not matches or not post.get('published_at'):
            return None
        posted = datetime.fromisoformat(post['published_at'])
        year = posted.astimezone(BJ).year
        try:
            start = _dt(matches[0], year, posted)
            if len(matches) == 2:
                end = _dt(matches[1], start.year)
                if end < start and _dt(matches[1], start.year + 1) - start <= timedelta(days=2):
                    end = _dt(matches[1], start.year + 1)  # an overnight window across New Year
            elif len(matches) == 1:
                clock = re.search(r'[~～–—-]|至|到', text[matches[0].end():])
                if not clock:
                    return None
                end_clock = re.search(r'(\d{1,2})[:：](\d{2})', text[matches[0].end()+clock.end():])
                if not end_clock or not matches[0][4]:
                    return None
                end = start.replace(hour=int(end_clock[1]), minute=int(end_clock[2]), second=0)
                if end < start:
                    end += timedelta(days=1)
            else:
                return None
            return (end.date().isoformat(), text, start.date().isoformat()) if end >= start else None
        except (ValueError, OverflowError):
            return None
    return None


def resolve_relative_starts(events, posts, game, version):
    """Bind relative dates to their own maintenance or an explicit version release.

    Scheduled maintenance proves the expected day only. Its planned end hour is
    never promoted to an actual opening timestamp.
    """
    from game_assistant.version_calendar import source

    def trusted(post):
        return (post.get('decision') == 'accepted'
                and (post.get('source') == 'official' or post.get('source_name') in OFFICIAL_CALENDAR_SOURCES)
                and all(not post.get(k) or post[k] == game for k in ('game', 'game_id')))

    def declaration(post):
        match = VERSION.search(content_title(post)) or VERSION.search((post.get('body') or '')[:4000])
        return match[1] if match else None

    notices = {str(p['id']): p for p in posts if trusted(p)}
    maintenance = []
    for post in notices.values():
        declared = declaration(post)
        if declared and version and declared != version:
            continue
        opening = _maintenance_opening_day(post)
        if opening:
            maintenance.append((post, opening[0], declared))
    result = []
    for original in events:
        row = dict(original)
        text = row.get('start_text') or ''
        origin = notices.get(str(row.get('source_post_id')))
        relative = RELATIVE.search(text)
        explicit_version = VERSION.search(text)
        if (not origin or not relative or row.get('start_at')
                or explicit_version and explicit_version[1] != version
                or declaration(origin) and version and declaration(origin) != version):
            result.append(row)
            continue
        day = row.get('start_date')
        own = [(p, date) for p, date, _ in maintenance if str(p['id']) == str(origin['id'])
               and (not day or day in (date, _maintenance_opening_day(p)[2]))]
        candidates = own
        if not candidates and day:
            candidates = [(p, date) for p, date, _ in maintenance if date == day]
        if not candidates and not day and re.search(r'版本更新(?:维护)?后', text):
            # Event.version may be assigned by the caller. Require a declaration
            # in the notice/text rather than inferring membership from recency.
            if (explicit_version and explicit_version[1] == version) or declaration(origin) == version:
                candidates = [(p, date) for p, date, declared in maintenance if declared == version
                              and re.search(r'版本.*(?:内容说明|更新公告|更新维护预告)', content_title(p))]
        if candidates and len({date for _, date in candidates}) == 1:
            post, day = candidates[0]
            row.update(start_date=day, start_source={**source(post), 'time_text':_maintenance_opening_day(post)[1]}, start_estimated=True,
                       start_basis='scheduled_maintenance', start_date_precision='day')
        elif day:
            row.update(start_estimated=True, start_basis='notice_relative_date', start_date_precision='day')
        result.append(row)
    return result


def _fill_announced_pool_dates(target, dated):
    """A newer version teaser must not hide its older, explicitly dated notice."""
    if (not target.get('announced_pool') or any(target.get(k) for k in ('start_at','end_at','start_date','end_date'))
            or not any(dated.get(k) for k in ('start_at','end_at','start_date','end_date'))):
        return
    for field in ('start_at','start_date','start_precision','start_text','start_source','start_estimated',
                  'start_basis','start_date_precision','end_at','end_date','end_precision','end_text','time_text','phase'):
        if field in dated:
            target[field] = dated[field]
    target['date_source'] = {k:dated.get(k) for k in ('source_name','source_title','source_post_id','source_url','published_at')}
    target['source_note'] = '卡池身份来自版本公告，时间取自分项公告。'


def calendar_from_posts(posts, game, now=None):
    now = now or datetime.now(timezone.utc)
    if game == 'endfield':
        from .endfield_notice import calendar_from_posts as endfield_calendar
        return endfield_calendar(posts, now)
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
        from game_assistant.version_calendar import version_metadata
        meta = version_metadata(game, now=now)
        meta['diagnostics'].append('未取得可靠当前版本锚点；仅展示来源已公布活动汇总。')
        available = []
        for post in posts:
            declared = VERSION.search(content_title(post))
            for event in parse_post_events(post, game, declared[1] if declared else None):
                if not any(_same_event(old, event) for old in available):
                    available.append({**event, 'version_metadata':meta})
        return dict(version=None, events=_resolve_undated_placeholders(available), version_metadata=meta)
    base, version, baseline = max(bases, key=lambda b: tuple(int(n) for n in b[1].split('.')))
    from game_assistant.version_calendar import select_unversioned_events, version_metadata
    meta = version_metadata(game, {**base, 'title':content_title(base)},
                            [{**p, 'title':content_title(p)} for p in posts], now=now)
    relevant = []
    for post in posts:
        if post['id'] == base['id']:
            continue
        declared = VERSION.search(content_title(post)) or VERSION.search(post.get('body', '')[:700])
        if declared and declared[1] != version:
            continue
        if not declared and post.get('published_at', '') < base['published_at']:
            continue
        parsed = parse_post_events(post, game, version)
        relevant.extend(parsed if declared else select_unversioned_events(parsed, meta))
    # Newer independent notices take precedence over baseline dates.
    result = []
    resolved = resolve_relative_starts(relevant + baseline, posts, game, version)
    for event in sorted(resolved, key=lambda e: e['published_at'], reverse=True):
        same = next((e for e in result if _same_event(e, event)), None)
        if same:
            _fill_announced_pool_dates(same, event)
        else:
            result.append(event)
    result = [{**e, 'version_metadata':meta} for e in _resolve_undated_placeholders(result)]
    return dict(version=version, events=result, source_post_id=base['id'], version_metadata=meta)


def merge_events(primary, community, version):
    result = [dict(e) for e in primary]
    for row in community:
        if '网页活动' in (row.get('category') or '') and not _official_version_source(row, version or row.get('version')):
            continue
        item = {**row, 'source': 'community', 'source_name': row.get('source_name') or '社区补充'}
        same = next((e for e in result if _same_event(e, item)), None)
        if same:
            same.setdefault('supplement_sources', []).append({k: item.get(k) for k in ('source_name', 'source_title', 'source_post_id', 'source_url', 'published_at', 'image_urls')})
            if same.get('announced_pool') and not (same.get('start_at') or same.get('start_date') or same.get('end_at') or same.get('end_date')):
                _fill_announced_pool_dates(same, item)
            elif any(same.get(k) != item.get(k) for k in ('start_at', 'end_at')):
                same['source_note'] = '社区时间与主来源不同，采用B站公告；相对开始时间保留原文。'
            continue
        if primary:
            declared = VERSION.search(row.get('source_title') or '')
            declared_version = row.get('version') or (declared[1] if declared else None)
            if declared_version != version:
                continue
        result.append(item)
    return _resolve_undated_placeholders(result)


def merge_news(primary, community):
    from .article_content import article_images

    def media(row):
        pictures = article_images(row.get('images') or [])
        supplied = {r.get('url'): r for r in row.get('image_sources') or [] if isinstance(r, dict)}
        return pictures, [{ 'url':url, 'source_url':supplied.get(url, {}).get('source_url') or row.get('url') } for url in pictures]

    def rank(item):
        if not item.get('body') and not item.get('images'): return 0
        status = item.get('content_status') or ('full' if item.get('decision') == 'accepted' else '')
        return 3 if status == 'full' else 2 if status == 'stale' else 1

    result = []
    ordered = sorted(primary, key=lambda p: p.get('published_at') or '', reverse=True)
    ordered += [{**r, 'source': r.get('source') or 'community', 'source_name': r.get('source_name') or '社区补充'} for r in community]
    for row in ordered:
        row = dict(row)
        row['title'] = content_title(row) if row.get('source') == 'bilibili' else row.get('title', '')
        ident = key(row['title'])
        same = next((item for item in result if
                     (row.get('url') and row['url'] == item.get('url')) or
                     (ident and key(item['title']) == ident and
                      (not row.get('version') or not item.get('version') or row['version'] == item['version']) and
                      item.get('source') != row.get('source') and
                      (not row.get('published_at') or not item.get('published_at') or
                       row['published_at'][:10] == item['published_at'][:10]))), None)
        if same is not None:
            old_pictures, old_sources = media(same)
            new_pictures, new_sources = media(row)
            links = same.setdefault('original_links', [{'url': same.get('url'), 'name': same.get('source_name') or '原文'}])
            for link in [{'url': row.get('url'), 'name': row.get('source_name') or '原文'}, *row.get('original_links', [])]:
                if link.get('url') and not any(old.get('url') == link['url'] for old in links):
                    links.append(link)
            if rank(row) > rank(same):
                for field in ('body', 'summary', 'content_status', 'content_error', 'fetched_at', 'source_stale', '_snapshot_capability'):
                    if field in row: same[field] = row[field]
            pictures = list(dict.fromkeys([*old_pictures, *new_pictures]))
            if pictures:
                same['images'] = pictures
                sources = {r['url']:r for r in [*new_sources, *old_sources]}
                same['image_sources'] = [sources[url] for url in pictures]
            continue
        result.append(row)
    return result
