from datetime import datetime

import pytest
import respx

from game_assistant.wuwa_guide_extract import POST_URL
from game_assistant.wuwa_guide_updates import SEARCH_URL
from game_assistant.wuwa_tower_guides import CN, TowerGuides, parse_detail, parse_post

NOW = datetime(2026, 10, 21, 12, tzinfo=CN)
IMAGE = 'https://prod-alicdn-community.kurobbs.com/forum/{}.png'


def post(post_id='1559169379056631808', title='鸣潮逆境深塔261012期推荐阵容', user='10525366', **values):
    return {'postId': post_id, 'postTitle': title, 'gameId': 3, 'postType': 1, 'userName': '作者甲',
            'userId': user, 'createTimestamp': '1791776547000', **values}


def detail(post_id='1559169379056631808', user='10525366', images=('a', 'b'), **values):
    blocks = [{'contentType': 1, 'content': '游戏内UID：100000000'},
              {'contentType': 1, 'content': '中塔主推合成角色，左右塔按抗性选择队伍。'}]
    blocks += [{'contentType': 2, 'url': IMAGE.format(name)} for name in images]
    blocks.append({'contentType': 2, 'url': 'https://example.com/evil.png'})
    return {'code': 200, 'data': {'postDetail': {'id': post_id, 'postUserId': user, 'postContent': blocks,
            'topicList': [{'topicName': '3.7版本攻略'}], **values}}}


def search(*posts, has_next=False):
    return {'code': 200, 'data': {'postList': list(posts), 'hasNext': has_next}}


def test_title_gives_the_period_and_rejects_implausible_posts():
    item = parse_post(post(), NOW)
    assert item['periodStart'] == '2026-10-12T04:00:00+08:00'
    assert item['periodEnd'] == '2026-11-09T04:00:00+08:00'
    assert item['scope'] == '2026-10-12 期深境区' and item['preferred']
    assert item['publishedAt'] == '2026-10-12 11:42'
    assert item['url'] == 'https://www.kurobbs.com/forum/post/1559169379056631808'
    assert not parse_post(post(user='1'), NOW)['preferred']
    for bad in (post(title='鸣潮逆境深塔261013期推荐阵容'),   # not a Monday
                post(title='鸣潮逆境深塔261109期推荐阵容'),   # future period
                post(title='鸣潮逆境深塔260525期推荐阵容'),   # outside the kept window
                post(title='逆境深塔通关思路详解'), post(postType=2), post(gameId=2), post(postId='x')):
        assert parse_post(bad, NOW) is None


def test_detail_keeps_safe_images_and_marks_automatic_entries_unreviewed():
    guide = parse_detail(detail(), parse_post(post(), NOW))
    assert guide['lineupImages'] == [IMAGE.format('a'), IMAGE.format('b')]
    assert guide['version'] == '3.7' and guide['status'] == 'unreviewed'
    assert guide['modes'] == ['tower'] and guide['format'] == '图文攻略' and guide['boss'] is None
    assert guide['summary'].startswith('中塔主推') and '未人工校对' in guide['summary']
    assert 'UID' not in guide['summary']
    candidate = parse_post(post(), NOW)
    for raw in (detail(user='1'), detail(post_id='2'), detail(isHide=True), detail(images=()), {'code': 500}):
        with pytest.raises(Exception):
            parse_detail(raw, candidate)


def clock(value=NOW):
    return lambda: value.timestamp()


