import asyncio

from fastapi.testclient import TestClient
from game_assistant.adapters.neverness.adapter import NteAdapter
from game_assistant.config import Settings
from game_assistant.api import create_app
from game_assistant.models import Capability, FetchResult
from game_assistant.snapshots import SnapshotStore
from tests.test_api import FakeRegistry

class HomeClient:
    def __init__(self):
        self.calls = 0
        self.value = 320
    async def get_role_home(self, role):
        self.calls += 1
        return {'code': 0, 'data': {'roleid': role, 'staminaValue': self.value, 'staminaMaxValue': 320}}

async def test_manual_refresh_bypasses_cached_full_stamina_and_preserves_real_zero():
    a = NteAdapter(Settings(nte_access_token='test'))
    c = HomeClient()
    assert (await a._home(c, 'r'))[0]['data']['staminaValue'] == 320
    c.value = 0
    assert (await a._home(c, 'r'))[0]['data']['staminaValue'] == 320
    a.prepare_refresh()
    assert (await a._home(c, 'r'))[0]['data']['staminaValue'] == 0
    assert c.calls == 2

async def test_inflight_old_response_cannot_repopulate_invalidated_cache():
    a = NteAdapter(Settings(nte_access_token='test'))
    entered, release = asyncio.Event(), asyncio.Event()
    class SlowClient(HomeClient):
        async def get_role_home(self, role):
            result = await super().get_role_home(role)
            entered.set()
            await release.wait()
            return result
    c = SlowClient()
    old = asyncio.create_task(a._home(c, 'r'))
    await entered.wait()
    a.prepare_refresh()
    release.set()
    await old
    c.value = 0
    assert (await a._home(c, 'r'))[0]['data']['staminaValue'] == 0
    assert c.calls == 2

def test_refresh_endpoint_invalidates_adapter_cache_before_collecting(tmp_path):
    class ObservedAdapter(NteAdapter):
        capabilities = [Capability.STAMINA]
        async def fetch_stamina(self):
            return FetchResult(ok=self._home_cache is None and self._characters_cache is None)
    a = ObservedAdapter(Settings())
    app = create_app(registry=FakeRegistry(a), store=SnapshotStore(':memory:'),
        settings=Settings(db_path=str(tmp_path/'test.db')), start_scheduler=False)
    a._home_cache = a._characters_cache = ('old',)
    with TestClient(app) as c:
        result = c.post('/api/games/nte/refresh').json()
    assert result['results']['stamina']['ok']
