"""Public curated role guides, protected by the application's local API boundary."""
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .nte_guides import GuideService, GuideSourceError
from .nte_guides_catalog import SOURCES, guide_catalog


def install_nte_guides_routes(app, settings):
    service = GuideService(Path(settings.db_path).with_suffix('.nte-guides.sqlite3'))
    app.state.nte_guides = service
    router = APIRouter(prefix='/api/nte/guides')

    @router.get('')
    async def catalog():
        return guide_catalog()

    async def read(post_id, force=False):
        if post_id not in SOURCES: raise HTTPException(404, '未收录的攻略来源')
        try: return await service.read(post_id, force=force)
        except GuideSourceError as error: raise HTTPException(502, str(error)) from None

    @router.get('/sources/{post_id}')
    async def source(post_id: int):
        return await read(post_id)

    @router.post('/sources/{post_id}/refresh')
    async def refresh(post_id: int):
        return await read(post_id, force=True)

    app.include_router(router)
