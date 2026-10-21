"""Reviewed public tools: website readers and administrator source maintenance.

Services keep their original source schemas and last-good SQLite caches. Cloud
composition adds aggregate budgets; no local credential/configuration is used.
"""
import asyncio
from collections import OrderedDict, deque
from contextvars import ContextVar
from pathlib import Path
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool

from .endfield_public import EndfieldPublicService, PublicSourceError
from .identity.dependencies import require_user
from .nte_guides import GuideService, GuideSourceError
from .nte_guides_catalog import SOURCES, guide_catalog
from .wuwa_guide_updates import GuideUpdates, Search, Selection


class CloudEndfieldPublicService(EndfieldPublicService):
    """Bound failure retries and aggregate requests even for varied map filters."""
    def __init__(self, path):
        super().__init__(path)
        self.attempts = deque()
        self.failures = OrderedDict()
        self.slots = asyncio.Semaphore(3)
        self.cache_only = ContextVar('endfield_cache_only', default=False)

    async def _request(self, url, params=None):
        if self.cache_only.get():
            raise PublicSourceError('公开来源读取超时，保留上次成功资料，请稍后重试')
        key = (url, tuple(sorted((params or {}).items())))
        now = time.monotonic()
        if now - self.failures.get(key, -1000) < 60:
            raise PublicSourceError('公开来源暂时不可用，保留上次成功资料，请稍后重试')
        while self.attempts and now - self.attempts[0] >= 60:
            self.attempts.popleft()
        if len(self.attempts) >= 32:
            raise PublicSourceError('公开来源请求过频，保留上次成功资料，请稍后重试')
        self.attempts.append(now)
        try:
            async with self.slots:
                return await super()._request(url, params)
        except (PublicSourceError, asyncio.CancelledError):
            self.failures[key] = time.monotonic()
            self.failures.move_to_end(key)
            while len(self.failures) > 128:
                self.failures.popitem(last=False)
            raise


class CloudPublicTools:
    TIMEOUT = 45
    FALLBACK_TIMEOUT = 1

    def __init__(self, settings):
        path = Path(settings.db_path)
        self.nte = GuideService(path.with_suffix('.nte-guides.sqlite3'))
        self.wuwa = GuideUpdates(path.with_suffix('.wuwa-guides.sqlite3'))
        self.endfield = CloudEndfieldPublicService(path)
        self.maintenance_attempts = {}

    def maintenance(self, kind):
        now = time.monotonic()
        if now - self.maintenance_attempts.get(kind, -1000) < 30:
            raise HTTPException(429, 'source_refresh_cooldown', headers={'Retry-After': '30'})
        self.maintenance_attempts[kind] = now

    async def bounded(self, operation):
        try:
            async with asyncio.timeout(self.TIMEOUT):
                return await operation()
        except TimeoutError:
            raise HTTPException(503, 'public_source_timeout') from None

    async def read_endfield(self, operation):
        try:
            return await self.bounded(operation)
        except HTTPException as error:
            if error.status_code != 503:
                raise
            # Run the original presentation with network disabled in this task;
            # its existing error path labels and retains the persisted cache.
            token = self.endfield.cache_only.set(True)
            try:
                async with asyncio.timeout(self.FALLBACK_TIMEOUT):
                    return await operation()
            except TimeoutError:
                raise HTTPException(503, 'public_source_timeout') from None
            finally:
                self.endfield.cache_only.reset(token)

    async def read_nte(self, post_id, force=False):
        if post_id not in SOURCES:
            raise HTTPException(404, '未收录的攻略来源')
        try:
            return await self.bounded(lambda: self.nte.read(post_id, force=force))
        except (GuideSourceError, HTTPException) as error:
            # A total deadline must also retain and label last-good guide data.
            if isinstance(error, HTTPException) and error.status_code != 503:
                raise
            cached = self.nte.cached(post_id)
            if cached:
                self.nte.errors[post_id] = '原帖暂时无法读取；保留上次成功资料，请稍后重试。'
                self.nte.save(post_id, {**cached, 'source_error': self.nte.errors[post_id]})
                return self.nte.present(cached, post_id)
            raise HTTPException(502, '原帖暂时无法读取，请稍后重试') from None

    def close(self):
        self.endfield.close()


