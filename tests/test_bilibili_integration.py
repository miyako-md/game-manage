import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from game_assistant.api import create_app
from game_assistant.config import Settings
from game_assistant.event_calendar import BEIJING_TZ
from game_assistant.adapters.neverness.adapter import NteAdapter
from game_assistant.snapshots import SnapshotStore
from tests.test_api import FakeRegistry
from tests.test_bilibili_source import post, UID

def setup(tmp_path):
    settings = Settings(db_path=str(tmp_path/'bili.db'), bilibili_sources={'nte': UID})
    store = SnapshotStore(settings.db_path)
    app = create_app(registry=FakeRegistry(NteAdapter(settings)), store=store, settings=settings, start_scheduler=False)
    return app, store

def test_bilibili_news_merges_without_overwriting_existing_news_or_private_snapshots(tmp_path):
    app, store = setup(tmp_path)
    store.save('nte', 'news', json.dumps([{'title': '原有资讯', 'url': 'https://example.com/news'}]))
    store.save('nte', 'stamina', '{"current":0}')
    from game_assistant.sources.bilibili import classify_dynamic
    now = datetime.now(timezone.utc)
    row = classify_dynamic(post('9月15日版本更新公告', published=now.timestamp()), UID, now)
    app.state.bilibili.store.save_rows('nte', UID, [row])
    with TestClient(app, base_url="http://127.0.0.1:8010") as c:
        assert 'news' in c.get('/api/games').json()[0]['capabilities']
        rows = c.get('/api/games/nte/snapshot/news').json()['payload']
        assert len(rows) == 2 and rows[0]['source'] == 'bilibili'
        assert c.get('/api/games/nte/snapshot/stamina').json()['payload']['current'] == 0
        assert c.post('/api/auth/bilibili-source/credentials', json={'sessdata':'test'}).status_code == 403

async def test_service_backfill_and_failure_preserve_successful_records(tmp_path):
    app, _ = setup(tmp_path)
    service = app.state.bilibili
    class Good:
        def __init__(self,*args): pass
        async def page(self,offset): return {'items':[post('9月15日活动开启公告',published=datetime.now(timezone.utc).timestamp())], 'has_more':False}
    service.client_factory=Good
    await service.run('nte',True)
    assert len(service.news('nte')) == 1 and service.statuses()[0]['history_complete']
    service.store.set_state('nte',UID,next_retry=0)
    class Bad(Good):
        async def page(self,offset): return {'items':[], 'has_more':False}
    service.client_factory=Bad
    await service.run('nte',True)
    assert service.statuses()[0]['status']=='error' and len(service.news('nte'))==1
    await service.close()

def test_mobile_calendar_primary_and_community_fallback_leave_native_storage_intact(tmp_path):
    app, store = setup(tmp_path)
    native = [{'name':'环期赠礼签到','source_title':'手动配置','start_at':'2026-08-13T00:00:00+08:00','end_at':'2026-09-24T05:59:00+08:00'}]
    store.save('nte','events',json.dumps(native))
    from tests.test_public_content import notice
    # The calendar only keeps a version that has already started, and the store
    # only keeps 60 days of posts, so the dates follow today's date.
    start = datetime.now(BEIJING_TZ) - timedelta(days=5)
    end = start + timedelta(days=30)
    row=notice('《异环》1.3版本更新公告\n●「环期赠礼」签到活动\n'
               f'活动时间：{start.month}月{start.day}日版本更新后-{end.month}月{end.day}日05:59',
               published=start.astimezone(timezone.utc).isoformat())
    row.update(source_uid=UID, reason='accepted', reason_text='accepted')
    with TestClient(app, base_url="http://127.0.0.1:8010") as c:
        fallback=c.get('/api/games/nte/snapshot/events').json()
        assert fallback['primary_source']=='community' and len(fallback['payload'])==1
        app.state.bilibili.store.save_rows('nte',UID,[row])
        result=c.get('/api/games/nte/snapshot/events').json()
        assert result['primary_source']=='bilibili' and len(result['payload'])==1
        assert result['payload'][0]['start_at'] is None
        assert json.loads(store.get('nte','events')['payload'])==native
        assert result['poll_status']['scope']=='public_source'

