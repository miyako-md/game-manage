"""终末地寻访账本只读接口；同步由适配器的 GACHA 能力轮询和「刷新数据」触发。"""
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import JSONResponse

from .endfield_gacha import EndfieldGachaStore, store_path


def install_endfield_gacha_routes(app, settings):
    store = EndfieldGachaStore(store_path(settings.db_path))
    router = APIRouter(prefix='/api/endfield/gacha')

    def role():
        identity = str(app.state.settings.endfield_role_id or '').strip()
        if not identity:
            raise HTTPException(status_code=409, detail='请先登录终末地')
        return identity

    @router.get('/summary')
    async def summary():
        return store.summary(role()).model_dump(mode='json')

    @router.get('/records')
    async def records(request: Request):
        try:
            limit = int(request.query_params.get('limit', '100'))
            offset = int(request.query_params.get('offset', '0'))
        except ValueError:
            raise HTTPException(status_code=400, detail='分页参数不正确') from None
        if not 1 <= limit <= 1000 or not 0 <= offset <= 2**31:
            raise HTTPException(status_code=400, detail='分页参数不正确')
        return store.records(role(), request.query_params.get('pool_key') or None, limit, offset)

    @router.get('/export')
    async def export():
        return JSONResponse(store.export(role()),
                            headers={'Content-Disposition': 'attachment; filename="endfield-gacha.json"'})

    app.include_router(router)
