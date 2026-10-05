"""Per-source freshness, partial updates, and cache-only display projection."""
import asyncio
import math
from datetime import datetime, timedelta, timezone
from time import monotonic

from game_assistant.event_calendar import BEIJING_TZ
from game_assistant.models import FetchResult
from .esports_client import EsportsSourceError, TencentEsportsClient
from .esports_models import EsportsSnapshot, EsportsTeam, GroupMeta, FAMILIES
from .esports_parse import BASE, parse_catalog, parse_matches, parse_team


def _replace_ids(old, new):
    values = {r.id: r for r in old}
    values.update({r.id: r for r in new})
    return list(values.values())


def merge_snapshot(previous: EsportsSnapshot | None, incoming: EsportsSnapshot) -> EsportsSnapshot:
    if previous is None or previous.season_year != incoming.season_year:
        return incoming.model_copy(deep=True)
    result = incoming.model_copy(deep=True)
    for field in ('tournaments', 'matches', 'teams', 'players'):
        setattr(result, field, _replace_ids(getattr(previous, field), getattr(incoming, field)))
    result.coverage = {**previous.coverage, **incoming.coverage}
    memberships = {(r.team_id, r.player_id, r.scope): r for r in previous.roster_memberships}
    for r in incoming.roster_memberships:
        memberships[(r.team_id, r.player_id, r.scope)] = r
    result.roster_memberships = list(memberships.values())
    return result


def snapshot_for_display(previous: EsportsSnapshot | None, poll_status: dict | None, now: datetime) -> dict:
    year = now.astimezone(BEIJING_TZ).year
    mismatch = previous is not None and previous.season_year != year
    model = previous if previous and not mismatch else EsportsSnapshot(season_year=year)
    payload = model.model_dump(mode='json')
    missing = set(FAMILIES) - {t.family for t in model.tournaments}
    payload['missing_families'] = [f for f in FAMILIES if f in missing]
    metas = {'catalog': model.catalog, **model.coverage}
    for key, meta in metas.items():
        data = payload['catalog'] if key == 'catalog' else payload['coverage'][key]
        threshold = 1800 if key.startswith('matches:') else 172800
        invalid_source = bool(meta.source_updated_at and meta.source_updated_at > now + timedelta(minutes=5))
        data['stale'] = (meta.last_success_at is None or (now - meta.last_success_at).total_seconds() > threshold
                         or meta.attempt_state in ('error', 'cooldown'))
        data['source_time_invalid'] = invalid_source
        data['source_lagging'] = bool(key.startswith('roster:') and meta.source_updated_at
                                     and not invalid_source and (now - meta.source_updated_at).total_seconds() > 604800)
    failed = bool(poll_status and poll_status.get('state') == 'error')
    return dict(payload=payload, stale=mismatch or failed or any(
        v.get('stale', False) for v in [payload['catalog'], *payload['coverage'].values()]),
        source_status={**(poll_status or {}), 'scope': 'public_source',
                       'reason': 'current_season_missing' if mismatch else 'never' if previous is None else None})


