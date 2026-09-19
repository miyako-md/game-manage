"""Account-scoped archives; gacha network access is explicit POST import only."""
import json
from typing import Literal

from fastapi import HTTPException, Query, Request

from game_assistant.wuwa_gacha import GachaStore, fetch_official

MAX_BODY = 2 * 1024 * 1024
GAME = 'wuthering_waves'


def install_wuwa_archive_routes(app):
    store = app.state.store
    gacha = GachaStore(store._conn, store._lock)

    @app.middleware('http')
    async def private_headers(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/wuwa/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    def current():
        try:
            adapter = app.state.registry.get(GAME)
        except KeyError:
            raise HTTPException(404, '鸣潮未启用') from None
        settings = getattr(adapter, '_settings', None)
        account = getattr(settings, 'wuwa_role_id', None)
        server = getattr(settings, 'wuwa_server_id', None)
        if not adapter.credentials_configured or not account or not server:
            raise HTTPException(401, '请先登录有角色与区服信息的鸣潮账号')
        return str(account), str(server), app.state.auth.account_generation(GAME)

    async def body(request):
        try:
            length = int(request.headers.get('content-length', '0'))
        except ValueError:
            raise HTTPException(413, '请求大小无效') from None
        if length < 0 or length > MAX_BODY:
            raise HTTPException(413, '请求过大，单次最多 2 MiB')
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BODY:
                raise HTTPException(413, '请求过大，单次最多 2 MiB')
        try:
            value = json.loads(raw or b'{}')
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (ValueError, UnicodeError):
            raise HTTPException(422, '请提供有效的 JSON 对象') from None

    @app.get('/api/wuwa/history')
    async def history(kind: Literal['tower', 'roles', 'role_detail'],
                      limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0, le=1000000)):
        account, server, _ = current()
        return store.wuwa_history.read(account, server, kind, limit, offset)

    @app.get('/api/wuwa/gacha')
    async def gacha_read(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0, le=1000000)):
        account, server, _ = current()
        return gacha.read(account, server, limit, offset)

    @app.post('/api/wuwa/history/backfill')
    async def backfill(request: Request):
        await body(request)
        account, server, _ = current()
        return store.wuwa_history.backfill(store, account, server)

    @app.post('/api/wuwa/gacha/import')
    async def gacha_import(request: Request):
        value = await body(request)
        identity = current()
        account, server, _ = identity
        if set(value) not in ({'url'}, {'records'}):
            raise HTTPException(422, '请仅提供 url 或 records 其中一种导入方式')
        failed, source = [], 'json_import'
        try:
            if 'url' in value:
                if not isinstance(value['url'], str):
                    raise ValueError('抽卡链接须为字符串')
                result = await fetch_official(value['url'], account, server)
                try:
                    unchanged = current() == identity
                except HTTPException:
                    unchanged = False
                if not unchanged:
                    raise HTTPException(409, '账号会话已变化，请重新导入')
                records, failed, source = result['records'], result['failed_pools'], 'official_query'
            else:
                records = value['records']
            return gacha.import_records(records, account, server, source=source, failed_pools=failed)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
