import asyncio

import httpx
import pytest

from game_assistant import system_update
from game_assistant.api import create_app
from game_assistant.cloud_runtime import build_app, load_runtime
from game_assistant.config import Settings
from game_assistant.scheduler import AccountPollingScheduler
from game_assistant.sources.bilibili_service import BilibiliService
from game_assistant.system_update_version import capture_version
from tests.test_api import FakeRegistry
from tests.test_cloud_operations import fixture
from tests.test_registry import DummyAdapter
from tests.test_system_update_api import worker_status
from tests.test_system_update_version import marker


def application(tmp_path, monkeypatch, mode, enabled=True):
    started = asyncio.Event()
    calls = {'scheduler':0,'shutdown':0,'bili':0,'bili_close':0}
    class Scheduler:
        def start(self):
            calls['scheduler'] += 1
            started.set()
        async def shutdown(self):
            calls['shutdown'] += 1
    original_close = BilibiliService.close
    def bili_start(self):
        calls['bili'] += 1
    async def bili_close(self):
        calls['bili_close'] += 1
        await original_close(self)
    monkeypatch.setattr(BilibiliService,'start',bili_start)
    monkeypatch.setattr(BilibiliService,'close',bili_close)
    state = tmp_path/'updates'
    state.mkdir()
    if mode == 'local':
        settings = Settings(db_path=str(tmp_path/'local.db'),auth_store_path=str(tmp_path/'credentials.json'),
            wuwa_enabled=False,nte_enabled=False,endfield_enabled=False,lol_enabled=False,
            system_update_enabled=enabled,system_update_state_dir=str(state),bilibili_sources={'dummy':'1'})
        app = create_app(settings=settings,registry=FakeRegistry(DummyAdapter()),scheduler=Scheduler())
        base_url = 'http://127.0.0.1:8010'
    else:
        _,_,_,config = fixture(tmp_path)
        runtime = load_runtime(config)
        runtime.settings.system_update_enabled = enabled
        runtime.settings.system_update_state_dir = str(state)
        original_shutdown = AccountPollingScheduler.shutdown
        def cloud_start(self):
            calls['scheduler'] += 1
            started.set()
        async def cloud_shutdown(self):
            calls['shutdown'] += 1
            await original_shutdown(self)
        monkeypatch.setattr(AccountPollingScheduler,'start',cloud_start)
        monkeypatch.setattr(AccountPollingScheduler,'shutdown',cloud_shutdown)
        app = build_app(runtime)
        base_url = 'https://localhost:8443'
    version = capture_version(marker(tmp_path/'release'))
    app.state.system_update.version = app.state.running_version = version
    monkeypatch.setattr(system_update,'BACKGROUND_START_POLL_SECONDS',0.005)
    return app,state,base_url,started,calls


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['local','cloud'])
@pytest.mark.parametrize('terminal',['completed','rolled_back'])
async def test_verification_serves_health_before_background_starts_once(tmp_path,monkeypatch,mode,terminal):
    app,state,url,started,calls = application(tmp_path,monkeypatch,mode)
    worker_status(state,'verifying')
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=url) as client:
            health = await client.get('/api/health')
            assert health.status_code == 200 and health.json()['ready'] is True
            assert (await client.get('/api/system/update')).status_code == (200 if mode=='local' else 401)
        await asyncio.sleep(0.02)
        assert calls['scheduler'] == calls['bili'] == 0
        worker_status(state,terminal)
        await asyncio.wait_for(started.wait(),1)
        await asyncio.sleep(0.02)
        assert calls['scheduler'] == 1
        assert calls['bili'] == (1 if mode=='local' else 0)
    assert calls['shutdown'] == 1
    assert calls['bili_close'] == (1 if mode=='local' else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['local','cloud'])
@pytest.mark.parametrize('phase',['verifying','recovery_required','corrupt'])
async def test_exit_cancels_pending_start_and_closes_unstarted_resources(tmp_path,monkeypatch,mode,phase):
    app,state,_,_,calls = application(tmp_path,monkeypatch,mode)
    if phase == 'corrupt':
        (state/'status.json').write_text('{bad')
    else:
        worker_status(state,phase)
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.02)
        tasks = [task for task in asyncio.all_tasks() if task.get_name()=='system-update-background-start']
        assert len(tasks) == 1
        assert calls['scheduler'] == calls['bili'] == 0
    assert tasks[0].done() and tasks[0].cancelled()
    worker_status(state,'completed')
    await asyncio.sleep(0.02)
    assert calls['scheduler'] == calls['bili'] == 0
    assert calls['shutdown'] == 1
    assert calls['bili_close'] == (1 if mode=='local' else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['local','cloud'])
@pytest.mark.parametrize('phase',['preparing','absent','disabled'])
async def test_preparing_initial_and_disabled_keep_normal_startup(tmp_path,monkeypatch,mode,phase):
    app,state,_,_,calls = application(tmp_path,monkeypatch,mode,enabled=phase!='disabled')
    if phase != 'absent':
        worker_status(state,'verifying' if phase=='disabled' else 'preparing')
    async with app.router.lifespan_context(app):
        assert calls['scheduler'] == 1
        assert calls['bili'] == (1 if mode=='local' else 0)
        assert not [task for task in asyncio.all_tasks() if task.get_name()=='system-update-background-start']
    assert calls['shutdown'] == 1
