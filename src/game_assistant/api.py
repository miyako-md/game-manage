from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request

from game_assistant.config import Settings
from game_assistant.registry import build_default_registry
from game_assistant.snapshots import SnapshotStore


def _stale(fetched_at: str, interval_seconds: int) -> bool:
    dt = datetime.fromisoformat(fetched_at)
    age = (datetime.now(timezone.utc) - dt).total_seconds()
    return age > 2 * max(interval_seconds, 60)


def create_app(registry=None, store=None, scheduler=None, notifier=None,
               settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    app = FastAPI(title="Game Assistant")
    app.state.settings = settings
    app.state.registry = registry if registry is not None else build_default_registry(settings)
    if store is None:
        from pathlib import Path
        Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
        store = SnapshotStore(settings.db_path)
    app.state.store = store
    app.state.scheduler = scheduler
    app.state.notifier = notifier

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/games")
    async def games() -> list[dict]:
        return [{
            "game_id": a.game_id, "display_name": a.display_name,
            "section": a.section,
            "capabilities": [c.value for c in a.capabilities],
            "credentials_configured": a.credentials_configured,
        } for a in app.state.registry.all()]

    @app.get("/api/games/{game_id}/snapshot/{capability}")
    async def snapshot(game_id: str, capability: str) -> dict:
        try:
            adapter = app.state.registry.get(game_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="未注册的游戏")
        snap = app.state.store.get(game_id, capability)
        if snap is None:
            return {"game_id": game_id, "capability": capability,
                    "payload": None, "fetched_at": None, "stale": False}
        interval = {
            "stamina": settings.stamina_seconds,
            "activity": settings.activity_seconds,
            "announcement": settings.announcement_seconds,
            "news": settings.news_seconds,
            "account": settings.activity_seconds,
        }.get(capability, 3600)
        import json
        return {"game_id": game_id, "capability": capability,
                "payload": json.loads(snap["payload"]),
                "fetched_at": snap["fetched_at"],
                "stale": _stale(snap["fetched_at"], interval)}

    @app.get("/api/status")
    async def status() -> dict:
        notifier = app.state.notifier
        enabled = bool(notifier and getattr(notifier, "send_key", "") )
        provider = getattr(notifier, "provider", None)
        return {"notify": {"enabled": enabled, "provider": provider}}

    return app
