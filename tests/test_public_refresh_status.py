import pytest
from fastapi.testclient import TestClient
from game_assistant.models import Capability, FetchResult
from tests.test_bilibili_integration import setup
from tests.test_bilibili_source import UID
from tests.test_public_source_status import seed


@pytest.mark.parametrize('bili_error', [None, 'B站官方动态首页返回空列表；本轮2天增量采集未完成'])
def test_refresh_result_follows_effective_public_snapshot_and_retains_native_diagnostics(tmp_path, monkeypatch, bili_error):
    app, store = setup(tmp_path)
    seed(app, store)
    native = '未找到版本公告，保留上次成功日历'
    if bili_error:
        app.state.bilibili.store.set_state('nte', UID, status='error', message=bili_error)
    adapter = app.state.registry.get('nte')
    adapter.capabilities = {Capability.EVENTS, Capability.STAMINA}
    async def fetch(cap):
        return FetchResult(ok=False, error=native if cap == Capability.EVENTS else '登录已失效', error_kind='source_error' if cap == Capability.EVENTS else 'auth_expired')
    monkeypatch.setattr(adapter, 'fetch', fetch)
    monkeypatch.setattr(adapter, 'prepare_refresh', lambda: None)
    # No credential reads, background collection, or actual requests in this test.
    monkeypatch.setattr(app.state.bilibili, 'trigger', lambda *a: None)
    with TestClient(app, base_url='http://127.0.0.1:8010') as client:
        response = client.post('/api/games/nte/refresh', headers={'X-Game-Assistant': '1'})
        assert response.status_code == 200
        result = response.json()
        assert result['results']['events']['ok'] is (bili_error is None)
        assert result['results']['events']['error'] == bili_error
        assert result['source_results']['community']['events']['error'] == native
        assert result['results']['stamina']['error'] == '登录已失效'
        snap = client.get('/api/games/nte/snapshot/events').json()
        assert len(snap['payload']) == 1 and snap['version'] == '1.4'
        assert snap['poll_status']['error'] == result['results']['events']['error']
