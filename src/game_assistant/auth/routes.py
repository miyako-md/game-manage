from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from .service import LoginError


class SmsRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    mobile: str = Field(min_length=11, max_length=11)
    captcha: dict | None = None


class LoginRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    mobile: str = Field(min_length=11, max_length=11)
    code: str = Field(min_length=4, max_length=8)


def install_auth_routes(app, service, settings):
    router = APIRouter(prefix='/api/auth')
    origins = {origin.rstrip('/') for origin in settings.auth_allowed_origins}
    hosts = {urlsplit(origin).hostname for origin in origins}

    @app.middleware('http')
    async def protect_login(request: Request, call_next):
        if request.url.path.startswith('/api/auth/'):
            origin = request.headers.get('origin')
            allowed = request.url.hostname in hosts and (not origin or origin in origins)
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                allowed = allowed and request.headers.get('x-game-assistant') == '1'
            try:
                length = int(request.headers.get('content-length', '0') or 0)
            except ValueError:
                length = 16385
            if not allowed:
                response = JSONResponse({'detail': '请从本机游戏助手页面操作登录'}, status_code=403)
            elif length > 16384 or length < 0:
                response = JSONResponse({'detail': '登录请求过大'}, status_code=413)
            else:
                response = await call_next(request)
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Referrer-Policy'] = 'no-referrer'
            return response
        return await call_next(request)

    @app.exception_handler(LoginError)
    async def login_error(request, error):
        headers = {'Retry-After': '60'} if error.status == 429 else None
        return JSONResponse({'detail': error.message}, status_code=error.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        if request.url.path.startswith('/api/auth/'):
            return JSONResponse({'detail': '登录参数不正确，请检查手机号和验证码'}, status_code=422)
        return await request_validation_exception_handler(request, error)

    @router.get('/status')
    async def status():
        return service.status()

    @router.post('/{game}/sessions')
    async def start(game: str):
        return await service.start(game)

    @router.post('/{game}/sms')
    async def sms(game: str, body: SmsRequest):
        return await service.sms(game, body.session_id, body.mobile, body.captcha)

    @router.post('/{game}/login')
    async def login(game: str, body: LoginRequest):
        return await service.login(game, body.session_id, body.mobile, body.code)

    @router.delete('/{game}')
    async def logout(game: str):
        return await service.logout(game)

    app.include_router(router)
