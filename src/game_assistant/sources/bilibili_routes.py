from fastapi import HTTPException, Request
from game_assistant.auth.bilibili_routes import CookieBody
from .bilibili import SourceError

def install_bilibili_routes(app, service, login_service=None):
    @app.get('/api/sources/bilibili')
    async def statuses():
        return {'sources': service.statuses() if service else [], 'login': login_service.status() if login_service else {'configured': False}}

    @app.get('/api/sources/bilibili/{game}/audit')
    async def audit(game: str):
        if not service or game not in service.sources: raise HTTPException(404)
        return {'rows': service.store.rows(game, service.sources[game], days=service.settings.bilibili_history_days, limit=2000)}

    @app.post('/api/auth/bilibili-source/credentials')
    async def credentials(body: CookieBody, request: Request):
        if not login_service: raise HTTPException(404)
        return await login_service.import_legacy(body.values(), is_disconnected=request.is_disconnected)

    @app.post('/api/sources/bilibili/{game}/refresh', status_code=202)
    async def refresh(game: str, backfill: bool = False):
        if not service: raise HTTPException(404)
        try: service.trigger(game, backfill)
        except SourceError as e: raise HTTPException(400, str(e)) from None
        return {'queued': True}
