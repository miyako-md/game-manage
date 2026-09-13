"""英雄 id→中文名目录（CommunityDragon zh_cn champion-summary）。

2026-09-13 实测校准：
- 源 JSON 为数组 [{id, name, alias, squarePortraitPath, ...}]，id=-1 为占位项
  （"无"）需跳过；实测字段名为 squarePortraitPath（无 iconPath），解析时两者
  兼容（iconPath 优先，缺失时取 squarePortraitPath）。
- 图标 URL：zh_cn 语言目录下 champion-icons 实测 404（图标不分语言），
  global/default/v1/champion-icons/{id}.png 实测 200，故 icon 统一拼 default 目录。

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
ICON_BASE = ("https://raw.communitydragon.org/latest/plugins/"
             "rcp-be-lol-game-data/global/default/v1")
_ASSETS_PREFIX = "/lol-game-data/assets/v1/"
CACHE_TTL_SECONDS = 7 * 24 * 3600


def _icon_url(path: str | None) -> str | None:
    # 游戏数据路径 /lol-game-data/assets/v1/champion-icons/{id}.png
    # → https://raw.communitydragon.org/latest/plugins/.../global/default/v1/champion-icons/{id}.png
    if not path:
        return None
    if path.startswith("http"):
        return path
    rel = path[len(_ASSETS_PREFIX):] if path.startswith(_ASSETS_PREFIX) else path.lstrip("/")
    return f"{ICON_BASE}/{rel}"


class ChampionCatalog:
    """英雄 id→中文名/图标映射，带 7 天文件缓存（默认 data/champions.json）。"""

    def __init__(self, cache_path: str = "data/champions.json",
                 url: str = CHAMPION_SUMMARY_URL, timeout: float = 15.0):
        self._cache_path = Path(cache_path)
        self._url = url
        self._timeout = timeout
        self._catalog: dict[int, dict] | None = None  # None = 尚未加载

    def _read_cache(self) -> tuple[dict[int, dict], bool]:
        """返回 (目录, 是否新鲜)；文件缺失/损坏返回 ({}, False)。"""
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
            champions = {int(k): v for k, v in (raw.get("champions") or {}).items()}
            fetched_at = float(raw.get("fetched_at") or 0)
            fresh = fetched_at > 0 and time.time() - fetched_at < CACHE_TTL_SECONDS
            return champions, fresh
        except (OSError, ValueError):
            return {}, False

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
            catalog[cid] = {
                "name": entry.get("name"),
                "icon": _icon_url(entry.get("iconPath")
                                  or entry.get("squarePortraitPath")),
            }
        return catalog

    async def get(self) -> dict[int, dict]:
        """返回 {id: {"name": str, "icon": url}}；保证不抛异常。"""
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
