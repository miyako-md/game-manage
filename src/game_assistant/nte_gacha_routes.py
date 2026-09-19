"""NTE ledger HTTP boundary: local-origin checks and bounded streaming bodies."""
import json
from pathlib import Path

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from .nte_gacha import GachaError, GachaStore

MAX_BODY = 8 * 1024 * 1024


def install_nte_gacha_routes(app, settings):
    store = GachaStore(Path(settings.db_path).with_suffix('.gacha.sqlite3'))
    app.state.nte_gacha = store
    router = APIRouter(prefix='/api/nte/gacha')

    @app.exception_handler(GachaError)
    async def error_handler(request, error):
        return JSONResponse({'detail': str(error)}, status_code=error.status)

    def role():
        identity = str(app.state.settings.nte_role_id or '').strip()
        if not identity:
            raise GachaError('请先登录并选择异环角色', 409)
        return identity

    async def body(request):
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > MAX_BODY:
                raise GachaError('导入请求超过 8 MB', 413)
            content.extend(chunk)
        try:
            value = json.loads(content)
        except (ValueError, UnicodeError, RecursionError):
            raise GachaError('请求必须是有效 JSON 对象') from None
        if not isinstance(value, dict):
            raise GachaError()
        return value

    def options(value):
        result = {}
        for key in ('latest_confirmed', 'continuity_confirmed', 'identity_confirmed'):
            v = value.get(key, False)
            if type(v) is not bool:
                raise GachaError('确认选项必须为布尔值')
            result[key] = v
        return result

    def query(request):
        pool = request.query_params.get('pool_id') or None
        try:
            limit = int(request.query_params.get('limit', '100'))
            offset = int(request.query_params.get('offset', '0'))
        except ValueError:
            raise GachaError('分页参数不正确') from None
        if not 1 <= limit <= 1000 or not 0 <= offset <= 2**31:
            raise GachaError('分页参数不正确')
        return pool, limit, offset

    @router.get('/summary')
    async def summary():
        return store.summary(role())

    @router.get('/records')
    async def records(request: Request):
        return store.records(role(), *query(request))

    @router.get('/export')
    async def export(request: Request):
        values = {}
        for name in ('offset', 'limit'):
            if name in request.query_params:
                try:
                    values[name] = int(request.query_params[name])
                except ValueError:
                    raise GachaError('导出分段参数不正确') from None
        result = store.export(role(), request.query_params.get('pool_id') or None, **values)
        return JSONResponse(result, headers={'Content-Disposition': 'attachment; filename="nte-gacha.json"'})

    @router.post('/preview')
    async def preview(request: Request):
        identity = role()
        value = await body(request)
        return store.preview(identity, value.get('document'), **options(value))

    @router.post('/import')
    async def import_document(request: Request):
        identity = role()
        value = await body(request)
        if identity != role():
            raise GachaError('角色已切换，请重新预览', 409)
        return store.import_document(identity, value.get('document'), preview_id=value.get('preview_id'), **options(value))

    @router.get('/rules')
    async def rules():
        return store.rules(role())

    @router.post('/rules')
    async def set_rule(request: Request):
        identity = role()
        value = await body(request)
        if identity != role():
            raise GachaError('角色已切换，请重新操作', 409)
        return store.set_rule(identity, value)

    app.include_router(router)