def test_lol_catalog_and_snapshot_are_not_changed_even_with_a_configured_bili_uid(tmp_path):
    from tests.test_registry import DummyAdapter
    from game_assistant.models import Capability
    class Lol(DummyAdapter):
        game_id='league_of_legends'
        capabilities={Capability.NEWS,Capability.ANNOUNCEMENT}
    settings=Settings(db_path=str(tmp_path/'lol.db'),bilibili_sources={'league_of_legends':'123'})
    store=SnapshotStore(settings.db_path)
    native=[{'title':'LOL资讯','url':'https://lol.qq.com/news'}]
    store.save('league_of_legends','news',json.dumps(native))
    app=create_app(registry=FakeRegistry(Lol()),store=store,settings=settings,start_scheduler=False)
    with TestClient(app, base_url="http://127.0.0.1:8010") as c:
        assert set(c.get('/api/games').json()[0]['capabilities'])=={'news','announcement'}
        result=c.get('/api/games/league_of_legends/snapshot/news').json()
        assert result['payload']==native and 'primary_source' not in result


def test_official_community_articles_are_visible_without_promoting_calendar_decisions(tmp_path):
    app, _ = setup(tmp_path)
    from game_assistant.sources.bilibili import classify_dynamic
    now = datetime.now(timezone.utc)
    bodies = ['创作征集网页活动开启\n活动时间10月4日到10月20日',
              '社区同人征集开启，欢迎投稿', '版本PV正式发布\n10月4日',
              '创作征集视频\n10月4日活动开启']
    rows = [classify_dynamic(post(body, id=str(i + 1), published=now.timestamp(), kind='DYNAMIC_TYPE_AV' if i == 3 else 'DYNAMIC_TYPE_DRAW'), UID, now) for i, body in enumerate(bodies)]
    app.state.bilibili.store.save_rows('nte', UID, rows)
    visible = app.state.bilibili.news('nte')
    assert {row['id'] for row in visible} == {'1', '2'}
    assert all(row['decision'] == 'excluded' for row in visible)
    assert app.state.bilibili.statuses()[0]['article_count'] == 2
    assert app.state.bilibili.calendar('nte')['events'] == []
    assert [r['decision'] for r in app.state.bilibili.store.rows('nte', UID)] == ['excluded'] * 4


def test_truncated_community_article_warns_and_keeps_previous_complete_body(tmp_path):
    app, _ = setup(tmp_path)
    from game_assistant.sources.bilibili import classify_dynamic
    now = datetime.now(timezone.utc)
    item = post('创作征集活动\n完整正文末尾', published=now.timestamp())
    complete = classify_dynamic(item, UID, now)
    app.state.bilibili.store.save_rows('nte', UID, [complete])
    item['modules']['module_dynamic']['major']['opus']['summary'] = {'text': '创作征集活动\n截断节选', 'has_more': True}
    partial = classify_dynamic(item, UID, now)
    assert partial['content_status'] == 'unavailable'
    app.state.bilibili.store.save_rows('nte', UID, [partial])
    row = app.state.bilibili.news('nte')[0]
    assert row['body'].endswith('完整正文末尾')
    assert row['content_status'] == 'stale'
    assert row['decision'] == 'excluded'
    assert app.state.bilibili.calendar('nte')['events'] == []


def test_endfield_keeps_official_priority_and_adds_bilibili_community_articles(tmp_path):
    from game_assistant.adapters.endfield.adapter import EndfieldAdapter
    from game_assistant.sources.bilibili import classify_dynamic
    uid = '1265652806'
    settings = Settings(db_path=str(tmp_path / 'endfield.db'), bilibili_sources={'endfield': uid})
    store = SnapshotStore(settings.db_path)
    store.save('endfield', 'news', json.dumps([{'title': '官网版本说明', 'source': 'official', 'url': 'https://endfield.hypergryph.com/news/42'}]))
    app = create_app(registry=FakeRegistry(EndfieldAdapter(settings)), store=store, settings=settings, start_scheduler=False)
    now = datetime.now(timezone.utc)
    item = post('网页活动创作征集开启\n10月4日开始', published=now.timestamp())
    item['modules']['module_author']['mid'] = int(uid)
    row = classify_dynamic(item, uid, now)
    app.state.bilibili.store.save_rows('endfield', uid, [row])
    with TestClient(app, base_url='http://127.0.0.1:8010') as client:
        result = client.get('/api/games/endfield/snapshot/news').json()
        assert result['primary_source'] == 'official'
        assert len(result['payload']) == 2
        assert result['payload'][0]['source'] == 'official'
        assert result['payload'][1]['source'] == 'bilibili'
        assert result['payload'][1]['decision'] == 'excluded'
