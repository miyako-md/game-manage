"""英雄 id→中文名目录（CommunityDragon zh_cn champion-summary）。

2026-09-13 实测：源 JSON 为数组 [{id, name, alias, ...}]，id=-1 为占位项（"无"）需跳过。
图标还没接入；同日实测 champion-icons 在 zh_cn 目录下 404，要用
global/default/v1/champion-icons/{id}.png。

网络失败 → 读缓存（哪怕已过期）→ 再失败返回 {}：映射失败降级为空表，
调用方显示"英雄 #id"，不得因此影响对局主流程。
"""
import json
import logging
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

CHAMPION_SUMMARY_URL = ("https://raw.communitydragon.org/latest/plugins/"
                        "rcp-be-lol-game-data/global/zh_cn/v1/champion-summary.json")
CACHE_TTL_SECONDS = 7 * 24 * 3600


class ChampionCatalog:
    """英雄 id→中文名映射，带 7 天文件缓存（默认 data/champions.json）。"""

    def __init__(self, cache_path: str = "data/champions.json",
                 url: str = CHAMPION_SUMMARY_URL, timeout: float = 15.0):
        self._cache_path = Path(cache_path)
        self._url = url
        self._timeout = timeout
        self._catalog: dict[int, dict] | None = None  # None = 尚未加载

    def _read_cache(self) -> tuple[dict[int, dict], bool]:
        """返回 (目录, 是否新鲜)；文件缺失、损坏或形状不对都返回 ({}, False)。"""
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
            champions = {int(k): v for k, v in (raw.get("champions") or {}).items()
                         if isinstance(v, dict)}
            fetched_at = float(raw.get("fetched_at") or 0)
            fresh = fetched_at > 0 and time.time() - fetched_at < CACHE_TTL_SECONDS
            return champions, fresh
        except (OSError, ValueError, TypeError, AttributeError):
            return {}, False

    def cached(self) -> dict[int, dict]:
        """只读缓存文件（可能过期或为空），不联网。"""
        return self._read_cache()[0]

    def _write_cache(self, catalog: dict[int, dict]) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(json.dumps({
                "fetched_at": time.time(),
                "champions": {str(k): v for k, v in catalog.items()},
            }, ensure_ascii=False), encoding="utf-8")
        except OSError:
            logger.warning("英雄目录缓存写入失败: %s", self._cache_path, exc_info=True)

    async def _fetch(self) -> dict[int, dict] | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(self._url)
                resp.raise_for_status()
                entries = resp.json()
        except Exception as e:
            logger.warning("英雄目录拉取失败（降级为缓存/空表）: %s", e)
            return None
        if not isinstance(entries, list):
            return None
        catalog: dict[int, dict] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            cid = entry.get("id")
            if not isinstance(cid, int) or cid < 0:  # id=-1 占位项跳过
                continue
            catalog[cid] = {"name": entry.get("name")}
        return catalog

    async def get(self) -> dict[int, dict]:
        """返回 {id: {"name": str}}；保证不抛异常。"""
        if self._catalog is not None:
            return self._catalog
        cached, fresh = self._read_cache()
        if cached and fresh:
            self._catalog = cached
            return self._catalog
        fetched = await self._fetch()
        if fetched:
            self._catalog = fetched
            self._write_cache(fetched)
        elif cached:
            self._catalog = cached  # 过期缓存也比空表好
        else:
            self._catalog = {}
        return self._catalog

    @staticmethod
    def name_for(catalog: dict, champion_id: int | None) -> str | None:
        if champion_id is None:
            return None
        return (catalog.get(champion_id) or {}).get("name")