def install_cloud_public_tools(app, settings):
    from .cloud_app import allow_cloud_route
    tools = CloudPublicTools(settings)
    app.state.cloud_public_tools = tools
    app.state.nte_guides = tools.nte
    app.state.wuwa_guide_updates = tools.wuwa
    app.state.endfield_public = tools.endfield
    readers = APIRouter(prefix='/api/public', dependencies=[Depends(require_user)])

    def admin(principal=Depends(require_user)):
        if not principal.is_admin:
            raise HTTPException(403, 'admin_required')

    writers = APIRouter(prefix='/api/admin', dependencies=[Depends(admin)])

    @readers.get('/nte/guides')
    async def catalog():
        return guide_catalog()

    @readers.get('/nte/guides/sources/{post_id}')
    async def nte_source(post_id: int):
        return await tools.read_nte(post_id)

    @writers.post('/nte/guides/sources/{post_id}/refresh')
    async def nte_refresh(post_id: int):
        if post_id not in SOURCES:
            raise HTTPException(404, '未收录的攻略来源')
        tools.maintenance('nte')
        return await tools.read_nte(post_id, force=True)

    @readers.get('/wuwa/guides/updates')
    async def wuwa_cached(query: Search = Depends()):
        return tools.wuwa.cached(query)

    @writers.post('/wuwa/guides/updates')
    async def wuwa_check(query: Search):
        tools.maintenance('wuwa-check')
        return await tools.bounded(lambda: tools.wuwa.check(query))

    @writers.post('/wuwa/guides/updates/extract')
    async def wuwa_extract(selection: Selection):
        tools.maintenance('wuwa-extract')
        query = Search(**selection.model_dump(exclude={'post_id'}))
        return await tools.bounded(lambda: tools.wuwa.extract(query, selection.post_id))

    @readers.get('/endfield/public')
    async def endfield_public():
        return await tools.read_endfield(tools.endfield.public)

    @writers.post('/endfield/public/refresh')
    async def endfield_refresh():
        tools.maintenance('endfield')
        return await tools.read_endfield(lambda: tools.endfield.public(force=True))

    @readers.get('/endfield/map')
    async def endfield_map(map_id: str | None = None, level_id: str | None = None,
                           type_id: str | None = None, q: str = '', offset: int = 0, limit: int = 100):
        try:
            return await tools.read_endfield(lambda: tools.endfield.map(map_id, level_id, type_id, q, offset, limit))
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    @readers.get('/endfield/map/marks/{mark_id}')
    async def endfield_mark(mark_id: str, map_id: str):
        try:
            return await tools.read_endfield(lambda: tools.endfield.map_mark_info(map_id, mark_id))
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    for router in (readers, writers):
        app.include_router(router)
        for route in router.routes:
            allow_cloud_route(app, route.path, route.methods)
    return tools


class CollectBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    backfill: StrictBool = True


class CloudCollect:
    """Administrator "collect and backfill": every public game now, plus the
    administrator's own private data. One global cooldown bounds upstream load."""
    COOLDOWN = 300

    def __init__(self, scheduler, accounts, query):
        self.scheduler, self.accounts, self.query = scheduler, accounts, query
        self.last = None
        self.clock = time.monotonic

    def retry_after(self):
        if self.last is None:
            return 0
        return max(0, int(self.COOLDOWN - (self.clock() - self.last) + 0.999))

    def games(self):
        return list(self.scheduler.public.sources) if self.scheduler.public else []

    def private(self, principal):
        from fastapi import HTTPException as RouteError
        from .accounts.store import AccountNotFoundError
        from .auth.store import CredentialStoreError
        requested = skipped = 0
        for account in self.accounts.list_accounts(principal):
            if account['state'] != 'active':
                continue
            for role in account['roles']:
                try:
                    scope = self.accounts.require_scope(principal, account['account_id'], role['role_id'])
                    for capability in self.query.capabilities(scope):
                        self.scheduler.request_refresh(scope, capability)
                        requested += 1
                except (RouteError, AccountNotFoundError, CredentialStoreError):
                    # Expired or unverifiable grants are skipped; their status stays visible.
                    skipped += 1
        return dict(requested=requested, skipped=skipped)

    def start(self, principal, backfill):
        games = []
        for game in self.games():
            generation = self.scheduler.public_result(game)['generation']
            receipt = self.scheduler.request_public_refresh(game, backfill)
            games.append(dict(game_id=game, job_id=receipt.job_id, generation=generation,
                              state='merged' if receipt.state == 'coalesced' else receipt.state))
        return dict(games=games, private_refresh=self.private(principal), backfill=backfill,
                    cooldown_seconds=self.COOLDOWN)

    def status(self):
        games = []
        for game in self.games():
            result = self.scheduler.public_result(game)
            games.append(dict(game_id=game, queue_state=self.scheduler.public_refresh_state(game),
                              generation=result['generation'], outcome=result['outcome']))
        return dict(games=games, retry_after=self.retry_after())


def install_cloud_collect_routes(app, scheduler, accounts, query):
    from fastapi.responses import JSONResponse
    from .cloud_app import allow_cloud_route
    collect = CloudCollect(scheduler, accounts, query)
    app.state.cloud_collect = collect

    def admin(principal=Depends(require_user)):
        if not principal.is_admin:
            raise HTTPException(403, 'admin_required')
        return principal

    router = APIRouter(prefix='/api/admin/collect')

    @router.get('')
    async def collect_status(principal=Depends(admin)):
        return collect.status()

    @router.post('')
    async def collect_now(body: CollectBody | None = None, principal=Depends(admin)):
        if not scheduler._running:
            raise HTTPException(503, 'scheduler_unavailable')
        wait = collect.retry_after()
        if wait:
            return JSONResponse({'detail': 'collect_cooldown', 'retry_after': wait},
                                status_code=429, headers={'Retry-After': str(wait)})
        collect.last = collect.clock()
        return collect.start(principal, body.backfill if body else True)

    app.include_router(router)
    for route in router.routes:
        allow_cloud_route(app, route.path, route.methods)
    return collect
