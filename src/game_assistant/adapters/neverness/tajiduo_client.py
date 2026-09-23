"""塔吉多社区（bbs-api.tajiduo.com）HTTP 客户端。

API 事实来源：参考项目 github.com/tyql688/NTEUID 公开源码（逐字引用，
见 endpoints.py 文件头注释）。2026-09-14 已完成实际登录态的数据查询校准。

两个客户端（参考 LoLNewsClient 生命周期模式：实例持有 AsyncClient，
aclose / async with 收尾；适配器每次拉取新建）：
- TajiduoWebClient：匿名 Web 客户端，官方公告专用（UA Mozilla/5.0，
  无 DS 签名、无 authorization）；
- TajiduoClient：鉴权客户端（APP 形态头 + DS 签名），401/402/403 统一
  报"会话已失效"。
"""
import hashlib
import secrets
import string
import time
import uuid

import httpx

from game_assistant.adapters.neverness.endpoints import (
    APP_VERSION, GACHA, GAME_ID, GET_ALL_COMMUNITY, GET_GAME_RECORD_CARD,
    GET_GAME_ROLES, GET_POST_FULL, GET_USER_FULL_INFO, ACHIEVE_PROGRESS,
    AREA_PROGRESS, CHARACTERS, OFFICIAL_POST_LIST, REALESTATE,
    ROLE_HOME, VEHICLES, TEAMS,
)

# HTTP 会话失效码（endpoints.py ⑤）
_SESSION_EXPIRED_CODES = (401, 402, 403)

# 匿名 Web 客户端头（官方公告，endpoints.py ⑥）
_WEB_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
}

_NONCE_CHARS = string.ascii_letters + string.digits


class TajiduoError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def ds_sign(ts: int, nonce: str, appversion: str = APP_VERSION) -> str:
    """DS 签名：md5(时间戳 + nonce + appversion + 盐)（endpoints.py ②，纯函数可单测）。"""
    salt = "pUds3dfMkl"
    raw = f"{ts}{nonce}{appversion}{salt}".encode()
    return hashlib.md5(raw).hexdigest()


def make_ds_header(appversion: str = APP_VERSION) -> str:
    """按当前时间与随机 nonce 生成 ds 头值："{ts},{nonce},{md5hex}"。"""
    ts = int(time.time())
    nonce = "".join(secrets.choice(_NONCE_CHARS) for _ in range(8))
    return f"{ts},{nonce},{ds_sign(ts, nonce, appversion)}"


async def _request_json(client: httpx.AsyncClient, method: str, url: str, *,
                        params: dict | None = None, headers: dict | None = None,
                        authorized: bool = True) -> dict:
    """统一请求与错误契约：网络错误/HTTP 码/业务 code 检查 → TajiduoError。

    成功码取 code∈(0, 200)（塔吉多为米哈游 BBS 风格接口，code=0 预期为主，
    200 为防御；Phase 2 按真实响应校准）。业务错误码原样进 status_code。
    """
    try:
        resp = await client.request(method, url, params=params, headers=headers)
    except httpx.HTTPError as e:
        raise TajiduoError(f"网络错误: {type(e).__name__}") from e
    if authorized and resp.status_code in _SESSION_EXPIRED_CODES:
        raise TajiduoError("塔吉多会话已失效，请在「社区账号」重新登录异环",
                           status_code=resp.status_code)
    if resp.status_code != 200:
        raise TajiduoError(f"HTTP {resp.status_code}", status_code=resp.status_code)
    try:
        data = resp.json()
    except ValueError as e:
        raise TajiduoError("响应非 JSON") from e
    if not isinstance(data, dict):
        raise TajiduoError("响应结构异常")
    code = data.get("code", data.get("retcode", 0))
    if code not in (0, 200):
        message = data.get("message") or data.get("msg") or "未知错误"
        raise TajiduoError(f"接口错误 code={code}: {message}", status_code=code)
    return data


