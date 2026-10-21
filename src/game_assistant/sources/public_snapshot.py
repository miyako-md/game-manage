"""Shared public-source selection for local, website and QQ cached reads."""
import json
from datetime import datetime, timezone

from game_assistant.models import Capability
from game_assistant.scheduler import interval_for
from .public_content import VERSION, merge_events, merge_news


def expired(value, interval, now):
    if not value:
        return False
    try:
        instant = datetime.fromisoformat(value)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        return (now - instant).total_seconds() > 2 * max(interval, 60)
    except (TypeError, ValueError):
        return True


def read_public_snapshot(store, game, capability, settings, bilibili=None, *, now=None, poll_seconds=None):
    """poll_seconds: the cloud public poll interval; freshness never expects
    data more often than the sources are actually collected."""
    now = now or datetime.now(timezone.utc)
    floor = poll_seconds or 0
    statuses, snapshots, native = {}, {}, []
    caps = (capability, 'announcement') if capability == 'news' else (capability,)
    for cap in caps:
        snap = store.get(game, cap)
        snapshots[cap] = snap
        status = store.get_poll_status(game, cap) or dict(
            game_id=game, capability=cap, state='never', last_attempt_at=None,
            last_success_at=snap['fetched_at'] if snap else None,
            consecutive_failures=0, error=None, error_kind=None)
        stale = bool(snap and (expired(snap['fetched_at'], max(interval_for(Capability(cap), settings), floor), now)
                     or status['state'] in ('error', 'auth_expired')))
        statuses[cap] = {**status, 'stale': stale}
        payload = json.loads(snap['payload']) if snap else []
        for row in payload if isinstance(payload, list) else []:
            native.append({**row, '_snapshot_capability': cap,
                           'source': row.get('source') or ('official' if game == 'endfield' else 'community'),
                           'source_stale': bool(stale or row.get('source_stale') or
                                                row.get('content_status') in ('error', 'stale'))})

    native_cap = capability
    if capability == 'news' and not snapshots[capability] and statuses[capability]['state'] == 'never':
        native_cap = 'announcement'
    effective = dict(statuses[native_cap])
    source_statuses = {'official' if game == 'endfield' else 'community': dict(effective)}
    if capability == 'news':
        source_statuses.update({cap: dict(statuses[cap]) for cap in caps})
    rows = merge_news([], native) if capability == 'news' else native
    official = game == 'endfield' and snapshots[capability] is not None
    primary_source = 'official' if game == 'endfield' else 'community'
    version = None
    state = None
    primary = []
    success_at = None
    if bilibili and game in bilibili.sources:
        state = bilibili.store.state(game, bilibili.sources[game])
        calendar = bilibili.calendar(game) if capability == 'events' else None
        primary = calendar['events'] if calendar else bilibili.news(game)
        success_at = state.get('last_success') or max(
            (r.get('fetched_at') for r in primary if r.get('fetched_at')), default=None)
        failed = state.get('status') == 'error'
        partial = any(r.get('source_stale') for r in primary)
        stale = expired(success_at, max(600, settings.bilibili_poll_seconds, floor), now)
        bili_status = dict(state='error' if failed or partial else 'ok' if success_at or primary else 'never',
            error=(state.get('message') or 'B站采集失败，保留成功记录') if failed else
                  '部分B站正文更新失败，保留上次成功内容' if partial else None,
            error_kind='source_error' if failed else 'partial_data' if partial else None,
            last_success_at=success_at, last_attempt_at=state.get('last_attempt'),
            consecutive_failures=state.get('failures', 0), stale=bool(stale or failed or partial))
        source_statuses['bilibili'] = bili_status
        primary = [{**r, 'source_stale': bool(r.get('source_stale') or stale or failed)} for r in primary]
        if official:
            if capability == 'news':
                rows = merge_news(rows, [r for r in primary if r.get('decision') != 'accepted'])
        else:
            rows = merge_news(primary, rows) if capability == 'news' else merge_events(primary, rows, calendar['version'])
            if primary or failed:
                effective.update(bili_status, scope='public_source')
            if primary:
                primary_source = 'bilibili'
                version = calendar['version'] if calendar else None

    # Only sources supplying returned rows/body determine content freshness.
    contributing_caps = {r['_snapshot_capability'] for r in rows if r.get('_snapshot_capability')}
    times = [snapshots[cap]['fetched_at'] for cap in contributing_caps if snapshots.get(cap)]
    if any(r.get('source') == 'bilibili' for r in rows) and success_at:
        times.append(success_at)
    if not rows and snapshots[native_cap]:
        times.append(snapshots[native_cap]['fetched_at'])
    for row in rows:
        row.pop('_snapshot_capability', None)
    if not version:
        for row in rows:
            declared = VERSION.search(row.get('source_title') or '')
            version = row.get('version') or (declared[1] if declared else None)
            if version:
                break
    stale = all(r.get('source_stale', False) for r in rows) if rows else bool(times and statuses[native_cap]['stale'])
    effective.update(game_id=game, capability=capability, observed_at=now.isoformat(),
                     stale=stale, source_statuses=source_statuses)
    from game_assistant.version_calendar import snapshot_version
    meta = snapshot_version(game, rows, version=version, stale=stale, statuses=source_statuses, now=now) if capability == 'events' else None
    media = {}
    if capability == 'events':
        try:
            from .article_content import article_images
            articles = read_public_snapshot(store, game, 'news', settings, bilibili, now=now,
                                            poll_seconds=poll_seconds)['payload'] or []
            index = []
            fields = ('id', 'post_id', 'article_id', 'source', 'url', 'source_url', 'source_post_id', 'version', 'version_id')
            for article in articles:
                pictures = article_images([article.get('banner'), article.get('image_url'),
                    *(article.get('images') or []), *(article.get('image_urls') or [])])
                if not pictures:
                    continue
                item = {key:article[key] for key in fields if article.get(key) is not None}
                item['images'] = pictures
                links = [{'url':link['url']} for link in article.get('original_links') or [] if isinstance(link, dict) and isinstance(link.get('url'), str)]
                if links:
                    item['original_links'] = links
                index.append(item)
            media = dict(artwork_sources=index, artwork_status={'state':'ok' if index else 'missing'})
        except Exception:
            # Optional media cannot turn a usable cached date response into a failure.
            media = dict(artwork_sources=[], artwork_status={'state':'error', 'error':'配图资料读取失败，活动日期仍可查看'})
    return dict(payload=rows if rows or any(snapshots.values()) else None,
                fetched_at=max(times, default=None), stale=stale,
                poll_status=effective, primary_source=primary_source, version=version,
                bilibili_status=state, complete=None, version_metadata=meta, **media)
