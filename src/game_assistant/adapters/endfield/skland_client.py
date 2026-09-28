"""森空岛国服私人接口。路径与签名据 EndUID / nonebot-plugin-skland 原码核对。"""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx

HOST = "https://zonai.skland.com"
REFRESH = "/api/v1/auth/refresh"
BINDING = "/api/v1/game/player/binding"
USER = "/api/v1/user"
CARD = "/api/v1/game/endfield/card/detail"
OPERATOR = "/api/v1/game/endfield/card/char"
ATTENDANCE = "/web/v1/game/endfield/attendance"
ATTENDANCE_RECORD = "/web/v1/game/endfield/attendance/record"
CHALLENGES = {
    "war": ("/api/v1/game/endfield/card/war-echoes", "warEchoes"),
    "monument": ("/api/v1/game/endfield/card/indie-hard", "indieHard"),
    "crisis": ("/api/v1/game/endfield/card/crisis-contract", "crisisContract"),
}
CRISIS_RECORD = "/api/v1/game/endfield/card/crisis-contract/record"
TOOLS = {
    "characters": "/web/v1/game/endfield/search-chars",
    "weapons": "/web/v1/game/endfield/search-weapons",
    "equipment": "/web/v1/game/endfield/search-equipments",
    "tactical": "/web/v1/game/endfield/search-tactical-items",
    "materials": "/web/v1/game/endfield/calculate/material-list",
}


class SklandError(Exception):
    """Public error message deliberately contains no response data or secrets."""

    def __init__(self, message: str, *, expired: bool = False):
        super().__init__(message)
        self.expired = expired


def sign_request(token: str, path: str, query_or_body: str = "", *, timestamp: int | None = None,
                 device_id: str = "") -> tuple[str, dict[str, str]]:
    """HMAC-SHA256 hex then MD5; header JSON order matches Skland's client."""
    ts = str(int(time.time()) if timestamp is None else timestamp)
    fields = {"platform": "3", "timestamp": ts, "dId": device_id, "vName": "1.0.0"}
    data = path + query_or_body + ts + json.dumps(fields, separators=(",", ":"), ensure_ascii=False)
    sha = hmac.new(token.encode(), data.encode(), hashlib.sha256).hexdigest()
    return hashlib.md5(sha.encode()).hexdigest(), fields


class SklandClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    async def _request(self, method: str, path: str, cred: str, token: str | None = None,
                       *, params: dict[str, str] | None = None, device_id: str = "",
                       role: tuple[str, str] | None = None):
        if path not in {REFRESH, BINDING, USER, CARD, OPERATOR, ATTENDANCE, ATTENDANCE_RECORD, CRISIS_RECORD,
                        *TOOLS.values(),
                        *(item[0] for item in CHALLENGES.values())}:
            raise SklandError("接口不受支持")
        query = urlencode(params or {})
        url = HOST + path + ("?" + query if query else "")
        headers = {"cred": cred, "Accept": "application/json", "User-Agent": "GameAssistant/0.1"}
        if token is not None:
            signature, fields = sign_request(token, path, query, device_id=device_id)
            headers.update(fields)
            headers["sign"] = signature
        if role:
            headers["sk-game-role"] = f"3_{role[0]}_{role[1]}"
        if path.startswith("/api/v1/game/endfield/card/"):
            headers.update({"Origin": "https://game.skland.com", "Referer": "https://game.skland.com/"})
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=12, follow_redirects=False) as client:
                response = await client.request(method, url, headers=headers)
            if response.status_code in (401, 403):
                raise SklandError("森空岛登录已失效，请重新连接", expired=True)
            if response.status_code != 200:
                raise SklandError("森空岛暂时无法提供数据")
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("bad envelope")
            code = result.get("code", result.get("status"))
            if code != 0:
                if code in (220, 10002):
                    raise SklandError("森空岛登录已失效，请重新连接", expired=True)
                # 10001 is ambiguous (device info, invalid cred or signed already).
                if code == 10001:
                    raise SklandError("森空岛拒绝请求；请检查登录状态或原生设备标识")
                raise SklandError("森空岛暂时无法提供数据")
            data = result.get("data")
            if not isinstance(data, dict):
                raise ValueError("bad data")
            return data
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise SklandError("森空岛响应异常，请稍后重试") from None

    async def refresh(self, cred: str) -> str:
        data = await self._request("GET", REFRESH, cred)
        token = data.get("token")
        if not isinstance(token, str) or not token:
            raise SklandError("森空岛未返回有效签名令牌")
        return token

    async def binding(self, cred: str, token: str, device_id: str = "") -> dict:
        return await self._request("GET", BINDING, cred, token, device_id=device_id)

    async def user(self, cred: str, token: str, device_id: str = "") -> dict:
        return await self._request("GET", USER, cred, token, device_id=device_id)

    async def card(self, cred: str, token: str, role_id: str, server_id: str,
                   user_id: str, device_id: str = "") -> dict:
        data = await self._request("GET", CARD, cred, token,
            params={"roleId": role_id, "serverId": server_id, "userId": user_id}, device_id=device_id)
        detail = data.get("detail")
        if not isinstance(detail, dict):
            raise SklandError("森空岛角色卡格式已变化")
        return detail

    async def attendance(self, cred: str, token: str, role_id: str, server_id: str,
                         device_id: str = "") -> dict:
        # Confirmed CN endpoint: empty POST and sk-game-role header.
        return await self._request("POST", ATTENDANCE, cred, token, role=(role_id, server_id), device_id=device_id)

    async def operator(self, cred: str, token: str, role_id: str, server_id: str,
                       user_id: str, char_id: str, device_id: str = "") -> dict:
        data = await self._request('GET', OPERATOR, cred, token,
            params={'roleId': role_id, 'serverId': server_id, 'userId': user_id, 'charId': char_id},
            device_id=device_id)
        detail = data.get('detail')
        if not isinstance(detail, dict):
            raise SklandError('森空岛暂未开放这个干员的配装详情')
        return detail

    async def attendance_calendar(self, cred: str, token: str, role_id: str, server_id: str,
                                  device_id: str = "") -> dict:
        return await self._request("GET", ATTENDANCE, cred, token, role=(role_id, server_id), device_id=device_id)

    async def attendance_records(self, cred: str, token: str, role_id: str, server_id: str,
                                 device_id: str = "") -> dict:
        return await self._request("GET", ATTENDANCE_RECORD, cred, token,
                                   role=(role_id, server_id), device_id=device_id)

    async def challenge(self, kind: str, cred: str, token: str, role_id: str,
                        server_id: str, user_id: str, device_id: str = "",
                        *, season_id: str | None = None, contract_id: str | None = None,
                        record_id: str | None = None) -> dict:
        if kind not in CHALLENGES:
            raise SklandError("挑战类型不受支持")
        path, key = CHALLENGES[kind]
        params = {"roleId": role_id, "serverId": server_id, "userId": user_id}
        if kind == "war" and season_id:
            params["seasonId"] = season_id
        if kind == "crisis" and contract_id:
            params["contractId"] = contract_id
        if kind == "crisis" and record_id:
            if not contract_id:
                raise SklandError("查看记录需指定合约期次")
            path, key = CRISIS_RECORD, "recordDetail"
            params["recordId"] = record_id
        data = await self._request("GET", path, cred, token, params=params, device_id=device_id)
        payload = data.get(key)
        if not isinstance(payload, dict):
            raise SklandError("森空岛挑战记录格式已变化")
        return payload

    async def tool(self, kind: str, cred: str, token: str, role_id: str, server_id: str,
                   device_id: str = "", *, char_id: str | None = None) -> dict:
        path = TOOLS.get(kind)
        if path is None:
            raise SklandError("工具类型不受支持")
        return await self._request("GET", path, cred, token, device_id=device_id)
