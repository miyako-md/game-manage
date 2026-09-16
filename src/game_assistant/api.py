from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from game_assistant.config import Settings
from game_assistant.models import Capability
from game_assistant.notify.base import build_notifier
from game_assistant.registry import build_default_registry
from game_assistant.reminder import ReminderEngine
from game_assistant.reminder_store import ReminderDedup
from game_assistant.scheduler import PollingScheduler, interval_for
from game_assistant.snapshots import SnapshotStore


def _stale(fetched_at: str, interval_seconds: int) -> bool:
    dt = datetime.fromisoformat(fetched_at)
    age = (datetime.now(timezone.utc) - dt).total_seconds()
    return age > 2 * max(interval_seconds, 60)


def create_app(registry=None, store=None, scheduler=None, notifier=None,
               settings: Settings | None = None,
               start_scheduler: bool = True, auth_service=None) -> FastAPI:
    settings = settings or Settings.load()
    if auth_service is None:
        from pathlib import Path
        from game_assistant.auth.service import LoginService
        from game_assistant.auth.store import CredentialStore
        auth_path = settings.auth_store_path or str(Path(settings.db_path).with_suffix('.credentials.json'))
        auth_service = LoginService(settings, CredentialStore(auth_path))
    app = FastAPI(title="Game Assistant")
    app.state.settings = settings
    app.state.registry = registry if registry is not None else build_default_registry(settings)
    if store is None:
        from pathlib import Path
        Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
        store = SnapshotStore(settings.db_path)
    app.state.store = store
    app.state.auth = auth_service
    auth_service.attach(app.state.registry, store)
    from game_assistant.auth.routes import install_auth_routes
    install_auth_routes(app, auth_service, settings)
    from game_assistant.adapters.wuthering_waves.routes import install_wuwa_routes
    install_wuwa_routes(app)
    from game_assistant.sources.bilibili_service import BilibiliService
    from game_assistant.sources.bilibili_routes import install_bilibili_routes
    from game_assistant.sources.public_content import MOBILE_GAMES, merge_events, merge_news
    sources = {game: str(uid) for game, uid in settings.bilibili_sources.items()
               if game in {a.game_id for a in app.state.registry.all()} and str(uid).isdigit()}
    bili = BilibiliService(settings, sources) if sources else None
    app.state.bilibili = bili
    install_bilibili_routes(app, bili)
    app.state.scheduler = scheduler
    # main.py 走默认路径时不传 notifier：在此统一解析，保证 state 与 scheduler
    # 持同一 notifier 实例，/api/status 不会恒报"未配置"
    notifier = notifier or build_notifier(settings)
    app.state.notifier = notifier

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "service": "game-assistant"}

    def poll_status(game_id: str, capability: str, snap=None) -> dict:
        observed_at = datetime.now(timezone.utc).isoformat()
        stored = app.state.store.get_poll_status(game_id, capability)
        if stored is not None:
            return {**stored, "observed_at": observed_at}
        snap = snap or app.state.store.get(game_id, capability)
        return {"game_id": game_id, "capability": capability, "state": "never",
                "last_attempt_at": None, "last_success_at": snap["fetched_at"] if snap else None,
                "consecutive_failures": 0, "error": None, "error_kind": None, "observed_at": observed_at}

    @app.get("/api/games")
    async def games() -> list[dict]:
        def capabilities(adapter):
            caps = [c.value for c in adapter.capabilities]
            if adapter.game_id in sources and adapter.game_id in MOBILE_GAMES:
                caps = [c for c in caps if c != 'announcement']
                caps += [c for c in ('news', 'events') if c not in caps]
            return caps
        return [{
            "game_id": a.game_id, "display_name": a.display_name,
            "section": a.section,
            "capabilities": capabilities(a),
            "credentials_configured": a.credentials_configured,
        } for a in app.state.registry.all()]

    @app.get("/api/games/{game_id}/snapshot/{capability}")
    async def snapshot(game_id: str, capability: str) -> dict:
        try:
            adapter = app.state.registry.get(game_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="未注册的游戏")
        snap = app.state.store.get(game_id, capability)
        source_status = poll_status(game_id, capability, snap)
        if capability in ('news', 'events') and bili and game_id in sources and game_id in MOBILE_GAMES:
            import json
            state = bili.store.state(game_id, sources[game_id])
            rows = json.loads(snap['payload']) if snap else []
            rows = rows if isinstance(rows, list) else []
            native_stale = bool(snap and (_stale(snap['fetched_at'], settings.news_seconds) or source_status['state'] in ('error', 'auth_expired')))
            rows = [{**r, 'source_stale': native_stale} for r in rows]
            calendar = None
            if capability == 'news':
                announcements = app.state.store.get(game_id, 'announcement')
                if announcements:
                    extra = json.loads(announcements['payload'])
                    if isinstance(extra, list):
                        rows += [{**r, 'source_stale': _stale(announcements['fetched_at'], settings.news_seconds)} for r in extra]
                primary = bili.news(game_id)
                rows = merge_news(primary, rows)
            else:
                calendar = bili.calendar(game_id)
                primary = calendar['events']
                rows = merge_events(primary, rows, calendar['version'])
            if primary or snap is None:
                source_status = {**source_status, 'scope': 'public_source',
                    'state': 'error' if state.get('status') == 'error' else 'ok' if rows else 'never',
                    'error': state.get('message') if state.get('status') == 'error' else None,
                    'last_success_at': max((r.get('fetched_at', '') for r in rows), default=None),
                    'last_attempt_at': state.get('last_attempt'), 'consecutive_failures': state.get('failures', 0)}
            return {'game_id': game_id, 'capability': capability,
                    'payload': rows if rows or snap or state.get('last_success') else None,
                    'fetched_at': max(filter(None, [snap['fetched_at'] if snap else None, state.get('last_success'), *[r.get('fetched_at') for r in rows]]), default=None),
                    'stale': bool(rows) and all(r.get('source_stale', False) for r in rows),
                    'poll_status': source_status, 'bilibili_status': state,
                    'primary_source': 'bilibili' if primary else 'community',
                    'version': calendar['version'] if calendar else None}
        if snap is None:
            return {"game_id": game_id, "capability": capability,
                    "payload": None, "fetched_at": None, "stale": False,
                    "poll_status": source_status}
        try:
            interval = interval_for(Capability(capability), settings)
        except (KeyError, ValueError):
            interval = 3600
        import json
        return {"game_id": game_id, "capability": capability,
                "payload": json.loads(snap["payload"]),
                "fetched_at": snap["fetched_at"],
                "stale": _stale(snap["fetched_at"], interval) or source_status["state"] in ("error", "auth_expired"),
                "poll_status": source_status}

    @app.get("/api/status")
    async def status() -> dict:
        notifier = app.state.notifier
        enabled = bool(notifier and getattr(notifier, "send_key", "") )
        provider = getattr(notifier, "provider", None)
        return {"notify": {"enabled": enabled, "provider": provider},
                "collection": [poll_status(adapter.game_id, cap.value)
                               for adapter in app.state.registry.all()
                               for cap in adapter.capabilities]}

    if scheduler is None and start_scheduler:
        # 默认路径：notifier → 提醒引擎 → 调度器（引擎随每轮轮询评估提醒规则）
        engine = ReminderEngine(ReminderDedup(settings.db_path), notifier,
                                settings)
        scheduler = PollingScheduler(app.state.registry, app.state.store,
                                     settings, notifier, reminder=engine)
    app.state.scheduler = scheduler

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if app.state.scheduler:
            app.state.scheduler.start()
        if bili and start_scheduler:
            bili.start()
        yield
        if app.state.scheduler:
            await app.state.scheduler.shutdown()
        if bili:
            await bili.close()

    @app.get("/api/games/{game_id}/match/{match_id}/detail")
    async def match_detail(game_id: str, match_id: str) -> dict:
        # 对局详情按需实时拉取（不写快照）；仅支持实现了 fetch_match_detail
        # 的适配器（LoL），其余 404
        try:
            adapter = app.state.registry.get(game_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="未注册的游戏")
        if not hasattr(adapter, "fetch_match_detail"):
            raise HTTPException(status_code=404, detail="该游戏不支持对局详情")
        result = await adapter.fetch_match_detail(match_id)
        if result.ok:
            return {"payload": result.payload.model_dump(mode="json")}
        # 失败走 200 + {"error"}，前端展示错误条（与 refresh 行为一致）
        return {"error": result.error}

    @app.post("/api/games/{game_id}/refresh")
    async def refresh(game_id: str) -> dict:
        try:
            adapter = app.state.registry.get(game_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="未注册的游戏")
        adapter.prepare_refresh()
        if bili and game_id in sources and game_id in MOBILE_GAMES:
            bili.trigger(game_id)
        results = {}
        for cap in adapter.capabilities:
            if app.state.scheduler:
                r = await app.state.scheduler.poll_once(game_id, cap)
            else:
                r = await adapter.fetch(cap)
            results[cap.value] = {"ok": r.ok, "error": r.error, "error_kind": r.error_kind}
        return {"results": results}

    app.router.lifespan_context = lifespan

    from game_assistant.web_ui import install_web_ui
    install_web_ui(app)

    return app
