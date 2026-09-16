"""库街区 roleBox 客户端（b-at 会话票据鉴权）。

头三件套（b-at/devCode/did）与 UA 逐字复刻自 APP WebView 请求（2026-09-13 实测）。
b-at由页面登录后的requestToken换取；过期由登录服务尝试续期，失败后提示重新登录。

与 kuro_client.py 的 token 鉴权完全不同：roleBox 系列请求不带 token 头，
鉴权全靠 b-at 头（32 位十六进制会话票据，来自库街区 APP 内 WebView 会话）。
必需头（实测）：Content-Type: application/x-www-form-urlencoded、
devCode（"客户端公网IP, 空格+完整UA" 整串）、source: ios、
Origin: https://web-static.kurobbs.com、did（设备 UUID）、
User-Agent（与 devCode 内 UA 一致，KuroGameBox 前是两个空格，逐字保留）、b-at。

响应 data 是 JSON 字符串，需二次解析（post 内完成，见 rolebox.py 防御式兜底）。
"""
import json

import httpx

from game_assistant.adapters.wuthering_waves.endpoints import (
    ROLEBOX_BASE_DATA, ROLEBOX_CALABASH_DATA, ROLEBOX_EXPLORE_INDEX,
    ROLEBOX_ROLE_DATA, ROLEBOX_REFRESH_DATA, ROLEBOX_TOWER_DETAIL,
    ROLEBOX_ROLE_DETAIL, ROLEBOX_CHALLENGE_DETAILS, ROLEBOX_SLASH_DETAIL,
    ROLEBOX_MORE_ACTIVITY, RESOURCE_BASE,
)

# 与 devCode 内 UA 逐字一致（注意 KuroGameBox 前是两个空格，保留）
USER_AGENT = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
              "AppleWebKit/605.1.15 (KHTML, like Gecko)  KuroGameBox/3.3.1")

# msg 含这两类字样 = b-at 过期/无效或角色不可见（实测 10901/10900 形状）
_INVALID_TICKET_MARKS = ("禁止访问", "角色查询失败")


class RoleBoxError(Exception):
    def __init__(self, message: str, code: int | None = None):
        self.message = message
        self.code = code
        super().__init__(message)


class RoleBoxClient:
    def __init__(self, b_at: str, dev_code: str, did: str, *, token: str = ''):
        self.token = token
        self.b_at = b_at
        self.dev_code = dev_code
        self.did = did
        self._client = httpx.AsyncClient(
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "devCode": self.dev_code,
                "source": "ios",
                "Origin": "https://web-static.kurobbs.com",
                "did": self.did,
                "User-Agent": USER_AGENT,
                "b-at": self.b_at,
            },
            timeout=15,
        )

    async def post(self, path: str, body: dict, *, refresh_ack: bool = False,
                   method: str = 'POST', resource: bool = False) -> dict | bool:
        """POST form 请求 → 内层 data dict（data 字符串已二次解析）。"""
        try:
            headers = {'token': self.token} if resource else {}
            resp = await self._client.request(method, path, data=body if method == 'POST' else None, headers=headers)
        except httpx.HTTPError as e:
            # Exception messages may contain request URLs or credential values.
            raise RoleBoxError(f"网络错误: {type(e).__name__}") from e
        if resp.status_code != 200:
            raise RoleBoxError(f"HTTP {resp.status_code}", resp.status_code)
        try:
            data = resp.json()
        except ValueError as e:
            raise RoleBoxError("响应非 JSON") from e
        if not isinstance(data, dict):
            raise RoleBoxError("响应结构异常")
        if data.get("code") != 200:
            msg = str(data.get("msg", "未知错误"))
            if any(mark in msg for mark in _INVALID_TICKET_MARKS):
                raise RoleBoxError("b-at 已失效或角色不可见，请在账号管理重新登录", data.get('code'))
            if data.get('code') == 10903:
                raise RoleBoxError('数据令牌已失效，请在账号管理重新登录', 10903)
            raise RoleBoxError(msg, data.get('code'))
        payload = data.get("data")
        if refresh_ack:
            if payload is not True:
                raise RoleBoxError('角色数据刷新未成功，请稍后重试')
            return True
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError as e:
                raise RoleBoxError("响应结构异常") from e
        if not isinstance(payload, dict):
            raise RoleBoxError("响应结构异常")
        return payload

    async def base_data(self, role_id: str, server_id: str) -> dict:
        # baseData is cached; call refresh_data first when collecting live state.
        return await self.post(ROLEBOX_BASE_DATA,
                               {"gameId": 3, "roleId": role_id,
                                "serverId": server_id})

    async def refresh_data(self, role_id: str, server_id: str) -> None:
        await self.post(ROLEBOX_REFRESH_DATA,
                        {"gameId": 3, "roleId": role_id, "serverId": server_id}, refresh_ack=True)

    async def tower_detail(self, role_id: str, server_id: str) -> dict:
        return await self.post(ROLEBOX_TOWER_DETAIL,
                               {"gameId": 3, "roleId": role_id, "serverId": server_id})

    async def explore_index(self, role_id: str, server_id: str) -> dict:
        # exploreIndex：探索度/残象探寻（channelId=19&countryCode=1 实测必需）
        return await self.post(ROLEBOX_EXPLORE_INDEX,
                               {"gameId": 3, "roleId": role_id,
                                "serverId": server_id,
                                "channelId": 19, "countryCode": 1})

    async def calabash_data(self, role_id: str, server_id: str) -> dict:
        # calabashData：数据坞（等级/基础捕获率/捕获品质/声骸收集）
        return await self.post(ROLEBOX_CALABASH_DATA,
                               {"gameId": 3, "roleId": role_id,
                                "serverId": server_id})

    async def role_data(self, role_id: str, server_id: str) -> dict:
        # roleData：角色练度墙（data.roleList 46 项，等级/命链/突破/属性/武器等；
        # body 与 baseData 完全一致）
        return await self.post(ROLEBOX_ROLE_DATA,
                               {"gameId": 3, "roleId": role_id,
                                "serverId": server_id})

    async def aclose(self) -> None:
        await self._client.aclose()

    async def role_detail(self, role_id, server_id, character_id):
        return await self.post(ROLEBOX_ROLE_DETAIL, {'gameId': 3, 'roleId': role_id,
            'serverId': server_id, 'id': character_id, 'channelId': 19, 'countryCode': 1})

    async def challenge_details(self, role_id, server_id):
        return await self.post(ROLEBOX_CHALLENGE_DETAILS, {'gameId': 3, 'roleId': role_id, 'serverId': server_id})

    async def slash_detail(self, role_id, server_id):
        return await self.post(ROLEBOX_SLASH_DETAIL, {'gameId': 3, 'roleId': role_id, 'serverId': server_id})

    async def more_activity(self, role_id, server_id):
        return await self.post(ROLEBOX_MORE_ACTIVITY, {'gameId': 3, 'roleId': role_id, 'serverId': server_id})

    async def period_list(self):
        return await self.post(RESOURCE_BASE + '/period/list', {}, method='GET', resource=True)

    async def resource_report(self, role_id, server_id, kind, period):
        if kind not in ('week', 'month', 'version'):
            raise ValueError('无效资源类型')
        return await self.post(RESOURCE_BASE + '/' + kind,
            {'roleId': role_id, 'serverId': server_id, 'period': period}, resource=True)

    async def __aenter__(self) -> "RoleBoxClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()
