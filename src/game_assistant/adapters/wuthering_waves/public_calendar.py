"""Bounded anonymous community calendar using the mature public date parser."""
import re
from datetime import datetime, timedelta, timezone

from pydantic import ConfigDict

from game_assistant.event_calendar import BEIJING_TZ, parse_ms_or_iso, strip_html
from game_assistant.models import GameEvent
from game_assistant.sources.article_content import article_content, article_images
from game_assistant.sources.public_content import VERSION, _same_event, parse_post_events, resolve_relative_starts


class PublicCalendarEvent(GameEvent):
    # Keep provenance and exact/day/relative precision through snapshot encoding.
    model_config = ConfigDict(extra='allow')


def published(row):
    return parse_ms_or_iso(row.get('publishTime'), row.get('firstPublishTime'))


async def read_calendar(client, rows, title_keys):
    rows = [r for r in rows or [] if isinstance(r, dict)]
    now = datetime.now(timezone.utc)
    bases = [r for r in rows if any(k in str(r.get('postTitle') or '') for k in title_keys)]
    bases.sort(key=lambda r: published(r) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    async def read(row, version, *, optional=False, require_version=False, allow_empty=False):
        ident = str(row.get('postId') or '')
        if not ident.isdigit():
            raise ValueError('missing public post identity')
        detail = await client.get_post_detail(ident)
        body = '\n'.join(strip_html(str(detail.get('postH5Content') or '')))
        title = str(detail.get('postTitle') or row.get('postTitle') or '')
        declarations = [VERSION.search(title), VERSION.search(body[:4000])]
        declared = next((d for d in declarations if d), None)
        if any(d and d[1] != version for d in declarations):
            if optional:
                return None, []
            raise ValueError('public post version changed')
        if require_version and not declared:
            return None, []
        stamp = published(row)
        # The independent notice's verified list/detail title is often its only
        # pool heading. Its body starts with the probability description.
        heading = re.sub(r'^.*?(?=「[^」]+」.*?(?:角色|武器)活动唤取)', '', title)
        post = dict(id=ident, title=title, body=heading+'\n'+body, decision='accepted',
                    published_at=stamp.isoformat() if stamp else None,
                    source='community', source_name='库街区官方公告', fetched_at=now.isoformat(),
                    url=f'https://www.kurobbs.com/forum/post/{ident}')
        images = article_images(row.get('coverUrl'), detail.get('coverUrl'),
                                article_content(detail.get('postH5Content'))['images'])
        events = [{**event, 'image_urls': images}
                  for event in parse_post_events(post, 'wuthering_waves', version)]
        if not events and not allow_empty:
            raise ValueError('public calendar notice has no dated events')
        return post, events

    # Check at most three version announcements, reserving the same total budget
    # for pools. Known future starts never replace the active calendar.
    requests = 0
    notices = []
    for base in bases[:3]:
        declared = VERSION.search(str(base.get('postTitle') or ''))
        if not declared or (published(base) and published(base) > now):
            continue
        version = declared[1]
        requests += 1
        # A future maintenance notice may list no activities; it is skipped below, not an error.
        post, baseline = await read(base, version, allow_empty=True)
        notices.append(post)
        starts = [e.get('start_at') or e.get('start_date') for e in baseline
                  if e.get('start_at') or e.get('start_date')]
        # Maintenance supplies an actual release boundary when present; it does
        # not turn a relative start into a fabricated instant.
        from game_assistant.sources.public_content import DATE, _dt
        lines = post['body'].splitlines()
        release = None
        for i, line in enumerate(lines):
            if re.search(r'(?:更新)?维护时间', line):
                match = DATE.search(line) or (DATE.search(lines[i+1]) if i+1 < len(lines) else None)
                if match and (match[1] or post['published_at']):
                    posted = datetime.fromisoformat(post['published_at']) if post['published_at'] else None
                    year = int(match[1]) if match[1] else posted.astimezone(BEIJING_TZ).year
                    release = _dt(match, year, posted)
                break
        if release and release > now:
            continue
        if not release and starts and min(starts) > now.astimezone(BEIJING_TZ).isoformat():
            continue
        if not baseline:
            raise ValueError('public calendar notice has no dated events')
        from game_assistant.version_calendar import select_unversioned_events, version_metadata
        meta = version_metadata('wuthering_waves', post, notices, now=now)
        candidates = []
        for row in rows:
            if str(row.get('postId')) == post['id'] or not re.search(r'(?:角色|武器)活动唤取|唤取(?:活动|说明|公告)', str(row.get('postTitle') or '')):
                continue
            declared = VERSION.search(str(row.get('postTitle') or ''))
            if declared and declared[1] != version:
                continue
            stamp, base_stamp = published(row), published(base)
            if not declared and (not stamp or not base_stamp or stamp < base_stamp - timedelta(days=7)):
                continue
            if stamp and stamp > now:
                continue
            candidates.append(row)
        candidates.sort(key=lambda r: published(r) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        relevant = []
        seen = {post['id']}
        for row in candidates:
            ident = str(row.get('postId') or '')
            if ident in seen:
                continue
            if requests >= 9:
                break
            seen.add(ident)
            requests += 1
            stamp, base_stamp = published(row), published(base)
            candidate, events = await read(row, version, optional=True,
                                          require_version=bool(stamp and base_stamp and stamp < base_stamp))
            if candidate and not (VERSION.search(candidate['title']) or VERSION.search(candidate['body'][:4000])):
                events = select_unversioned_events(events, meta)
            if candidate:
                notices.append(candidate)
            relevant.extend(events)
        result = []
        resolved = resolve_relative_starts(relevant + baseline, notices, 'wuthering_waves', version)
        for event in sorted(resolved, key=lambda e: e.get('published_at') or '', reverse=True):
            if not any(_same_event(e, event) for e in result):
                result.append(event)
        meta = version_metadata('wuthering_waves', post, notices, now=now)
        return [PublicCalendarEvent(**{**event, 'version_metadata':meta}) for event in result]
    return []
