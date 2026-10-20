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

    def current():
        try:
            adapter = app.state.registry.get(GAME)
        except KeyError:
            raise HTTPException(404, '鸣潮未启用') from None
        settings = adapter._settings
        account = settings.wuwa_role_id
        server = settings.wuwa_server_id
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
        except (ValueError, UnicodeError, RecursionError):
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

    @app.get('/api/wuwa/gacha/export')
    async def gacha_export(limit: int = Query(2000, ge=1, le=20000), offset: int = Query(0, ge=0)):
        account, server, _ = current()
        try:
            return gacha.export(account, server, limit=limit, offset=offset)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @app.post('/api/wuwa/gacha/rules')
    async def gacha_rule(request: Request):
        identity = current()
        value = await body(request)
        if current() != identity:
            raise HTTPException(409, '账号会话已变化，请重试')
        account, server, _ = identity
        try:
            return gacha.set_rule(account, server, value)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @app.post('/api/wuwa/gacha/preview')
    async def gacha_preview(request: Request):
        identity = current()
        value = await body(request)
        if current() != identity:
            raise HTTPException(409, '账号会话已变化，请重新预览')
        account, server, generation = identity
        if set(value) == {'url'}:
            try:
                result=await fetch_official(value['url'], account, server)
                if current() != identity:
                    raise HTTPException(409, '账号会话已变化，请重新预览')
                return gacha.preview(result['records'], account, server, session=generation,
                    source='official_query', failed_pools=result['failed_pools'])
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
        if not {'records'} <= set(value) or set(value) - {'records','source','latest_confirmed','continuity_confirmed'}:
            raise HTTPException(422, '预览参数无效')
        try:
            return gacha.preview(value['records'], account, server, session=generation,
                **{k:v for k,v in value.items() if k != 'records'})
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

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
        if set(value) == {'preview_id'}:
            try:
                return gacha.commit_preview(value['preview_id'], account, server, session=identity[2])
            except (ValueError, TypeError):
                raise HTTPException(409, '预览已过期或账号会话已变化，请重新预览') from None
        raise HTTPException(422, '请先预览，再使用 preview_id 确认导入')
