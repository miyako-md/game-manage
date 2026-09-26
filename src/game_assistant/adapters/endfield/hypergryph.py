"""鹰角通行证与寻访记录 HTTP 客户端（端点见 endpoints.py）。

通行证与绑定接口以 status=0 表示成功，寻访记录接口以 code=0 表示成功。
错误信息只保留服务端的简短提示，不包含 URL、token 或响应正文。
"""
import re
from typing import Any

import httpx

from game_assistant.adapters.endfield.endpoints import (
    BINDING_APP_CODE, BINDING_LIST, CHAR_RECORD, GACHA_APP_CODE, OAUTH_GRANT,
    OFFICIAL_SERVER_ID, U8_TOKEN_BY_UID, USER_AGENT, WEAPON_POOLS, WEAPON_RECORD,
)

EXPIRED_MESSAGE = "鹰角通行证登录已失效，请在「社区账号」重新登录终末地"
# 失效码未经实测；除 HTTP 401/403 外，只按服务端提示文字识别登录失效。
_EXPIRED_TEXT = re.compile(r"(?:登录|登陆|token|凭证|授权).{0,8}(?:过期|失效|无效)", re.I)


class EndfieldError(Exception):
    def __init__(self, message: str, status_code: int | None = None, expired: bool = False,
                 hint: str = ""):
        self.message = message
        self.status_code = status_code
        self.expired = expired
        self.hint = hint  # 服务端的简短提示，登录流程直接展示给用户
        super().__init__(message)


def server_message(payload: dict) -> str:
    """服务端提示文字：去掉控制字符并截断，避免把异常响应原样带进界面。"""
    text = payload.get("msg") or payload.get("message")
    if not isinstance(text, str):
        return ""
    return "".join(ch for ch in text.strip() if ch.isprintable())[:60]


def _status(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit() and len(value) <= 12:
        return int(value)
    return None


async def request_data(client: httpx.AsyncClient, method: str, url: str, *, key: str = "status",
                       params: dict | None = None, body: dict | None = None) -> Any:
    try:
        response = await client.request(method, url, params=params, json=body)
    except httpx.HTTPError as error:
        raise EndfieldError(f"网络错误: {type(error).__name__}") from None
    if response.status_code in (401, 403):
        raise EndfieldError(EXPIRED_MESSAGE, status_code=response.status_code, expired=True)
    if response.status_code != 200:
        raise EndfieldError(f"HTTP {response.status_code}", status_code=response.status_code)
    try:
        payload = response.json()
    except ValueError:
        raise EndfieldError("响应非 JSON") from None
    if not isinstance(payload, dict):
        raise EndfieldError("响应结构异常")
    status = _status(payload.get(key))
    if status is None:
        raise EndfieldError("响应结构异常")
    if status != 0:
        hint = server_message(payload)
        expired = bool(_EXPIRED_TEXT.search(hint))
        raise EndfieldError(EXPIRED_MESSAGE if expired else f"接口错误 {key}={status}{'：' + hint if hint else ''}",
                            status_code=status, expired=expired, hint=hint)
    return payload.get("data")


def _required_text(data: Any, field: str) -> str:
    value = data.get(field) if isinstance(data, dict) else None
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or not value.strip():
        raise EndfieldError("响应结构异常")
    return value.strip()


class HypergryphClient:
    """寻访记录链路：授权 → 绑定列表 → u8_token → 记录分页。每次拉取新建，async with 收尾。"""

    def __init__(self, *, trust_env: bool = True):
        self._client = httpx.AsyncClient(timeout=15, trust_env=trust_env,
                                         headers={"User-Agent": USER_AGENT})

    async def grant(self, token: str) -> str:
        data = await request_data(self._client, "POST", OAUTH_GRANT,
                                  body={"token": token, "appCode": GACHA_APP_CODE, "type": 1})
        return _required_text(data, "token")

    async def binding_list(self, grant_token: str) -> Any:
        return await request_data(self._client, "GET", BINDING_LIST,
                                  params={"token": grant_token, "appCode": BINDING_APP_CODE})

    async def u8_token(self, uid: str, grant_token: str) -> str:
        data = await request_data(self._client, "POST", U8_TOKEN_BY_UID,
                                  body={"uid": uid, "token": grant_token})
        return _required_text(data, "token")

    async def char_records(self, u8_token: str, pool_type: str, seq_id: str | None = None) -> Any:
        params = {"token": u8_token, "server_id": OFFICIAL_SERVER_ID, "pool_type": pool_type, "lang": "zh-cn"}
        if seq_id:
            params["seq_id"] = seq_id
        return await request_data(self._client, "GET", CHAR_RECORD, key="code", params=params)

    async def weapon_pools(self, u8_token: str) -> Any:
        return await request_data(self._client, "GET", WEAPON_POOLS, key="code",
                                  params={"token": u8_token, "server_id": OFFICIAL_SERVER_ID, "lang": "zh-cn"})

    async def weapon_records(self, u8_token: str, pool_id: str, seq_id: str | None = None) -> Any:
        params = {"token": u8_token, "server_id": OFFICIAL_SERVER_ID, "pool_id": pool_id, "lang": "zh-cn"}
        if seq_id:
            params["seq_id"] = seq_id
        return await request_data(self._client, "GET", WEAPON_RECORD, key="code", params=params)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "HypergryphClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()
