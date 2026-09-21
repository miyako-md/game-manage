import httpx

from game_assistant.adapters.wuthering_waves.endpoints import (
    EVENT_LIST, POST_DETAIL, ROLE_LIST, WIDGET_DATA, WIDGET_REFRESH,
)


class KuroError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"库街区接口错误 code={code}: {message}")


class KuroClient:
    def __init__(self, token: str, did: str = '', source: str = 'h5'):
        self.token = token
        self.did = did
        self.source = source

    def _headers(self) -> dict:
        return {
            "token": self.token,
            "devCode": self.did or "9asdpjhjklgfhjko90876532134",  # legacy config fallback
            "version": "3.0.0",
            "countryCode": "CN",
            "source": self.source,
        }

    async def _post(self, url: str, body: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # 库街区 APP 端为 form-urlencoded（来源：Kuro-API-Collection/waves-plugin），
                # 若上游改回 JSON 在此切换
                resp = await client.post(url, headers=self._headers(), data=body)
        except httpx.HTTPError as e:
            raise KuroError(-1, f"网络错误: {e}") from e
        if resp.status_code != 200:
            raise KuroError(resp.status_code, f"HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as e:
            raise KuroError(-2, "响应非 JSON") from e
        if not isinstance(data, dict):
            # 归一化 200 但顶层非 dict（如网关返回数组/字符串）的情况
            raise KuroError(-2, "响应结构异常")
        if data.get("code") != 200:
            raise KuroError(data.get("code", -2), data.get("msg", "未知错误"))
        return data

    async def role_list(self) -> dict:
        # /gamer/role/list：token 即身份，无需 userId；data 为数组（首元素默认角色）
        return await self._post(ROLE_LIST, {"gameId": 3})

    async def widget_data(self, role_id: str, server_id: str,
                          refresh: bool = False) -> dict:
        # /gamer/widget/game3/getData：体力等组件数据（baseData 需 APP 端 token，不可用）
        # refresh=True 改走同族 refresh 端点（参数相同，实测数据更新鲜，体力用，
        # 见 endpoints.py ⑧）；默认 False 保持兼容
        return await self._post(WIDGET_REFRESH if refresh else WIDGET_DATA,
                                {"gameId": 3, "roleId": role_id,
                                 "serverId": server_id, "type": 2,
                                 "sizeType": 1})

    async def find_event_list(self, event_type: int) -> dict:
        # findEventList：eventType 1=活动 2=资讯 3=公告（公告不走 forum/list 社区板块）
        return await self._post(EVENT_LIST, {"gameId": 3, "eventType": event_type})

    async def get_post_detail(self, post_id: str) -> dict:
        # /forum/getPostDetail：帖子详情（2026-09-13 实测仅需 postId，网页 token 头
        # 即可）；返回 data.postDetail（dict，postH5Content=H5 HTML 全文/postTitle=标题）
        raw = await self._post(POST_DETAIL, {"postId": post_id})
        detail = (raw.get("data") or {}).get("postDetail")
        if not isinstance(detail, dict):
            raise KuroError(-3, "帖子详情响应结构异常")
        return detail
