import httpx

from game_assistant.adapters.wuthering_waves.endpoints import (
    ACTIVITY_LIST, ANNOUNCEMENT_LIST, ROLE_DATA,
)


class KuroError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"库街区接口错误 code={code}: {message}")


class KuroClient:
    def __init__(self, token: str, user_id: str):
        self.token = token
        self.user_id = user_id

    def _headers(self) -> dict:
        return {
            "token": self.token,
            "devCode": "9asdpjhjklgfhjko90876532134",  # 库街区 APP 固定 devCode 样例
            "version": "3.0.0",
            "countryCode": "CN",
            "source": "h5",
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

    async def get_role_data(self) -> dict:
        return await self._post(ROLE_DATA,
                                {"gameId": 3, "userId": self.user_id, "serverId": ""})

    async def get_activity_list(self) -> dict:
        # findEventList：eventType 1=活动（0=全部/2=资讯/3=公告），见 endpoints.py 校准注释
        return await self._post(ACTIVITY_LIST, {"gameId": 3, "eventType": 1})

    async def get_announcement_list(self) -> dict:
        # /forum/list 参数为 pageIndex/pageSize（Step 5 校准）；forumId=1602 未核实
        return await self._post(ANNOUNCEMENT_LIST,
                                {"forumId": 1602, "gameId": 3, "pageIndex": 1,
                                 "pageSize": 20})
