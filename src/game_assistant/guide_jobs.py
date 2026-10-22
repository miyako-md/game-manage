"""Cloud daily guide check: every WuWa role, the tower when due, then the NTE sources.

One run per Beijing-time slot. Runs are persisted in guide_runs next to the guide
caches, so a restart never repeats a started slot. The job only reuses the existing
service instances, whose locks serialise it with the administrator buttons; it never
rewrites reviewed advice and logs counts and fixed codes only.
"""
import asyncio
from contextlib import closing
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
import logging
from pathlib import Path
import sqlite3

from .nte_guides import GuideSourceError
from .nte_guides_catalog import SOURCES
from .wuwa_guide_updates import STOP_CODES, Search, is_new_candidate, preferred_candidate

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent
CN = timezone(timedelta(hours=8))
PAUSE = 3
EXTRACT_BUDGET = 8


@lru_cache(maxsize=1)
def _roster():
    static = json.loads((ROOT / 'qq' / 'role_guides.json').read_text(encoding='utf-8'))['guides']['wuthering_waves']
    defaults = json.loads((ROOT / 'assessment-defaults-wuwa.json').read_text(encoding='utf-8'))['characters']
    # The exact id/name/attribute strings the web page sends for static entries.
    rows = [dict(character_id=str(g['id']), name=g['name'], attribute=g.get('attribute') or '', static=True) for g in static]
    seen = {row['character_id'] for row in rows}
    # Default-weight names spell the Rover forms "漂泊者·<attribute>"; the search needs them apart.
    rows += [dict(character_id=str(cid), static=False,
                  **dict(zip(('name', 'attribute'), value['name'].split('·', 1)
                             if value['name'].startswith('漂泊者·') else (value['name'], ''))))
             for cid, value in defaults.items() if str(cid) not in seen]
    sources = {str(g['id']): frozenset({str(s['id']) for s in g.get('sources', []) if s.get('id')}
                                       | {str(s['sourceId']) for s in g.get('sections', []) if s.get('sourceId')})
               for g in static}
    # Catalog dates are Beijing time "YYYY-MM-DD HH:MM"; only posts newer than the newest one are new.
    since = {}
    for g in static:
        dates = [s['publishedAt'] for s in g.get('sources', []) if isinstance(s.get('publishedAt'), str)]
        try:
            since[str(g['id'])] = max(datetime.strptime(d, '%Y-%m-%d %H:%M').replace(tzinfo=CN) for d in dates)
        except ValueError:
            pass
    return tuple(rows), sources, since


def guide_roster():
    """WuWa guide roster: static entries first, then default-weight roles without one."""
    return [dict(row) for row in _roster()[0]]


def static_sources(character_id):
    return _roster()[1].get(str(character_id), frozenset())


def static_since(character_id):
    return _roster()[2].get(str(character_id))


def pending_candidate(character_id, value):
    """The preferred post of a cached check when it is new to the guide on display.

    A role with a static guide shows its extraction only once all sections are reviewed (the
    page's rule), so until then an extracted new post still waits for review.
    """
    value = value or {}
    preferred = preferred_candidate(value.get('candidates'))
    guide = value.get('active_guide')
    if static_sources(character_id) and not (isinstance(guide, dict) and guide.get('sections') and all(
            isinstance(s, dict) and s.get('status') == 'reviewed' for s in guide['sections'])):
        guide = None
    return preferred if is_new_candidate(preferred, guide, static_sources(character_id),
                                         static_since(character_id)) else None


def slot_time(check_time, now):
    """Today's Beijing-time slot for an "HH:MM" setting."""
    hour, minute = map(int, check_time.split(':'))
    return now.astimezone(CN).replace(hour=hour, minute=minute, second=0, microsecond=0)


