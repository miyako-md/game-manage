import asyncio
import json
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from pydantic import BaseModel

from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult

logger = logging.getLogger(__name__)

INTERVAL_ATTRS = {
    Capability.STAMINA: "stamina_seconds",
    Capability.PROGRESS: "activity_seconds",
    Capability.ANNOUNCEMENT: "announcement_seconds",
    # 活动日历（版本公告解析）：与公告同源同频
    Capability.EVENTS: "announcement_seconds",
    Capability.NEWS: "news_seconds",
    Capability.ACCOUNT: "activity_seconds",
    Capability.MATCH: "activity_seconds",
    # 生涯统计（近 20 场口径）：慢变化数据，与对局同为 1 小时
    Capability.STATS: "activity_seconds",
    # 探索度/数据坞（roleBox）：慢变化数据，与资讯同为 4 小时
    Capability.EXPLORATION: "news_seconds",
    Capability.CALABASH: "news_seconds",
    # 角色练度墙（roleBox）：抽到新角色能较快反映，与进度同为 1 小时
    Capability.ROLES: "activity_seconds",
    Capability.COMBAT: "activity_seconds",
    Capability.ACTIVITIES: "activity_seconds",
    Capability.RESOURCES: "news_seconds",
    # 异环（塔吉多）抽卡记录/战绩卡：慢变化数据，与资讯同为 4 小时
    Capability.GACHA: "news_seconds",
    Capability.RECORD: "news_seconds",
    Capability.REALESTATE: "news_seconds",
    Capability.VEHICLES: "news_seconds",
    Capability.TEAMS: "news_seconds",
    Capability.ESPORTS: "esports_seconds",
}


def interval_for(capability: Capability, settings: Settings) -> int:
    return getattr(settings, INTERVAL_ATTRS[capability])


def _serialize(payload: Any) -> str:
    if isinstance(payload, list):
        return json.dumps([p.model_dump(mode="json") if isinstance(p, BaseModel)
                           else p for p in payload], ensure_ascii=False)
    if isinstance(payload, BaseModel):
        return payload.model_dump_json()
    return json.dumps(payload, ensure_ascii=False)


class PollingScheduler:
    def __init__(self, registry, store, settings: Settings, reminder=None):
        self.registry = registry
        self.store = store
        self.settings = settings
        self.reminder = reminder
        self._scheduler: AsyncIOScheduler | None = None
        self._poll_locks: dict[tuple[str, Capability], asyncio.Lock] = {}

    def build_jobs(self) -> list[tuple[str, Capability, int]]:
        jobs = []
        for adapter in self.registry.all():
            for cap in adapter.capabilities:
                secs = interval_for(cap, self.settings)
                if secs > 0:
                    jobs.append((adapter.game_id, cap, secs))
        return jobs

    async def poll_once(self, game_id: str, capability: Capability) -> FetchResult:
        lock = self._poll_locks.setdefault((game_id, capability), asyncio.Lock())
        async with lock:
            return await self._poll_once_locked(game_id, capability)

    async def _poll_once_locked(self, game_id: str, capability: Capability) -> FetchResult:
        adapter = self.registry.get(game_id)
        auth = getattr(adapter, '_auth', None)
        generation = getattr(auth, 'account_generation', lambda _: None)
        original_generation = generation(game_id)
        try:
            result = await adapter.fetch(capability)
        except Exception as exc:
            logger.warning("拉取失败 %s/%s (%s)", game_id, capability.value, type(exc).__name__)
            result = FetchResult(ok=False, error='数据源请求失败，请稍后重试', error_kind='source_error')
        if original_generation != generation(game_id):
            return FetchResult(ok=False, error='账号已切换，请重新刷新', error_kind='account_changed')
        if auth and result.credential_version is not None and result.credential_version != auth.version(game_id):
            return FetchResult(ok=False, error='账号已切换，请重新刷新', error_kind='account_changed')
        if result.error_kind == 'account_changed':
            return result
        if result.ok:
            if capability in (Capability.NEWS, Capability.ANNOUNCEMENT) and isinstance(result.payload, list):
                from game_assistant.sources.article_content import retain_article_bodies
                old = self.store.get(game_id, capability.value)
                previous = json.loads(old['payload']) if old else []
                result.payload = retain_article_bodies(result.payload, previous if isinstance(previous, list) else [])
            self.store.save(game_id, capability.value, _serialize(result.payload))
        elif result.error_kind not in ('offline', 'unconfigured'):
            logger.warning("拉取失败 %s/%s: %s（保留旧快照）",
                           game_id, capability.value, result.error)
        status = self.store.record_poll(game_id, capability.value, result)
        if self.reminder and capability != Capability.ESPORTS:
            # 提醒引擎异常不得影响轮询与快照保存
            try:
                await self.reminder.handle_poll(game_id, adapter.display_name,
                                                capability, result,
                                                failure_count=status['consecutive_failures'])
            except Exception:
                logger.warning("提醒规则评估失败", exc_info=True)
        return result

    def start(self) -> None:
        # misfire_grace_time：错过触发点的任务在 1 小时内仍补跑一次，避免
        # 休眠/挂起恢复后整轮轮询被静默跳过
        self._scheduler = AsyncIOScheduler(job_defaults={"misfire_grace_time": 3600})
        for game_id, cap, secs in self.build_jobs():
            self._scheduler.add_job(
                self.poll_once, IntervalTrigger(seconds=secs),
                args=[game_id, cap], id=f"{game_id}:{cap.value}",
                max_instances=1, coalesce=True)
        self._scheduler.start()

    async def shutdown(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)


