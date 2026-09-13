"""LCU 本机客户端。校准来源：C:\\GPT\\LOLhelper pigeon/lcu.py。

SSL 约束（LOLhelper 原文）：LCU 是 127.0.0.1 本机进程，证书为 Riot 自签且
每次安装不同，业界通行做法就是跳过校验。此上下文只能用于本机 LCU 请求，
任何公网请求一律走系统默认校验，不得复用这里的配置。
"""
import base64
import logging

import httpx

from game_assistant.adapters.league_of_legends.endpoints import (
    GAME_DETAIL, MATCH_HISTORY, RANKED_STATS, SUMMONER_CURRENT,
)

logger = logging.getLogger(__name__)


class LcuError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class LcuUnavailableError(LcuError):
    pass


class LcuClient:
    def __init__(self, port: str, token: str):
        auth = base64.b64encode(f"riot:{token}".encode()).decode()
        self._client = httpx.AsyncClient(
            base_url=f"https://127.0.0.1:{port}",
            headers={"Authorization": f"Basic {auth}"},
            verify=False,  # 仅限本机 LCU 自签证书，见模块 docstring
            timeout=15,
        )

    async def get(self, path: str) -> dict:
        try:
            resp = await self._client.get(path)
        except httpx.HTTPError as e:
            raise LcuUnavailableError(f"LCU 连接失败: {type(e).__name__}") from e
        if resp.status_code != 200:
            raise LcuError(f"HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as e:
            raise LcuError("响应非 JSON") from e
        if not isinstance(data, dict):
            raise LcuError("响应结构异常")
        return data

    async def current_summoner(self) -> dict:
        return await self.get(SUMMONER_CURRENT)

    async def ranked_stats(self, puuid: str) -> dict:
        return await self.get(RANKED_STATS.format(puuid=puuid))

    async def match_history(self, puuid: str, count: int = 20) -> dict:
        return await self.get(MATCH_HISTORY.format(puuid=puuid, count=count))

    async def game_detail(self, game_id: str) -> dict:
        return await self.get(GAME_DETAIL.format(game_id=game_id))