class LolEsportsService:
    def __init__(self, client_factory=TencentEsportsClient, *, clock=None, monotonic_clock=None, settings):
        self.client_factory = client_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic_clock or monotonic
        self.settings = settings
        self._cooldown_until = 0.0
        self._attempt_after = {}
        self._failed_meta = {}

    def source_cooldown_seconds(self) -> int:
        return max(0, math.ceil(self._cooldown_until - self.monotonic()))

    async def refresh(self, previous: EsportsSnapshot | None) -> FetchResult:
        if self.source_cooldown_seconds():
            return FetchResult(ok=False, error='腾讯数据源暂时限制访问，请稍后重试', error_kind='source_error')
        now = self.clock()
        year = now.astimezone(BEIJING_TZ).year
        working = previous.model_copy(deep=True) if previous and previous.season_year == year else EsportsSnapshot(season_year=year)
        # All-failure rounds do not replace the stored snapshot. Keep their group
        # status across backoff/no-op rounds until an actual request succeeds.
        self._failed_meta = {k: v for k, v in self._failed_meta.items() if k[0] == year}
        for (_, key), meta in self._failed_meta.items():
            if key == 'catalog':
                working.catalog = meta.model_copy(deep=True)
            else:
                working.coverage[key] = meta.model_copy(deep=True)
        slots = asyncio.Semaphore(3)
        successes = 0
        attempts = 0
        errors = 0

        def due(key, meta, interval):
            return (self.monotonic() >= self._attempt_after.get(key, 0)
                    and (meta is None or meta.last_success_at is None
                         or (now - meta.last_success_at).total_seconds() >= interval))

        async def fetch(key, callback, old, interval):
            nonlocal successes, attempts, errors
            if not due(key, old, interval):
                return None
            async with slots:
                if self.source_cooldown_seconds():
                    errors += 1
                    return None
                attempts += 1
                self._attempt_after[key] = self.monotonic() + max(60, min(interval, 900))
                try:
                    result = await callback()
                    meta = GroupMeta(group_key=key, last_attempt_at=now, last_success_at=now,
                                     attempt_state='ok', **result.meta.model_dump())
                    if meta.source_updated_at and meta.source_updated_at > now + timedelta(minutes=5):
                        meta.source_updated_at = None
                        meta.issues.append('源更新时间异常')
                    if key == 'catalog':
                        working.catalog = meta
                    else:
                        working.coverage[key] = meta
                    successes += 1
                    self._failed_meta.pop((year, key), None)
                    return result
                except (EsportsSourceError, ValueError, TypeError, KeyError) as exc:
                    errors += 1
                    cooldown = max(60, exc.retry_after_seconds or 900) if isinstance(exc, EsportsSourceError) else 900
                    if isinstance(exc, EsportsSourceError) and (exc.retry_after_seconds is not None or exc.code in ('http_429', 'http_403', 'http_412')):
                        self._cooldown_until = max(self._cooldown_until, self.monotonic() + cooldown)
                    meta = old.model_copy(deep=True) if old else GroupMeta(group_key=key)
                    meta.last_attempt_at, meta.attempt_state = now, 'error'
                    meta.issues = list(dict.fromkeys([*meta.issues, '腾讯资料更新失败，保留已有数据']))
                    self._failed_meta[(year, key)] = meta.model_copy(deep=True)
                    if key == 'catalog':
                        working.catalog = meta
                    else:
                        working.coverage[key] = meta
                    return None

        try:
            async with asyncio.timeout(120):
                async with self.client_factory() as client:
                    async def catalogue():
                        return parse_catalog(await client.fetch_catalog(), year)
                    parsed = await fetch('catalog', catalogue, working.catalog, self.settings.esports_profiles_seconds)
                    if parsed:
                        working.tournaments = _replace_ids(working.tournaments, parsed.tournaments)

                    async def matches(tournament):
                        key = 'matches:' + tournament.id
                        async def read():
                            return parse_matches(await client.fetch_matches(tournament.source_id), tournament)
                        parsed = await fetch(key, read, working.coverage.get(key), self.settings.esports_seconds)
                        if parsed:
                            working.matches = _replace_ids(working.matches, parsed.matches)
                    await asyncio.gather(*(matches(t) for t in working.tournaments))

                    refs = {}
                    for match in working.matches:
                        for tid, name in ((match.team_a_id, match.team_a_name), (match.team_b_id, match.team_b_name)):
                            if tid:
                                refs.setdefault(tid, {'name': name, 'tournaments': set()})['tournaments'].add(match.tournament_id)
                    existing = {t.id: t for t in working.teams}
                    for tid, ref in refs.items():
                        if tid not in existing:
                            sid = tid.rsplit(':', 1)[1]
                            existing[tid] = EsportsTeam(id=tid, source_id=sid, name=ref['name'],
                                tournament_ids=sorted(ref['tournaments']), source_url=f'{BASE}team-detail.html?tid={sid}')
                        else:
                            existing[tid].tournament_ids = sorted(set(existing[tid].tournament_ids) | ref['tournaments'])
                    working.teams = list(existing.values())

                    async def roster(team):
                        key = 'roster:' + team.id
                        async def read():
                            value = parse_team(await client.fetch_team(team.source_id), team.tournament_ids)
                            if value.team.id != team.id:
                                raise ValueError('team identity mismatch')
                            return value
                        parsed = await fetch(key, read, working.coverage.get(key), self.settings.esports_profiles_seconds)
                        if parsed:
                            working.teams = _replace_ids(working.teams, [parsed.team])
                            working.players = _replace_ids(working.players, parsed.players)
                            memberships = {(m.team_id, m.player_id, m.scope): m for m in working.roster_memberships}
                            # activePlayers is the website's current list; only an intact parse may replace it.
                            if not parsed.meta.issues:
                                memberships = {k: m for k, m in memberships.items() if m.team_id != team.id or m.scope != 'source_current'}
                            memberships.update({(m.team_id, m.player_id, m.scope): m for m in parsed.roster_memberships})
                            working.roster_memberships = list(memberships.values())
                    await asyncio.gather(*(roster(team) for team in working.teams))
        except TimeoutError:
            errors += 1
            # A published partial snapshot must not imply unfinished groups were updated.
            for key, meta in working.coverage.items():
                if meta.last_success_at != now and due(key, meta, 900):
                    meta.attempt_state = 'error'
                    meta.issues = list(dict.fromkeys([*meta.issues, '本轮更新超时，保留已有数据']))
        if attempts and not successes or errors and not successes:
            return FetchResult(ok=False, error='腾讯资料暂不可用，保留已有缓存', error_kind='source_error')
        if not attempts and (previous is None or previous.season_year != year or self._failed_meta):
            return FetchResult(ok=False, error='腾讯资料暂未取得，请稍后重试', error_kind='source_error')
        working.refresh_state = ('missing' if not working.tournaments else 'partial' if errors
            or working.catalog.coverage != 'complete' or any(m.coverage != 'complete' or m.attempt_state != 'ok'
            for m in working.coverage.values()) else 'ok')
        # Only list players for which a retained current-scope relationship exists.
        player_ids = {r.player_id for r in working.roster_memberships}
        working.players = [p for p in working.players if p.id in player_ids]
        return FetchResult(ok=True, payload=working)