class TajiduoWebClient:
    """匿名 Web 客户端：官方公告（endpoints.py ⑥），无需任何凭据。"""

    def __init__(self):
        self._client = httpx.AsyncClient(headers=_WEB_HEADERS, timeout=15)

    async def get_all_communities(self) -> dict:
        return await _request_json(self._client, "GET", GET_ALL_COMMUNITY,
                                   authorized=False)

    async def get_teams(self) -> dict:
        return await _request_json(self._client, 'GET', TEAMS, authorized=False)

    async def get_official_post_list(self, column_id: str, count: int = 20) -> dict:
        # 2026-09-13 匿名实测：version/officialType 传空串会被服务端拒绝
        # （code=6 NumberFormatException，officialType 需 int），故仅传
        # columnId + count（officialType=1 亦验证 200，返回相同数据）
        return await _request_json(self._client, "GET", OFFICIAL_POST_LIST,
                                   params={"columnId": column_id, "count": count},
                                   authorized=False)

    async def get_post_full(self, post_id) -> dict:
        # 帖子详情（匿名 GET，2026-09-13 实测 code=0 成功）：返回 data.post
        # （dict，content 为正文 HTML 或明文，活动日历解析版本公告用）
        raw = await _request_json(self._client, "GET", GET_POST_FULL,
                                  params={"postId": post_id}, authorized=False)
        post = (raw.get("data") or {}).get("post")
        if not isinstance(post, dict):
            raise TajiduoError("帖子详情响应结构异常")
        return post

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "TajiduoWebClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()


class TajiduoClient:
    """鉴权客户端（endpoints.py ③④⑦）：APP 形态头 + DS 签名。

    access_token 为空时 authorization 头为空串，由适配器 credentials_configured 门控。
    续期走 NteLoginProvider.renew（endpoints.py ④），客户端不自带续期路径。
    """

    def __init__(self, access_token: str, refresh_token: str,
                 device_id: str | None = None):
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._device_id = device_id or str(uuid.uuid4())
        self._client = httpx.AsyncClient(timeout=15)

    def _headers(self) -> dict:
        return {
            "User-Agent": "okhttp/4.12.0",
            "platform": "android",
            "deviceid": self._device_id,
            "appversion": APP_VERSION,
            "uid": "0",
            "authorization": self._access_token,
            "ds": make_ds_header(),
        }

    async def _request(self, method: str, url: str, *,
                       params: dict | None = None) -> dict:
        return await _request_json(self._client, method, url, params=params,
                                   headers=self._headers(), authorized=True)

    async def get_user_full_info(self) -> dict:
        return await self._request("GET", GET_USER_FULL_INFO)

    async def get_game_roles(self) -> dict:
        return await self._request("GET", GET_GAME_ROLES, params={"gameId": GAME_ID})

    async def get_game_record_card(self, uid: str) -> dict:
        return await self._request("GET", GET_GAME_RECORD_CARD, params={"uid": uid})

    async def get_role_home(self, role_id: str) -> dict:
        return await self._request("GET", ROLE_HOME, params={"roleId": role_id})

    async def get_role_characters(self, role_id: str) -> dict:
        return await self._request("GET", CHARACTERS, params={"roleId": role_id})

    async def get_role_achievement_progress(self, role_id: str) -> dict:
        return await self._request("GET", ACHIEVE_PROGRESS,
                                   params={"roleId": role_id})

    async def get_role_area_progress(self, role_id: str) -> dict:
        return await self._request("GET", AREA_PROGRESS, params={"roleId": role_id})

    async def get_role_realestate(self, role_id: str) -> dict:
        return await self._request("GET", REALESTATE, params={"roleId": role_id})

    async def get_role_vehicles(self, role_id: str) -> dict:
        return await self._request("GET", VEHICLES, params={"roleId": role_id})

    async def get_gacha_summary(self) -> dict:
        # yh/gacha：参考项目调用未见 roleId 参数（endpoints.py ⑦），保持逐字
        return await self._request("GET", GACHA)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "TajiduoClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()