@respx.mock
async def test_check_prefers_reviewed_author_and_keeps_last_good(tmp_path):
    respx.post(SEARCH_URL).respond(200, json=search(post('2', user='1'), post(), post('3', '鸣潮逆境深塔260914期推荐阵容')))
    details = respx.post(POST_URL)
    details.side_effect = lambda request: respx.MockResponse(200, json=detail(
        *(('1559169379056631808', '10525366') if b'1559169379056631808' in request.content else ('3', '10525366'))))
    service = TowerGuides(tmp_path / 'g.db', clock=clock())
    first = await service.check()
    assert [g['id'] for g in first['guides']] == ['1559169379056631808', '3']
    assert first['error'] is None and first['checked_at']
    assert details.call_count == 2
    assert (await service.check())['deferred']

    later = TowerGuides(tmp_path / 'g.db', clock=clock(NOW.replace(hour=13)))
    respx.post(SEARCH_URL).respond(200, json=search(post('2', user='1')))
    second = await later.check()
    # A non-preferred post never replaces a stored preferred one; known posts are not re-read.
    assert [g['id'] for g in second['guides']] == ['1559169379056631808', '3']
    assert details.call_count == 2

    respx.post(SEARCH_URL).respond(503, text='DO_NOT_EXPOSE')
    failed = await TowerGuides(tmp_path / 'g.db', clock=clock(NOW.replace(hour=14))).check()
    assert failed['error'] and failed['guides'] == second['guides']
    assert failed['checked_at'] == second['checked_at'] and 'DO_NOT_EXPOSE' not in str(failed)


@respx.mock
async def test_unreadable_post_falls_back_to_another_author_only_when_nothing_better(tmp_path):
    respx.post(SEARCH_URL).respond(200, json=search(post('2', user='1')))
    respx.post(POST_URL).respond(200, json=detail('2', '1'))
    service = TowerGuides(tmp_path / 'g.db', clock=clock())
    guides = (await service.check())['guides']
    assert [(g['id'], g['preferred']) for g in guides] == [('2', False)]


def test_due_retries_sooner_while_the_current_period_is_missing(tmp_path):
    service = TowerGuides(tmp_path / 'g.db', clock=clock())
    assert service.due()
    guide = {'periodStart': '2026-10-12T04:00:00+08:00', 'periodEnd': '2026-11-09T04:00:00+08:00'}
    old = {'periodStart': '2026-09-14T04:00:00+08:00', 'periodEnd': '2026-10-12T04:00:00+08:00'}
    hours = lambda n: NOW.replace(hour=12 - n).isoformat()
    assert not service.due({'guides': [guide], 'attempted_at': hours(7)})
    assert service.due({'guides': [old], 'attempted_at': hours(7)})
    assert not service.due({'guides': [old], 'attempted_at': hours(5)})


@respx.mock
async def test_due_read_starts_one_background_check(tmp_path):
    route = respx.post(SEARCH_URL).respond(200, json=search())
    service = TowerGuides(tmp_path / 'g.db', clock=clock())
    assert service.read()['guides'] == [] and service.read()['checked_at'] is None
    await service.task
    assert route.call_count == 1
    assert service.read()['checked_at'] and service.task.done()


async def test_local_routes_read_cache_and_check(tmp_path, monkeypatch):
    import httpx
    from game_assistant.api import create_app
    from game_assistant.config import Settings
    from game_assistant.wuwa_tower_guides import TowerGuides as Service
    calls = []

    async def check(self):
        calls.append(1)
        return {'guides': [], 'checked_at': 'now', 'attempted_at': 'now', 'error': None}
    monkeypatch.setattr(Service, 'check', check)
    monkeypatch.setattr(Service, 'due', lambda self, value=None: False)
    settings = Settings(db_path=str(tmp_path / 'app.db'), auth_store_path=str(tmp_path / 'auth.json'),
                        auth_allowed_origins=['http://testserver'], bilibili_sources={})
    app = create_app(settings=settings, start_scheduler=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        assert (await client.get('/api/wuwa/guides/tower')).json()['guides'] == []
        assert (await client.post('/api/wuwa/guides/tower/check')).status_code == 403
        assert calls == []
        response = await client.post('/api/wuwa/guides/tower/check', headers={'X-Game-Assistant': '1'})
        assert response.status_code == 200 and calls == [1]
