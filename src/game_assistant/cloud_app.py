"""Explicit, fail-closed cloud entrypoint, independent of the local API app.

Run with: python -m game_assistant.cloud_runtime --config <cloud.toml>, which checks the
runtime configuration before building this app (see docs/cloud-operations.md).
Only loopback reverse proxies may supply a single X-Forwarded-For address.
"""

from ipaddress import ip_address
from contextlib import asynccontextmanager
import inspect
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse
from starlette.routing import compile_path

from .api_security import _authority, _origin
from .config import Settings
from .identity.routes import install_identity_routes
from .identity.service import IdentityError, IdentityService
from .identity.store import IdentityStore


def source_ip(request: Request) -> str:
    peer = request.client.host if request.client else 'unknown'
    try:
        trusted = ip_address(peer).is_loopback
    except ValueError:
        trusted = False
    forwarded = request.headers.getlist('x-forwarded-for')
    if trusted and len(forwarded) == 1:
        try:
            return str(ip_address(forwarded[0].strip()))
        except ValueError:
            pass
    return peer


def allow_cloud_route(app: FastAPI, path: str, methods, *, access='user', body_limit=None):
    """Explicit policy registration. Adding a FastAPI route alone grants no access.

    Future service routes require app.state.service_authenticator(request), an
    independent credential validator. Its default is absent, always denying.
    Public/preauth are reserved for reviewed non-private endpoints.
    """
    if access not in {'user', 'public', 'preauth', 'service'}:
        raise ValueError('Unknown cloud route access policy')
    if body_limit is not None and (access != 'user' or type(body_limit) is not int or not 1 <= body_limit <= 8 * 1024 * 1024):
        raise ValueError('Invalid private route body limit')
    regex, _, _ = compile_path(path)
    methods = frozenset(method.upper() for method in methods)
    for old_regex, old_methods, _ in app.state.cloud_route_policy:
        if old_regex.pattern == regex.pattern and old_methods & methods:
            raise ValueError('Cloud route policy already exists')
    app.state.cloud_route_policy.append((regex, methods, access))
    if body_limit is not None:
        if not hasattr(app.state, 'cloud_route_body_limits'):
            app.state.cloud_route_body_limits = {}
        for method in methods:
            app.state.cloud_route_body_limits[(regex.pattern, method)] = body_limit


class CloudBoundary:
    """Raw ASGI boundary reads bounded chunks before dispatching any route."""
    def __init__(self, app, owner, settings):
        self.app, self.owner, self.settings = app, owner, settings
        self.origins = {_origin(value) for value in settings.cloud_allowed_origins}
        if not self.origins or None in self.origins or any(origin[0] != 'https' for origin in self.origins):
            raise ValueError('Cloud origins must be explicit HTTPS origins')
        self.authorities = {(origin[1], origin[2]) for origin in self.origins}

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            if scope['type'] == 'websocket':
                await send({'type': 'websocket.close', 'code': 1008})
            else:
                await self.app(scope, receive, send)
            return
        request = Request(scope)
        static = False
        async def secured_send(message):
            if message['type'] == 'http.response.start':
                # Build files are named by content hash, so one name never changes meaning.
                cache = ([(b'cache-control', b'public, max-age=31536000, immutable')] if static and message['status'] == 200
                         else [(b'cache-control', b'no-store'), (b'pragma', b'no-cache')])
                message['headers'] = list(message.get('headers', [])) + cache + [
                    (b'referrer-policy', b'no-referrer'), (b'x-content-type-options', b'nosniff')]
            await send(message)
        async def reject(code, status):
            await JSONResponse({'detail': code}, status_code=status)(scope, receive, secured_send)

        hosts = request.headers.getlist('host')
        authority = _authority(hosts[0]) if len(hosts) == 1 else None
        normalized = (authority[0], 443 if authority[1] is None else authority[1]) if authority else None
        origins = request.headers.getlist('origin')
        fetch_sites = request.headers.getlist('sec-fetch-site')
        if (normalized not in self.authorities or (origins and (len(origins) != 1 or _origin(origins[0]) not in self.origins))
                or (fetch_sites and (len(fetch_sites) != 1 or fetch_sites[0] == 'cross-site'))):
            return await reject('untrusted_origin', 403)

        access = None
        body_limit = self.settings.cloud_body_limit_bytes
        for regex, methods, policy in self.owner.state.cloud_route_policy:
            if scope['method'] in methods and regex.fullmatch(scope['path']):
                access = policy
                body_limit = getattr(self.owner.state, 'cloud_route_body_limits', {}).get(
                    (regex.pattern, scope['method']), body_limit)
                break
        if access is None:
            return await reject('route_not_available', 404)
        static = access == 'public' and scope['method'] in ('GET', 'HEAD') and scope['path'].startswith('/assets/')
        service = self.owner.state.identity
        session = None if access == 'service' or static else service.authenticate(request.cookies.get('__Host-ga_session'))
        scope.setdefault('state', {})['identity_session'] = session
        try:
            if access == 'service':
                validator = self.owner.state.service_authenticator
                # Cookie cannot authenticate this path; require dedicated bearer credentials.
                authorization = request.headers.getlist('authorization')
                if validator is None or len(authorization) != 1 or not authorization[0].startswith('Bearer '):
                    raise IdentityError('service_authentication_required', 401)
                result = validator(request)
                if inspect.isawaitable(result):
                    result = await result
                if not result:
                    raise IdentityError('service_authentication_required', 401)
                scope['state']['service_principal'] = result
            elif access == 'user' and session is None:
                raise IdentityError('authentication_required', 401)
            if scope['method'] not in {'GET', 'HEAD', 'OPTIONS'} and access != 'service':
                tokens = request.headers.getlist('x-csrf-token')
                service.check_csrf(session, request.cookies.get('__Host-ga_preauth'),
                                   tokens[0] if len(tokens) == 1 else None, preauth=access == 'preauth')
        except IdentityError as error:
            return await reject(error.code, error.status_code)

        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            size += len(chunk)
            if size > body_limit:
                return await reject('body_too_large', 413)
            chunks.append(chunk)
            if not message.get('more_body', False):
                break
        body, delivered = b''.join(chunks), False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            return await receive()
        await self.app(scope, bounded_receive, secured_send)


