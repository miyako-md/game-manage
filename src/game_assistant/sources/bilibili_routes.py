from fastapi import HTTPException
from pydantic import BaseModel, Field
from .bilibili import SourceError

class BiliCredentials(BaseModel):
    sessdata: str = Field(min_length=1, max_length=4096)
    bili_jct: str = Field(default='', max_length=128)
    buvid3: str = Field(default='', max_length=256)

def install_bilibili_routes(app, service):
    @app.get('/api/sources/bilibili')
    async def statuses():
        return {'sources': service.statuses() if service else [], 'login': service.login_state() if service else {'configured': False}}

    @app.get('/api/sources/bilibili/{game}/audit')
    async def audit(game: str):
        if not service or game not in service.sources: raise HTTPException(404)
        return {'rows': service.store.rows(game, service.sources[game], days=service.settings.bilibili_history_days, limit=2000)}

    @app.post('/api/auth/bilibili-source/credentials')
    async def credentials(body: BiliCredentials):
        if not service: raise HTTPException(404)
        try: service.save_credentials(body.model_dump())
        except SourceError as e: raise HTTPException(409, str(e)) from None
        return {'ok': True, **service.login_state()}

    @app.post('/api/sources/bilibili/{game}/refresh', status_code=202)
    async def refresh(game: str, backfill: bool = False):
        if not service: raise HTTPException(404)
        try: service.trigger(game, backfill)
        except SourceError as e: raise HTTPException(400, str(e)) from None
        return {'queued': True}
