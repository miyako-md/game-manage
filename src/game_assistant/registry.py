from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.config import Settings


class GameRegistry:
    def __init__(self):
        self._adapters: dict[str, BaseGameAdapter] = {}

    def register(self, adapter: BaseGameAdapter) -> None:
        if adapter.game_id in self._adapters:
            raise ValueError(f"重复注册: {adapter.game_id}")
        self._adapters[adapter.game_id] = adapter

    def get(self, game_id: str) -> BaseGameAdapter:
        if game_id not in self._adapters:
            raise KeyError(f"未注册的游戏: {game_id}")
        return self._adapters[game_id]

    def all(self) -> list[BaseGameAdapter]:
        return list(self._adapters.values())


def build_default_registry(settings: Settings) -> GameRegistry:
    registry = GameRegistry()
    if settings.wuwa_enabled:
        try:
            from game_assistant.adapters.wuthering_waves.adapter import WutheringWavesAdapter
        except ImportError:
            import logging
            logging.getLogger(__name__).warning(
                "鸣潮适配器导入失败，跳过注册（检查依赖完整性）", exc_info=True)
        else:
            registry.register(WutheringWavesAdapter(settings))
    if settings.lol_enabled:
        try:
            from game_assistant.adapters.league_of_legends.adapter import LeagueOfLegendsAdapter
        except ImportError:
            import logging
            logging.getLogger(__name__).warning(
                "英雄联盟适配器导入失败，跳过注册（Task 8 完成前属预期）", exc_info=True)
        else:
            registry.register(LeagueOfLegendsAdapter(settings))
    return registry
