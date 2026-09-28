"""Local-only routes for Endfield CN Skland private data."""
import json

from fastapi import APIRouter, HTTPException, Request

from game_assistant.adapters.endfield.skland_client import SklandError
from game_assistant.endfield_skland import EndfieldSklandService


def _http_error(exc: SklandError):
    message = str(exc)
    status = 401 if exc.expired else 409 if message.startswith("请先") else 400
    if message.startswith("森空岛暂时") or message.startswith("森空岛响应"):
        status = 502
    return HTTPException(status_code=status, detail=message)


async def _json_object(request: Request) -> dict:
    if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > 16384:
        raise HTTPException(413, "请求内容过大")
    body = bytearray()
    try:
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 16384:
                raise HTTPException(413, "请求内容过大")
        value = json.loads(body)
    except (ValueError, UnicodeError):
        raise HTTPException(400, "请求内容格式不正确") from None
    if not isinstance(value, dict):
        raise HTTPException(400, "请求内容格式不正确")
    return value


def install_endfield_skland_routes(app, settings):
    service = EndfieldSklandService(settings.db_path)
    app.state.endfield_skland = service
    router = APIRouter(prefix="/api/endfield/skland")

    @router.get("/status")
    def status():
        return service.status()

    @router.post("/connect")
    async def connect(request: Request):
        body = await _json_object(request)
        try:
            return await service.connect(body.get("cred"), body.get("device_id", ""))
        except SklandError as exc:
            raise _http_error(exc) from None

    @router.post("/role")
    async def role(request: Request):
        body = await _json_object(request)
        try:
            return await service.select_role(body.get("role_id"), body.get("server_id"))
        except SklandError as exc:
            raise _http_error(exc) from None

    @router.delete("/connection")
    async def connection():
        return await service.disconnect()

    @router.get("/card")
    async def card():
        try:
            return await service.read_card()
        except SklandError as exc:
            raise _http_error(exc) from None

    @router.post("/refresh")
    async def refresh():
        try:
            return await service.read_card(force=True)
        except SklandError as exc:
            raise _http_error(exc) from None

    @router.get("/attendance")
    async def attendance():
        try:
            return await service.attendance_status()
        except SklandError as exc:
            raise _http_error(exc) from None

    @router.get('/operators/{char_id}')
    async def operator_detail(char_id: str):
        try:
            return await service.read_operator(char_id)
        except SklandError as exc:
            raise _http_error(exc) from None

    @router.post("/attendance")
    async def sign():
        try:
            return await service.sign_attendance()
        except SklandError as exc:
            raise _http_error(exc) from None

    @router.get("/challenges")
    async def challenges(kind: str, season_id: str | None = None,
                         contract_id: str | None = None, record_id: str | None = None):
        try:
            return await service.read_challenges(kind, season_id=season_id,
                                                 contract_id=contract_id, record_id=record_id)
        except SklandError as exc:
            raise _http_error(exc) from None

    @router.get("/tools")
    async def tools(kind: str, char_id: str | None = None):
        try:
            return await service.read_tool(kind, char_id=char_id)
        except SklandError as exc:
            raise _http_error(exc) from None

    app.include_router(router)
