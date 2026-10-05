"""Protected local Bilibili login API; only safe public session data is returned."""
from typing import Literal
import re
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from starlette.responses import JSONResponse
from .bilibili_service import BilibiliLoginError

PREFIX = '/api/auth/bilibili-source/login'
LEGACY = '/api/auth/bilibili-source/credentials'

class BilibiliBodyLimitMiddleware:
    def __init__(self, app, max_bytes=16384): self.app, self.max_bytes = app, max_bytes
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not (scope['path'].startswith(PREFIX+'/') or scope['path'] == LEGACY):
            return await self.app(scope, receive, send)
        messages, total = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect': return
            total += len(message.get('body', b''))
            if total > self.max_bytes:
                response = JSONResponse({'detail':'登录请求过大'}, status_code=413,
                    headers={'Cache-Control':'no-store','Pragma':'no-cache','Referrer-Policy':'no-referrer'})
                return await response(scope, receive, send)
            messages.append(message)
            if not message.get('more_body', False): break
        async def replay():
            if messages: return messages.pop(0)
            return await receive()
        return await self.app(scope, replay, send)

class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_default=True)

class StartBody(StrictBody):
    mode: Literal['qr','password','sms','cookie']

class Proof(StrictBody):
    geetest_validate: SecretStr = Field(alias='validate', min_length=1, max_length=4096)
    seccode: SecretStr = Field(min_length=1, max_length=4096)
    def values(self): return {k:v.get_secret_value() for k,v in self.model_dump(by_alias=True).items()}

class PasswordBody(StrictBody):
    username: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=512)
    proof: Proof

class SmsBody(StrictBody):
    mobile: str = Field(pattern=r'^1[3-9][0-9]{9}$')
    proof: Proof

class CodeBody(StrictBody):
    code: SecretStr = Field(min_length=4, max_length=8)
    @field_validator('code')
    @classmethod
    def ascii_digits(cls, value):
        if not re.fullmatch(r'[0-9]{4,8}', value.get_secret_value()): raise ValueError('Invalid input')
        return value

class CookieBody(StrictBody):
    sessdata: SecretStr = Field(min_length=1, max_length=4096)
    bili_jct: SecretStr = Field(default='', max_length=128)
    buvid3: SecretStr = Field(default='', max_length=256)
    def values(self): return {k:v.get_secret_value() for k,v in self.model_dump().items()}

def install_bilibili_auth_routes(app, service):
    app.add_middleware(BilibiliBodyLimitMiddleware)
    @app.exception_handler(BilibiliLoginError)
    async def login_error(request, error):
        body = {'detail':error.detail,'error_code':error.error_code}
        if error.state: body['state'] = error.state
        if error.retry_after: body['retry_after'] = error.retry_after
        return JSONResponse(body, status_code=error.status,
            headers={'Retry-After':str(error.retry_after)} if error.retry_after else None)
    router = APIRouter(prefix=PREFIX)
    @router.get('/status')
    async def status(): return service.status()
    @router.post('/sessions')
    async def start(body: StartBody, request: Request):
        return await service.start(body.mode, is_disconnected=request.is_disconnected)
    @router.get('/sessions/{sid}')
    async def session(sid: str): return service.session_status(sid)
    @router.delete('/sessions/{sid}')
    async def cancel(sid: str): return await service.cancel(sid)
    @router.post('/sessions/{sid}/captcha')
    async def captcha(sid: str, request: Request):
        return await service.captcha(sid, is_disconnected=request.is_disconnected)
    @router.post('/sessions/{sid}/password')
    async def password(sid: str, body: PasswordBody, request: Request):
        return await service.password(sid, body.username, body.password.get_secret_value(), body.proof.values(), is_disconnected=request.is_disconnected)
    @router.post('/sessions/{sid}/sms/send')
    async def sms(sid: str, body: SmsBody, request: Request):
        return await service.sms_send(sid, body.mobile, body.proof.values(), is_disconnected=request.is_disconnected)
    @router.post('/sessions/{sid}/sms/submit')
    async def submit(sid: str, body: CodeBody, request: Request):
        return await service.sms_submit(sid, body.code.get_secret_value(), is_disconnected=request.is_disconnected)
    @router.post('/sessions/{sid}/qr/poll')
    async def poll(sid: str, request: Request):
        return await service.qr_poll(sid, is_disconnected=request.is_disconnected)
    @router.post('/sessions/{sid}/cookie')
    async def cookie(sid: str, body: CookieBody, request: Request):
        return await service.cookie(sid, body.values(), is_disconnected=request.is_disconnected)
    @router.post('/sessions/{sid}/commit')
    async def commit(sid: str, request: Request):
        return await service.commit(sid, is_disconnected=request.is_disconnected)
    app.include_router(router)