class SchedulerAlreadyRunning(RuntimeError):
    pass


class _SchedulerLease:
    """An OS-held lock, released by kernel even after a process crash."""
    def __init__(self, root):
        from pathlib import Path
        self.path = Path(root).resolve() / 'scheduler.lock'
        self.file = None

    def acquire(self):
        import os
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file = self.path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                if file.seek(0, 2) == 0:
                    file.write(b'0')
                    file.flush()
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            file.close()
            raise SchedulerAlreadyRunning('Cloud scheduler already running') from None
        self.file = file

    def close(self):
        if self.file is not None:
            self.file.close()
            self.file = None


class AccountPollingScheduler:
    """One event-loop scheduler; queueing never waits for upstream requests."""
    def __init__(self, accounts, query, settings, root, *, public=None, reminders=None):
        import time
        self.accounts, self.query, self.settings, self.public = accounts, query, settings, public
        self.reminders = reminders
        self.lease = _SchedulerLease(root)
        self._global = asyncio.Semaphore(settings.cloud_poll_concurrency)
        self._providers = {}
        self._locks = {}
        self._pending = {}
        self._tasks = set()
        self._due = {}
        self._loop = None
        self._running = False
        self._public_running = set()
        # Per game: completed public jobs and the last outcome (admin collect progress).
        self._public_results = {}
        self.clock = time.monotonic

    def start(self, *, periodic=True):
        if self._running:
            return
        self.lease.acquire()
        self._running = True
        self.accounts._listeners.append(self._invalidate)
        if periodic:
            self._loop = asyncio.create_task(self._run())

    def _invalidate(self, user_id, grant_id):
        for key in list(set(self._due) | set(self._pending)):
            scope = key[0]
            if not hasattr(scope, 'user_id') or scope.user_id != user_id:
                continue
            if self.accounts.describe(scope, active=False)['grant_id'] != grant_id:
                continue
            self._due.pop(key, None)
            item = self._pending.pop(key, None)
            if item:
                item[1].cancel()

    def refresh_state(self, scope, capability):
        item = self._pending.get((scope, capability))
        return 'queued' if item and not item[1].done() else 'idle'

    def _paused(self, scope):
        info = self.accounts.describe(scope)
        return any((self.query.snapshots.get_poll_status_scoped(scope, cap, grant_version=info['version']) or
                    {}).get('state') == 'auth_expired' for cap in self.query.capabilities(scope))

    def _queue(self, key, action):
        import uuid
        from game_assistant.accounts.models import RefreshReceipt
        existing = self._pending.get(key)
        if existing and not existing[1].done():
            return RefreshReceipt(existing[0], 'coalesced')
        job_id = uuid.uuid4().hex
        task = asyncio.create_task(action())
        self._tasks.add(task)
        self._pending[key] = job_id, task
        # Cloud collection bypasses BilibiliService.trigger. Register the shared
        # queue task so authorization saves also see queued/running collection.
        if key[0] == 'public' and self.public and getattr(self.public, 'bilibili', None):
            bili = self.public.bilibili
            if key[1] in bili.sources:
                bili.tasks[key[1]] = task
        def finished(done):
            self._tasks.discard(done)
            if self._pending.get(key, (None, None))[1] is done:
                self._pending.pop(key, None)
            if not done.cancelled():
                # Retrieve unexpected errors so they never leak credential-bearing traces.
                done.exception()
        task.add_done_callback(finished)
        return RefreshReceipt(job_id, 'queued')

    def request_refresh(self, scope, capability):
        from fastapi import HTTPException
        from game_assistant.accounts.store import AccountNotFoundError
        if not self._running:
            raise HTTPException(503, 'scheduler_unavailable')
        info = self.query.validate(scope, capability)
        if self._paused(scope):
            raise HTTPException(409, 'authorization_expired')
        key = (scope, capability)
        if key not in self._due:
            self._due[key] = self._persisted_due(scope, capability)
        async def refresh():
            try:
                await asyncio.sleep(max(0, self._due.get(key, 0) - self.clock()) if
                                    self._failed(scope, capability, info['version']) else 0)
                if self.accounts.describe(scope)['version'] != info['version']:
                    return
                await self.poll_once(scope, capability)
            except AccountNotFoundError:
                return
            except Exception:
                # Exception messages can contain credentials or private snapshot data.
                logger.error('scoped_refresh_failed')
                self._due[key] = self.clock() + self.settings.private_poll_seconds(info['game'], capability)
        return self._queue(key, refresh)

    def _failed(self, scope, capability, version):
        status = self.query.snapshots.get_poll_status_scoped(scope, capability, grant_version=version,
            minimum_version=self.accounts.snapshot_generation(scope, version))
        return status and status['state'] == 'error'

    def _next_delay(self, game, capability, status):
        interval = self.settings.private_poll_seconds(game, capability)
        if status['state'] == 'ok':
            return interval
        backoff = min(3600, 60 * 2 ** min(max(0, status['consecutive_failures'] - 1), 6))
        # A rate-limited source is not retried sooner than its normal interval.
        return max(backoff, interval) if status.get('error_code') == 429 else backoff

    def _persisted_due(self, scope, capability):
        from datetime import datetime, timezone
        version, generation = self.accounts.snapshot_bounds(scope)
        status = self.query.snapshots.get_poll_status_scoped(scope, capability, grant_version=version,
            minimum_version=generation)
        if (not status or not status.get('last_attempt_at') or
                status['state'] == 'auth_expired' and not self.query.snapshots.get_poll_status_scoped(
                    scope, capability, grant_version=version)):
            return self.clock()
        delay = self._next_delay(self.accounts.describe(scope)['game'], capability, status)
        try:
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(status['last_attempt_at'])).total_seconds()
        except (ValueError, TypeError):
            elapsed = 0
        return self.clock() + max(0, delay - elapsed)

    async def poll_once(self, scope, capability):
        from game_assistant.accounts.store import AccountNotFoundError
        key = (scope, capability)
        async with self._locks.setdefault(key, asyncio.Lock()):
            info = self.query.validate(scope, capability)
            provider = self._providers.setdefault(info['provider'], asyncio.Semaphore(
                self.settings.cloud_provider_concurrency))
            async with provider, self._global:
                # Waiting for capacity can overlap revocation or relogin.
                try:
                    if self.accounts.describe(scope)['version'] != info['version']:
                        return FetchResult(ok=False, error_kind='account_changed')
                    adapter = self.query.adapter(scope)
                    adapter.prepare_refresh()
                    result = await asyncio.wait_for(adapter.fetch(Capability(capability)),
                                                    timeout=self.settings.cloud_upstream_timeout_seconds)
                except AccountNotFoundError:
                    return FetchResult(ok=False, error_kind='account_changed')
                except Exception as error:
                    result = FetchResult(ok=False, error='数据源请求失败，请稍后重试', error_kind='source_error',
                                         failure_codes=f'exception:{type(error).__name__}')
                try:
                    current = self.accounts.describe(scope)
                except AccountNotFoundError:
                    return FetchResult(ok=False, error_kind='account_changed')
                version = result.credential_version if result.credential_version is not None else info['version']
                if current['version'] != version or result.error_kind == 'account_changed':
                    return FetchResult(ok=False, error_kind='account_changed')
                # No await between current grant check and synchronous snapshot commit.
                failed_kinds = []
                if result.ok and current['game'] == 'endfield' and capability == 'combat':
                    from game_assistant.endfield_challenges import challenge_reports, merge_challenge_snapshot
                    failed_kinds = [r['kind'] for r in challenge_reports(result.payload) if r['stale']]
                    previous = self.query.snapshots.get_scoped(scope, capability, grant_version=version,
                        minimum_version=self.accounts.snapshot_generation(scope, version))
                    result.payload = merge_challenge_snapshot(json.loads(previous['payload']) if previous else None,
                                                              result.payload)
                if result.ok:
                    self.query.snapshots.save_scoped(scope, capability, _serialize(result.payload), version)
                # Never persist arbitrary exception/upstream messages from adapters.
                if not result.ok:
                    result.error = '授权已失效，请重新授权' if result.error_kind == 'auth_expired' else '数据源暂时不可用，保留上次数据'
                status = self.query.snapshots.record_poll_scoped(scope, capability, result, version)
                if not result.ok or failed_kinds:
                    # Counts and short fixed codes only; never scope identifiers or upstream messages.
                    logger.warning('scoped_poll_failed game=%s capability=%s state=%s error_code=%s failed_kinds=%s failed_codes=%s',
                                current['game'], capability, status['state'], result.error_code, ','.join(failed_kinds) or '-',
                                result.failure_codes or '-')
                if self.reminders:
                    try:
                        self.reminders.handle_poll(scope, capability, result, version)
                    except Exception:
                        logger.warning('Scoped reminder evaluation failed')
                delay = self._next_delay(current['game'], capability, status)
                self._due[key] = self.clock() + max(30, delay)
                if result.ok and current['game'] == 'wuthering_waves' and capability in ('roles', 'combat') and self.query.private:
                    try:
                        self.query.private.ledger(scope, 'wuwa_history').capture(scope, capability,
                            json.loads(_serialize(result.payload)))
                    except Exception:
                        logger.warning('Scoped history capture failed')
                return result

    def public_refresh_state(self, game):
        item = self._pending.get(('public', game))
        if not item or item[1].done():
            return 'idle'
        return 'running' if game in self._public_running else 'queued'

    def request_bilibili_refresh(self, game, backfill=False):
        import time
        from fastapi import HTTPException
        bili = getattr(self.public, 'bilibili', None)
        if not bili or game not in bili.sources:
            raise HTTPException(404, 'source_not_configured')
        if not self._running:
            raise HTTPException(503, 'scheduler_unavailable')
        if self.public_refresh_state(game) != 'idle':
            raise HTTPException(409, 'source_busy')
        if time.time() < bili.store.state(game, bili.sources[game]).get('next_retry', 0):
            raise HTTPException(409, 'source_backoff')
        return self._queue(('public', game), lambda: self._poll_public(game, bili_only=True, backfill=backfill))

    def public_result(self, game):
        return self._public_results.get(game) or dict(generation=0, outcome=None)

    def request_public_refresh(self, game, backfill=True):
        """Administrator collect: one immediate full public poll for the game.

        Shares the ('public', game) queue key, so a queued or running job for the
        game is merged instead of starting another one."""
        from fastapi import HTTPException
        if not self.public or game not in self.public.sources:
            raise HTTPException(404, 'source_not_configured')
        if not self._running:
            raise HTTPException(503, 'scheduler_unavailable')
        return self._queue(('public', game), lambda: self._poll_public(game, force=True, backfill=backfill))

    async def _poll_public(self, game, *, bili_only=False, backfill=False, force=False):
        from datetime import datetime, timezone
        key = ('public', game)
        provider = self._providers.setdefault(self.public.provider(game), asyncio.Semaphore(
            self.settings.cloud_provider_concurrency))
        outcome = dict(state='failed', scope='bilibili' if bili_only else 'public', bilibili=None, failed=[])
        try:
            async with provider, self._global:
                self._public_running.add(game)
                if bili_only:
                    await self.public.bilibili.run(game, backfill, history_days=60 if backfill else None)
                    state = self.public.bilibili.store.state(game, self.public.bilibili.sources[game])
                    outcome.update(bilibili='error' if state.get('status') == 'error' else 'ok')
                else:
                    outcome.update(await (self.public.poll(game, force=True, backfill=backfill) if force
                                          else self.public.poll(game)) or {})
                outcome['state'] = 'failed' if outcome['bilibili'] == 'error' or outcome['failed'] else 'done'
        except Exception:
            logger.warning('Cloud public source poll failed')
        finally:
            self._public_running.discard(game)
            if not bili_only:
                self._due[key] = self.clock() + self.settings.cloud_public_poll_seconds
            previous = self._public_results.get(game, {}).get('generation', 0)
            self._public_results[game] = dict(generation=previous + 1,
                outcome={**outcome, 'finished_at': datetime.now(timezone.utc).isoformat()})

    async def tick(self):
        from game_assistant.accounts.models import AccountScope
        from game_assistant.accounts.store import AccountNotFoundError
        from game_assistant.auth.store import CredentialStoreError
        import hashlib
        rows = self.accounts.connection.execute("SELECT a.user_id,a.account_id,r.role_id FROM accounts a "
            "JOIN grants g ON g.grant_id=a.grant_id JOIN roles r ON r.account_id=a.account_id "
            "JOIN users u ON u.user_id=a.user_id WHERE g.state='active' AND u.disabled_at IS NULL").fetchall()
        for row in rows:
            scope = AccountScope(*row)
            try:
                if self._paused(scope):
                    continue
                for cap in self.query.capabilities(scope):
                    key = (scope, cap)
                    if key not in self._due:
                        jitter = int(hashlib.sha256(repr(key).encode()).hexdigest()[:8], 16) % 30
                        self._due[key] = max(self.clock() + jitter, self._persisted_due(scope, cap))
                    if self.clock() >= self._due[key]:
                        self.request_refresh(scope, cap)
            except (AccountNotFoundError, CredentialStoreError):
                continue
        if self.public:
            for game in self.public.sources:
                key = ('public', game)
                if self.clock() >= self._due.get(key, 0):
                    self._queue(key, lambda game=game: self._poll_public(game))

    async def _run(self):
        while True:
            try:
                await self.tick()
            except Exception:
                logger.warning('Cloud scheduling cycle failed')
            await asyncio.sleep(5)

    async def drain(self):
        await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def shutdown(self):
        self._running = False
        if self._invalidate in self.accounts._listeners:
            self.accounts._listeners.remove(self._invalidate)
        tasks = ([self._loop] if self._loop else []) + list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._pending.clear()
        self._tasks.clear()
        self._loop = None
        self.lease.close()
