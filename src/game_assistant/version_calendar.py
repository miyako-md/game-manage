"""Source-backed version scope; event extents never define version boundaries."""
import re
from datetime import datetime, timezone

from game_assistant.event_calendar import BEIJING_TZ, nearest_year, parse_ms_or_iso

VERSION = re.compile(r'(\d+\.\d+)\s*版本')
MAINTENANCE = re.compile(r'(?:更新)?维护时间')
DATE = re.compile(r'(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日\s*(?:(\d{1,2}):([0-5]\d))?')


def source(post):
    return dict(post_id=str(post.get('id') or post.get('postId') or ''),
                title=post.get('title') or post.get('postTitle') or post.get('subject') or '',
                url=post.get('url'), source_name=post.get('source_name'),
                published_at=post.get('published_at'))


def version_status(meta, now=None, *, stale=False):
    now = (now or datetime.now(timezone.utc)).astimezone(BEIJING_TZ)
    if not meta.get('id'):
        return 'unknown'
    if stale:
        return 'historical'
    end = parse_ms_or_iso(meta.get('end_at')) if meta.get('end_precision') == 'minute' else None
    end_day = str(meta.get('end_date') or '') if meta.get('end_precision') == 'day' else ''
    if end and end.tzinfo is None:
        end = end.replace(tzinfo=BEIJING_TZ)
    today = now.date().isoformat()
    if end and end <= now or end_day and end_day < today:
        return 'historical'
    # A day-precision update does not prove opening or maintenance completion
    # at midnight. Within either boundary day, currentness is unverified.
    start = parse_ms_or_iso(meta.get('start_at')) if meta.get('start_precision') == 'minute' else None
    if start and start.tzinfo is None:
        start = start.replace(tzinfo=BEIJING_TZ)
    opened = bool(start and start <= now or meta.get('start_date') and meta['start_date'] < today)
    before_end = bool(end and now < end or end_day and today < end_day)
    return 'current' if opened and before_end else 'unverified'


def maintenance(post):
    """A maintenance instant bounds the old version; it is not a release instant."""
    lines = str(post.get('body') or '').splitlines()
    published = parse_ms_or_iso(post.get('published_at'))
    for i, line in enumerate(lines):
        if not MAINTENANCE.search(line) and not ('版本更新维护' in line and DATE.search(line)):
            continue
        match = DATE.search(line) or (DATE.search(lines[i+1]) if i+1 < len(lines) else None)
        if not match or not (match[1] or published):
            return None, 'unknown'
        try:
            parts = int(match[2]), int(match[3]), int(match[4] or 0), int(match[5] or 0)
            stamp = (datetime(int(match[1]), *parts, tzinfo=BEIJING_TZ) if match[1]
                     else nearest_year(*parts, near=published))
            return stamp, 'minute' if match[4] else 'day'
        except ValueError:
            return None, 'unknown'
    return None, 'unknown'


def version_metadata(game, base=None, posts=(), *, now=None):
    now = now or datetime.now(timezone.utc)
    declaration = VERSION.search(str((base or {}).get('title') or ''))
    ident = declaration[1] if declaration else None
    start, _ = maintenance(base or {})
    end = None
    end_precision = 'unknown'
    end_source = None
    for post in posts:
        other = VERSION.search(str(post.get('title') or ''))
        if not ident or not other or tuple(map(int, other[1].split('.'))) <= tuple(map(int, ident.split('.'))):
            continue
        stamp, precision = maintenance(post)
        if stamp and start and stamp > start and (end is None or stamp < end):
            end, end_precision, end_source = stamp, precision, source(post)
    stale = bool((base or {}).get('source_stale'))
    diagnostics = ['官方公告清单覆盖待核验；有界来源列表可能遗漏公告。']
    if start is None:
        diagnostics.append('缺少版本开放日期依据，不宣称当前版本。')
    if end is None:
        diagnostics.append('版本结束未知；未按固定周期或最后活动推算。')
    if stale:
        diagnostics.append('版本来源为陈旧快照。')
    meta = dict(id=ident, game=game, server='国服', source_stale=stale,
        start_at=None, start_date=start.date().isoformat() if start else None,
        start_precision='day' if start else 'unknown', start_text='更新维护当日，开放时刻未确认' if start else '未知',
        end_at=end.isoformat() if end and end_precision == 'minute' else None,
        end_date=end.date().isoformat() if end else None, end_precision=end_precision,
        start_source=source(base) if base else None, end_source=end_source,
        sources=[source(base)] if base else [], fetched_at=(base or {}).get('fetched_at'),
        coverage='unverified', diagnostics=diagnostics)
    meta['status'] = version_status(meta, now, stale=stale or bool(meta.get('source_stale')))
    return meta