class GuideJob:
    def __init__(self, updates, tower, nte, *, sleep=asyncio.sleep, now=None, pause=PAUSE, budget=EXTRACT_BUDGET):
        self.updates, self.tower, self.nte = updates, tower, nte
        self.path = updates.path
        self.sleep, self.pause, self.budget = sleep, pause, budget
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.running = False
        updates.runner = self
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS guide_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, '
                         'started_at TEXT NOT NULL, finished_at TEXT, outcome TEXT, stop_code TEXT, summary TEXT)')
            conn.commit()

    def runs(self, limit=2):
        with closing(sqlite3.connect(self.path)) as conn:
            rows = conn.execute('SELECT started_at, finished_at, outcome, stop_code FROM guide_runs '
                                'ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [dict(started_at=r[0], finished_at=r[1], outcome=r[2], stop_code=r[3]) for r in rows]

    def due(self, check_time):
        now = self.now()
        slot = slot_time(check_time, now)
        last = self.runs(1)
        return now >= slot and (not last or datetime.fromisoformat(last[0]['started_at']) < slot)

    def next_run_at(self, check_time):
        now = self.now()
        slot = slot_time(check_time, now)
        last = self.runs(1)
        if now >= slot and last and datetime.fromisoformat(last[0]['started_at']) >= slot:
            slot += timedelta(days=1)
        return slot.astimezone(timezone.utc).isoformat()

    def last_run(self):
        for run in self.runs():
            if run['finished_at']:
                return run
            if not self.running:
                # Ended without finishing (process killed): never shown as a success.
                return {**run, 'outcome': 'failed'}
        return None

    def background(self):
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute('SELECT finished_at FROM guide_runs WHERE finished_at IS NOT NULL '
                               'ORDER BY id DESC LIMIT 1').fetchone()
        return {'running': self.running, 'last_run_at': row[0] if row else None}

    async def run(self):
        with closing(sqlite3.connect(self.path)) as conn:
            run_id = conn.execute('INSERT INTO guide_runs (started_at) VALUES (?)', (self.now().isoformat(),)).lastrowid
            conn.commit()
        self.running = True
        counts = dict(checked=0, extracted=0, failed=0)
        summary = dict(wuthering_waves=counts, tower=None, nte_failed=None)
        outcome, stop = 'failed', None
        try:
            stop = await self._wuwa(counts)
            # The tower is the same community API: never asked right after a refusal.
            summary['tower'] = 'skipped' if stop else await self._tower()
            summary['nte_failed'] = await self._nte()
            if stop:
                outcome = 'stopped'
            elif counts['checked'] == 0 and counts['failed']:
                outcome = 'failed'
            elif counts['failed'] or summary['nte_failed'] or summary['tower'] not in ('ok', 'fresh', 'deferred'):
                outcome = 'partial'
            else:
                outcome = 'ok'
        except asyncio.CancelledError:
            outcome, stop = 'stopped', 'shutdown'
            raise
        except Exception:
            logger.warning('guide_job_failed')
        finally:
            self.running = False
            with closing(sqlite3.connect(self.path)) as conn:
                conn.execute('UPDATE guide_runs SET finished_at=?, outcome=?, stop_code=?, summary=? WHERE id=?',
                             (self.now().isoformat(), outcome, stop, json.dumps(summary), run_id))
                conn.commit()
            # Warning level: the cloud runtime configures no INFO handler, and operators need this line.
            logger.warning('guide_job_finished outcome=%s checked=%d extracted=%d failed=%d',
                        outcome, counts['checked'], counts['extracted'], counts['failed'])
        return outcome

    async def _wuwa(self, counts):
        # Roles without a static guide first: their extraction is shown at once, so they get the budget.
        for index, role in enumerate(sorted(guide_roster(), key=lambda r: r['static'])):
            if index:
                await self.sleep(self.pause)
            query = Search(character_id=role['character_id'], name=role['name'], attribute=role['attribute'])
            stored = None if role['static'] else self.updates.stored(role['character_id'])
            if stored:
                # A new role checked from the page first: keep the page's spelling so both share one key.
                query = Search(character_id=role['character_id'], name=stored[1]['name'], attribute=stored[1]['attribute'])
            result = await self.updates.check(query, extract='changed' if counts['extracted'] < self.budget else 'never',
                                              known=static_sources(role['character_id']),
                                              since=static_since(role['character_id']))
            codes = [result.get('error_code') if result.get('error') else None]
            failed = bool(result.get('error'))
            counts['checked'] += not failed
            if result.get('extracted'):
                counts['extracted'] += 1
                if result.get('extraction_error'):
                    failed = True
                    codes.append(self.updates.extractor.active(query).get('error_code'))
            counts['failed'] += failed
            stop = next((code for code in codes if code in STOP_CODES), None)
            if stop:
                logger.warning('guide_job_stopped code=%s', stop)
                return stop
        return None

    async def _tower(self):
        if not self.tower.due():
            return 'fresh'
        value = await self.tower.check()
        if value.get('error'):
            return value.get('error_code') or 'failed'
        return 'deferred' if value.get('deferred') else 'ok'

    async def _nte(self):
        failed = 0
        for post_id in SOURCES:
            # Cached posts younger than 24 hours are returned without a request.
            try:
                async with asyncio.timeout(60):
                    failed += bool((await self.nte.read(post_id)).get('error'))
            except (GuideSourceError, TimeoutError):
                failed += 1
        return failed

    def status(self, *, state='idle', next_run_at=None, retry_after=0):
        """Administrator card: cache reads only, no network."""
        roles = guide_roster()
        checked, pending, extraction_failed, failed = [], [], [], []
        for role in roles:
            value = self.updates.cached_by_id(role['character_id'])
            if not value:
                continue
            ref = dict(character_id=role['character_id'], name=role['name'])
            if value.get('checked_at'):
                checked.append(value['checked_at'])
            if value.get('error'):
                failed.append({**ref, 'error_code': value.get('error_code')})
            if value.get('extraction_error'):
                extraction_failed.append(ref)
            preferred = pending_candidate(role['character_id'], value)
            if preferred:
                pending.append({**ref, 'post_id': preferred['id'], 'title': preferred.get('title'),
                                'author': preferred.get('author'), 'published_at': preferred.get('published_at')})
        tower = self.tower.cached()
        now = self.now().timestamp()
        covered = None if not tower.get('attempted_at') else any(
            datetime.fromisoformat(g['periodStart']).timestamp() <= now < datetime.fromisoformat(g['periodEnd']).timestamp()
            for g in tower['guides'])
        posts = []
        for post_id, source in SOURCES.items():
            value = self.nte.status(post_id)
            posts.append({'post_id': post_id, 'title': source['title'], 'fetched_at': None, 'summary_changed': False,
                          'stale': True, 'error': False, **(value or {})})
        return {'job': {'state': state, 'last_run': self.last_run(), 'next_run_at': next_run_at, 'retry_after': retry_after},
                'wuthering_waves': {'roles_total': len(roles), 'roles_checked': len(checked),
                                    'checked_at_oldest': min(checked) if checked else None, 'pending': pending,
                                    'extraction_failed': extraction_failed, 'failed': failed},
                'tower': {'checked_at': tower.get('checked_at'), 'current_period_covered': covered,
                          'error_code': tower.get('error_code') if tower.get('error') else None},
                'nte': {'posts': posts}}
