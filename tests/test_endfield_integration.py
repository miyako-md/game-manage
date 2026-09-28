from datetime import datetime, timedelta, timezone

import httpx

from game_assistant.adapters.endfield.adapter import EndfieldAdapter
from game_assistant.api import create_app
from game_assistant.config import Settings
from game_assistant.endfield_public import PublicSourceError
from game_assistant.models import Capability, GameEvent
from game_assistant.scheduler import PollingScheduler
from game_assistant.snapshots import SnapshotStore
from tests.test_api import FakeRegistry


async def test_official_public_data_reaches_calendar_without_login_and_keeps_source(tmp_path):
    settings = Settings(db_path=str(tmp_path / 'game.db'), bilibili_sources={'endfield': '1265652806'},
                        auth_allowed_origins=['http://testserver'])
    adapter = EndfieldAdapter(settings)
    registry = FakeRegistry(adapter)
    store = SnapshotStore(settings.db_path)
    scheduler = PollingScheduler(registry, store, settings)
    app = create_app(registry=registry, store=store, scheduler=scheduler, settings=settings,
                     start_scheduler=False)
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    class Public:
        fail = False
        calls = []

        async def news(self, force=False):
            self.calls.append(force)
            if self.fail:
                raise PublicSourceError('官网暂时无法访问')
            return [{'title': '本期版本公告', 'url': 'https://endfield.hypergryph.com/news/2653',
                     'source': 'official', 'source_name': '终末地官网'}]

        async def events(self, force=False):
            self.calls.append(force)
            if self.fail:
                raise PublicSourceError('官网暂时无法访问')
            return [{'name': '限时活动', 'end_at': tomorrow, 'start_at': None,
                     'start_text': '版本更新后', 'end_precision': 'minute', 'source': 'official',
                     'source_name': '终末地官网', 'version': '雪凇幽梦'}]

    public = Public()
    adapter._public = public
    # A conflicting fallback must not replace official dates or provenance.
    app.state.bilibili.news = lambda _: [{'title': '本期版本公告', 'source': 'bilibili'}]
    app.state.bilibili.calendar = lambda _: {'events': [{'name': '旧活动'}], 'version': '旧版本'}
    app.state.bilibili.trigger = lambda _: None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        before = (await client.get('/api/games/endfield/snapshot/news')).json()
        assert before['primary_source'] == 'bilibili'
        response = await client.post('/api/games/endfield/refresh', headers={'X-Game-Assistant': '1'})
        result = response.json()['results']
        assert result['account']['error_kind'] == 'unconfigured'
        assert result['news']['ok'] and result['events']['ok']
        assert public.calls == [True, False]
        calendar = (await client.get('/api/games/endfield/snapshot/events')).json()
        assert calendar['primary_source'] == 'official'
        assert calendar['version'] == '雪凇幽梦'
        assert calendar['payload'][0]['start_text'] == '版本更新后'
        assert datetime.fromisoformat(calendar['payload'][0]['end_at']) == datetime.fromisoformat(tomorrow)
        assert isinstance((await adapter.fetch_events()).payload[0], GameEvent)
        public.fail = True
        assert not (await scheduler.poll_once('endfield', Capability.EVENTS)).ok
        stale = (await client.get('/api/games/endfield/snapshot/events')).json()
        assert stale['stale'] and stale['payload'][0]['name'] == '限时活动'
        assert stale['poll_status']['error'] == '官网暂时无法访问'
    await app.state.bilibili.close()
