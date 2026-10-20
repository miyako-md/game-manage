"""Website-only account API. Cloud boundary owns CSRF and route allowlisting."""
from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from game_assistant.auth.routes import SmsRequest, LoginRequest, StartRequest
from game_assistant.auth.service import LoginError
from game_assistant.auth.store import CredentialStoreError
from game_assistant.identity.dependencies import require_user
from .store import AccountNotFoundError


class RoleRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role_id: str = Field(min_length=1,max_length=128)


class SklandRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cred: str = Field(min_length=1,max_length=4096)
    device_id: str = Field(default='',max_length=512)


class SklandPassportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account_id: str = Field(min_length=1,max_length=128)
    role_id: str = Field(min_length=1,max_length=128)


def install_account_routes(app, service, login=None, *, query=None):
    """Return routes so the cloud entrypoint can explicitly allowlist each one."""
    login = login or service.login
    router = APIRouter(prefix='/api/accounts')
    previous_validation = app.exception_handlers.get(RequestValidationError,request_validation_exception_handler)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request,error):
        if request.url.path.startswith('/api/accounts'):
            return JSONResponse({'error_code':'invalid_input','detail':'授权参数格式不正确'},status_code=422)
        return await previous_validation(request,error)

    @app.exception_handler(AccountNotFoundError)
    async def missing(request,error):
        return JSONResponse({'error_code':'account_not_found','detail':'账号或角色不存在'},status_code=404)

    @app.exception_handler(CredentialStoreError)
    async def credential_error(request,error):
        return JSONResponse({'error_code':'credential_unavailable','detail':'授权凭据不可用'},status_code=503)

    @app.exception_handler(LoginError)
    async def login_error(request,error):
        return JSONResponse({'error_code':error.error_kind or 'login_failed','detail':error.message},
                            status_code=error.status,headers={'Retry-After':'60'} if error.status==429 else None)

    @router.get('')
    async def accounts(principal=Depends(require_user)):
        return {'accounts':query.list_accounts(principal) if query else service.list_accounts(principal)}

    if query is not None:
        from dataclasses import asdict
        from datetime import datetime, timezone

        @router.get('/{account_id}/roles/{role_id}/snapshot/{capability}')
        async def snapshot(account_id:str,role_id:str,capability:str,principal=Depends(require_user)):
            scope=service.require_scope(principal,account_id,role_id)
            result=query.read(scope,capability)
            old=bool(result.fetched_at and (datetime.now(timezone.utc)-datetime.fromisoformat(
                result.fetched_at)).total_seconds()>app.state.settings.cloud_private_poll_seconds*2)
            return {**asdict(result),'account_id':account_id,'role_id':role_id,
                    'game_id':service.describe(scope)['game'],'capability':capability,
                    'stale':bool(result.payload is not None and (old or result.state in ('error','auth_expired','never'))),
                    'poll_status':query.status(scope,capability)}

        @router.post('/{account_id}/roles/{role_id}/refresh/{capability}',status_code=202)
        async def refresh(account_id:str,role_id:str,capability:str,principal=Depends(require_user)):
            scope=service.require_scope(principal,account_id,role_id)
            return asdict(query.request_refresh(scope,capability))

    @router.put('/{account_id}/default-role')
    async def role(account_id: str,body: RoleRequest,principal=Depends(require_user)):
        return service.select_role(principal,account_id,body.role_id)

    @router.delete('/{account_id}/authorization')
    async def revoke(account_id: str,principal=Depends(require_user)):
        return service.revoke(principal,account_id)

    @router.post('/auth/{provider}/sessions')
    async def start(provider: str,body: StartRequest | None = None,principal=Depends(require_user)):
        return await login.start(principal,provider,channel=body.channel if body else 'official')

    @router.post('/auth/{provider}/sms')
    async def sms(provider: str,body: SmsRequest,principal=Depends(require_user)):
        return await login.sms(principal,provider,body.session_id,body.mobile,body.captcha)

    @router.post('/auth/{provider}/login')
    async def finish(provider: str,body: LoginRequest,principal=Depends(require_user)):
        return await login.login(principal,provider,body.session_id,body.mobile,body.code)

    @router.post('/auth/skland/connect')
    async def skland(body: SklandRequest,principal=Depends(require_user)):
        return await login.connect_skland(principal,body.cred,body.device_id)

    @router.post('/auth/skland/passport')
    async def skland_passport(body: SklandPassportRequest,principal=Depends(require_user)):
        return await login.connect_skland_passport(principal,body.account_id,body.role_id)

    app.include_router(router)
    return router
