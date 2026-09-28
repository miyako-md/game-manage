"""Public Endfield news and map routes."""
from fastapi import APIRouter, HTTPException

from .endfield_public import EndfieldPublicService


def install_endfield_public_routes(app, settings):
    service = EndfieldPublicService(settings.db_path)
    app.state.endfield_public = service
    router = APIRouter(prefix='/api/endfield')

    @router.get('/public')
    async def public():
        return await service.public()

    @router.post('/public/refresh')
    async def refresh():
        return await service.public(force=True)

    @router.get('/map')
    async def map_data(map_id: str | None = None, level_id: str | None = None,
                       type_id: str | None = None, q: str = '', offset: int = 0,
                       limit: int = 100):
        try:
            return await service.map(map_id, level_id, type_id, q, offset, limit)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @router.get('/map/marks/{mark_id}')
    async def mark_info(mark_id: str, map_id: str):
        try:
            return await service.map_mark_info(map_id, mark_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    app.include_router(router)