def snapshot_version(game, events, *, metadata=None, version=None, stale=False, statuses=None, now=None):
    """Old snapshots stay readable, but their version title alone proves no currentness."""
    meta = dict(metadata or next((e['version_metadata'] for e in events if e.get('version_metadata')), {})
                or version_metadata(game, now=now))
    ids = {e.get('version') for e in events if e.get('version')}
    if not meta.get('id'):
        meta['id'] = version or (next(iter(ids)) if len(ids) == 1 else None)
    meta['status'] = version_status(meta, now, stale=stale or bool(meta.get('source_stale')))
    meta['diagnostics'] = list(meta.get('diagnostics') or [])
    meta['sources'] = list(meta.get('sources') or [])
    for e in events:
        item = dict(post_id=e.get('source_post_id'), title=e.get('source_title'), url=e.get('source_url'), source_name=e.get('source_name'))
        if item['post_id'] and not any(s.get('post_id') == item['post_id'] for s in meta['sources']):
            meta['sources'].append(item)
    if stale:
        meta['status'] = 'historical' if meta.get('id') else 'unknown'
        meta['diagnostics'].append('陈旧快照：保留已知活动，当前版本待刷新核验。')
    for name, state in (statuses or {}).items():
        if state.get('state') in ('error', 'auth_expired', 'never'):
            meta['coverage'] = 'partial'
            meta['diagnostics'].append(f'{name} 来源不可用或未采集。')
    meta['coverage'] = meta.get('coverage') if meta.get('coverage') in ('unverified', 'partial') else 'unverified'
    if any(e.get('start_precision') == 'unknown' or e.get('end_precision') == 'unknown' for e in events):
        meta['diagnostics'].append('部分活动日期缺失或无法可靠解析；保留原始时间描述。')
    return meta


def select_version_events(events, metadata):
    """Explicit ownership or a known intersection qualifies; unknown ownership stays visible."""
    ident = metadata.get('id')
    if not ident:
        return list(events)
    output = []
    for row in events:
        if not row.get('version') or row.get('version') == ident:
            output.append(row)
            continue
        # Keep a known cross-version interval only with source-backed boundaries.
        start = parse_ms_or_iso(metadata.get('start_date'))
        end = parse_ms_or_iso(metadata.get('end_at') or metadata.get('end_date'))
        a = parse_ms_or_iso(row.get('start_at') or row.get('start_date'))
        b = parse_ms_or_iso(row.get('end_at') or row.get('end_date'))
        stamps = [start, end, a, b]
        if all(stamps):
            stamps = [s.replace(tzinfo=BEIJING_TZ) if s.tzinfo is None else s for s in stamps]
            start, end, a, b = stamps
            if a < end and b > start:
                output.append({**row, 'cross_version': True})
    return output


def select_unversioned_events(events, metadata):
    """Exclude proven out-of-version dates without inventing missing ownership."""
    start_day = metadata.get('start_date')
    end_day = metadata.get('end_date')
    end = parse_ms_or_iso(metadata.get('end_at'))
    output = []
    for event in events:
        a = event.get('start_at') or event.get('start_date')
        b = event.get('end_at') or event.get('end_date')
        if start_day and b and b[:10] < start_day:
            continue
        if end and a:
            stamp = parse_ms_or_iso(a)
            if stamp and (stamp.replace(tzinfo=BEIJING_TZ) if stamp.tzinfo is None else stamp) >= end:
                continue
        elif end_day and a and a[:10] > end_day:
            continue
        # A known intersection is not proof that this notice belongs to this
        # version. Keep its source dates visible with ownership unconfirmed.
        output.append({**event, 'version': None})
    return output
