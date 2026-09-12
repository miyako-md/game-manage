import pytest

from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.models import Capability, FetchResult
from game_assistant.registry import GameRegistry


class DummyAdapter(BaseGameAdapter):
    game_id = "dummy"
    display_name = "测试游戏"
    section = "pc"
    capabilities = [Capability.STAMINA]

    def __init__(self):
        self.credentials_configured = True
        self.calls = []

    async def fetch_stamina(self) -> FetchResult:
        self.calls.append("stamina")
        return FetchResult(ok=True, payload=None)


def test_fetch_dispatches_and_rejects_unknown():
    a = DummyAdapter()
    import asyncio
    r = asyncio.run(a.fetch(Capability.STAMINA))
    assert r.ok is True
    r2 = asyncio.run(a.fetch(Capability.ACCOUNT))
    assert r2.ok is False and "不支持" in r2.error


def test_registry_register_get_all():
    reg = GameRegistry()
    a = DummyAdapter()
    reg.register(a)
    assert reg.get("dummy") is a
    assert reg.all() == [a]
    with pytest.raises(ValueError):
        reg.register(DummyAdapter())
    with pytest.raises(KeyError):
        reg.get("nope")
