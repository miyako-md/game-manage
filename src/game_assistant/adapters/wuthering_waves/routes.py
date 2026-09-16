"""Bounded private detail reads, sharing LoginService renewal and isolation."""
from datetime import datetime, timezone
from typing import Literal, Annotated

from fastapi import HTTPException, Path
from fastapi.encoders import jsonable_encoder

from game_assistant.models import Capability


def install_wuwa_routes(app):
    async def read(capability, method, *args):
        game = 'wuthering_waves'
        try:
            adapter = app.state.registry.get(game)
        except KeyError:
            raise HTTPException(404, '鸣潮未启用') from None
        if not adapter.credentials_configured:
            raise HTTPException(401, '请先登录鸣潮账号')
        auth = app.state.auth
        generation = auth.account_generation(game)
        settings = getattr(adapter, '_settings', None)
        def identity():
            return tuple(getattr(settings, field, None) for field in
                         ('wuwa_user_id', 'wuwa_role_id', 'wuwa_server_id'))
        original_identity = identity()
        result = await auth.fetch(game, capability, lambda: getattr(adapter, method)(*args))
        if (generation != auth.account_generation(game) or original_identity != identity()
                or result.credential_version != auth.version(game) or not adapter.credentials_configured):
            raise HTTPException(409, '账号会话已变化，请重新读取')
        if not result.ok:
            status = {'not_found': 404, 'unconfigured': 401, 'auth_expired': 401,
                      'account_changed': 409}.get(result.error_kind, 502)
            raise HTTPException(status, result.error or '读取失败')
        return {'payload': jsonable_encoder(result.payload),
                'fetched_at': datetime.now(timezone.utc).isoformat()}

    @app.get('/api/wuwa/roles/{role_id}')
    async def role_detail(role_id: Annotated[str, Path(pattern=r'^\d{1,12}$')]):
        return await read(Capability.ROLES, 'fetch_role_detail', role_id)

    @app.get('/api/wuwa/resources/{kind}/{period}')
    async def resource_detail(kind: Literal['week', 'month', 'version'],
                              period: Annotated[str, Path(pattern=r'^[A-Za-z0-9_.-]{1,64}$')]):
        return await read(Capability.RESOURCES, 'fetch_resource_detail', kind, period)