def create_cloud_app(settings: Settings, start_scheduler: bool = True) -> FastAPI:
    if Path(settings.cloud_db_path).resolve() == Path(settings.db_path).resolve():
        raise ValueError('Cloud and local database paths must differ')
    # Validate before touching any database or deferring middleware construction.
    origins = {_origin(value) for value in settings.cloud_allowed_origins}
    if not origins or None in origins or any(origin[0] != 'https' for origin in origins):
        raise ValueError('Cloud origins must be explicit HTTPS origins')
    @asynccontextmanager
    async def lifespan(app):
        if not settings.cloud_accounts_enabled:
            yield
            return
        import sqlite3
        from .accounts.service import AccountService
        from .accounts.runtime import AccountRuntime
        from .accounts.query import AccountQuery, CloudPublicQuery
        from .accounts.routes import install_account_routes
        from .auth.service import ScopedLoginService, FIELDS
        from .auth.store import CredentialStore
        from .private_routes import install_cloud_private_routes
        from .registry import build_default_registry
        from .scheduler import AccountPollingScheduler
        from .snapshots import SnapshotStore
        from .sources.bilibili_service import BilibiliService

        root = Path(settings.cloud_data_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        # This connection is created, used, and closed on the event-loop thread.
        connection = sqlite3.connect(settings.cloud_db_path, timeout=10)
        connection.execute('PRAGMA foreign_keys=ON')
        runtime = private = scheduler = snapshots = public = bili_login = public_tools = reminder_store = reminders = assessment_store = None
        original_routes = list(app.router.routes)
        original_policy = list(app.state.cloud_route_policy)
        try:
            credentials = CredentialStore(root / 'unused', connection=connection,
                key_path=settings.cloud_credentials_key_path or None)
            credentials._grant_key()  # fail startup clearly; never provision/replace a key
            accounts = AccountService(connection, credentials)
            from .scoped_reminders import ReminderStore, ScopedReminderService
            from .group_settings import GroupSettingsService
            from .reminder_routes import install_reminder_routes
            reminder_store = ReminderStore(root / 'reminders.db')
            reminders = ScopedReminderService(reminder_store, accounts)
            groups = GroupSettingsService(reminder_store)
            app.state.reminders = reminders
            app.state.qq_group_settings = groups
            install_reminder_routes(app, reminders, groups)
            login = ScopedLoginService(accounts, public_ip_url=settings.wuwa_login_public_ip_url)
            private_root = root / 'private'
            runtime = AccountRuntime(accounts, settings, private_root, login=login)
            snapshots = SnapshotStore(str(root / 'snapshots.db'))
            private = install_cloud_private_routes(app, accounts, runtime, private_root, snapshots=snapshots)
            accounts.clear_private = private.clear_private
            private.allowlist(app)
            from .assessment_routes import install_assessment_routes
            assessment_store = install_assessment_routes(app, accounts, private_root, snapshots)
            query = AccountQuery(accounts, runtime, snapshots, private=private)
            query.assessments = assessment_store

            # Public sources never inherit local/community game credentials.
            public_settings = settings.model_copy(deep=True)
            for mapping in FIELDS.values():
                for field in mapping.values():
                    setattr(public_settings, field, '')
            public_settings.wuwa_app_token = public_settings.notify_send_key = ''
            public_settings.qq_service_token = ''
            public_settings.auth_store_path = ''
            public_settings.lol_enabled = False
            public_settings.nte_events = []
            public_settings.db_path = str(root / 'public.db')
            from .cloud_public_tools import install_cloud_public_tools
            public_tools = install_cloud_public_tools(app, public_settings)
            registry = build_default_registry(public_settings)
            sources = {game:str(uid) for game,uid in settings.bilibili_sources.items()
                       if game in {a.game_id for a in registry.all()} and str(uid).isdigit()}
            from .auth.cloud_bilibili import CloudBilibiliCredentialStore, CloudBilibiliLoginService, install_cloud_bilibili_routes
            bili = BilibiliService(public_settings, sources,
                credential_store=CloudBilibiliCredentialStore(credentials)) if sources else None
            bili_login = CloudBilibiliLoginService(bili, app.state.identity)
            app.state.bilibili_login = bili_login
            install_cloud_bilibili_routes(app, bili_login)
            public = CloudPublicQuery(registry, snapshots, bilibili=bili, settings=public_settings)
            scheduler = AccountPollingScheduler(accounts, query, settings, root, public=public, reminders=reminders)
            from .sources.cloud_bilibili_routes import install_cloud_bilibili_collection_routes
            install_cloud_bilibili_collection_routes(app, bili, scheduler)
            from .cloud_public_tools import install_cloud_collect_routes
            install_cloud_collect_routes(app, scheduler, accounts, query)
            query.scheduler = scheduler
            for name,value in dict(accounts=accounts,account_runtime=runtime,account_query=query,
                                   private_routes=private,store=snapshots,public_query=public,
                                   scheduler=scheduler,bilibili=bili).items():
                setattr(app.state,name,value)
            router = install_account_routes(app, accounts, login, query=query)
            for route in router.routes:
                allow_cloud_route(app, route.path, route.methods)

            if settings.qq_app_id and settings.qq_service_token:
                from .qq.query_routes import install_qq_query_routes
                install_qq_query_routes(app, app_id=settings.qq_app_id,
                    dashboard_url=settings.qq_dashboard_url,
                    urls_approved=settings.qq_dashboard_urls_approved)

            from dataclasses import asdict
            @app.get('/api/public/games/{game_id}/{capability}')
            async def public_snapshot(game_id:str,capability:str):
                result = public.read(game_id,capability)
                return {**asdict(result),'game_id':game_id,'capability':capability}
            # Public means no game credentials; website session remains mandatory.
            allow_cloud_route(app, '/api/public/games/{game_id}/{capability}', ['GET'])
            from .system_update import background_start_after_maintenance
            def start_background():
                if start_scheduler:
                    scheduler.start()
                    # QQ image browser warm-up (no-op unless QQ images are enabled).
                    if getattr(app.state, 'qq_query', None) is not None:
                        app.state.qq_query.start_prewarm()
            async with background_start_after_maintenance(app.state.system_update, start_background):
                yield
        finally:
            # One failed closer must not skip the remaining account/private resources.
            cleanup_errors = []
            qq_query = getattr(app.state, 'qq_query', None)
            closers = [scheduler.shutdown if scheduler else None, assessment_store.close if assessment_store else None, bili_login.aclose if bili_login else None,
                       public.aclose if public else None,
                       qq_query.aclose if qq_query else None,
                       public_tools.close if public_tools else None,
                       runtime.aclose if runtime else None, private.close if private else None,
                       snapshots._conn.close if snapshots else None,
                       reminders.close if reminders else reminder_store.close if reminder_store else None, connection.close]
            for close in filter(None, closers):
                try:
                    result = close()
                    if inspect.isawaitable(result):
                        await result
                except Exception as error:
                    cleanup_errors.append(error)
            # Re-entering lifespan must never retain handlers bound to closed services.
            app.router.routes[:] = original_routes
            app.state.cloud_route_policy[:] = original_policy
            if cleanup_errors:
                raise RuntimeError('Cloud resource cleanup failed') from None

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False,
                  lifespan=lifespan)
    app.state.settings = settings
    app.state.identity = IdentityService(IdentityStore(settings.cloud_db_path), settings)
    app.state.cloud_route_policy = []
    app.state.service_authenticator = None

    @app.exception_handler(IdentityError)
    async def identity_error(request, error):
        return JSONResponse({'detail': error.code}, status_code=error.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse({'detail': 'invalid_request'}, status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return JSONResponse({'detail': error.detail}, status_code=error.status_code)

    # Starlette captures exception handlers when it first builds middleware,
    # before lifespan starts. Register composition errors now, not in lifespan.
    if settings.cloud_accounts_enabled:
        from .accounts.store import AccountNotFoundError
        from .auth.store import CredentialStoreError
        from .auth.service import LoginError
        from .auth.bilibili_service import BilibiliLoginError
        from .nte_gacha import GachaError

        @app.exception_handler(AccountNotFoundError)
        async def missing_account(request, error):
            return JSONResponse({'error_code':'account_not_found','detail':'账号或角色不存在'},status_code=404)

        @app.exception_handler(CredentialStoreError)
        async def unavailable_credentials(request, error):
            return JSONResponse({'error_code':'credential_unavailable','detail':'授权凭据不可用'},status_code=503)

        @app.exception_handler(LoginError)
        async def account_login_error(request, error):
            return JSONResponse({'error_code':error.error_kind or 'login_failed','detail':error.message},
                                status_code=error.status)

        @app.exception_handler(BilibiliLoginError)
        async def bilibili_login_error(request, error):
            return JSONResponse({'detail':error.detail,'error_code':error.error_code,
                **({'state':error.state} if error.state else {}),
                **({'retry_after':error.retry_after} if error.retry_after else {})},
                status_code=error.status, headers={'Retry-After':str(error.retry_after)} if error.retry_after else None)

        @app.exception_handler(GachaError)
        async def invalid_ledger(request, error):
            return JSONResponse({'error_code':'invalid_gacha_input','detail':str(error)},status_code=error.status)

    from .system_update import install_system_update
    install_system_update(app, settings, cloud=True)

    @app.get('/api/health')
    async def health():
        ready = False
        try:
            with app.state.identity.store.connect() as db:
                db.execute('SELECT 1').fetchone()
            if settings.cloud_accounts_enabled:
                app.state.accounts.connection.execute('SELECT 1').fetchone()
                app.state.store._conn.execute('SELECT 1').fetchone()
            ready = app.state.running_version.ready
        except Exception:
            # A healthy listener does not prove that an update activated matching assets/data.
            pass
        body = {'status': 'ok', 'version': app.state.running_version.health(), 'ready': bool(ready)}
        if app.state.system_update.background_start_error:
            body.update(ready=False, background_start='failed')
        return body

    install_identity_routes(app)
    from .qq.internal_routes import install_qq_routes
    install_qq_routes(app)
    if settings.qq_app_id and settings.qq_service_token and not settings.cloud_accounts_enabled:
        from .qq.query_routes import install_qq_query_routes
        install_qq_query_routes(app, app_id=settings.qq_app_id,
            dashboard_url=settings.qq_dashboard_url,
            urls_approved=settings.qq_dashboard_urls_approved)
    allow_cloud_route(app, '/api/health', ['GET'], access='public')
    allow_cloud_route(app, '/api/identity/csrf', ['GET'], access='public')
    for action in ('register', 'login', 'recover'):
        allow_cloud_route(app, '/api/identity/' + action, ['POST'], access='preauth')
    for action in ('me', 'sessions'):
        allow_cloud_route(app, '/api/identity/' + action, ['GET'])
    allow_cloud_route(app, '/api/identity/logout', ['POST'])
    allow_cloud_route(app, '/api/identity/sessions/{session_id}', ['DELETE'])
    from .cloud_compression import CloudReadCompression
    app.add_middleware(CloudReadCompression)
    app.add_middleware(CloudBoundary, owner=app, settings=settings)
    return app
