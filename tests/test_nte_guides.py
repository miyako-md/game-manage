import asyncio
import copy

import httpx
import pytest
import respx

from game_assistant.nte_guides import GuideService, GuideSourceError, parse_post
from game_assistant.nte_guides_catalog import guide_catalog

URL = 'https://bbs-api.tajiduo.com/bbs/wapi/getPostFull'


def post(content='<p>配装说明</p>', image='https://bbs-upload.tajiduo.com/test.png'):
    return {'code': 0, 'data': {'post': {'postId': 495234, 'subject': '黑羽攻略', 'uid': 'author',
        'content': content, 'images': [{'url': image}], 'createTime': 1790222409776,
        'lastEditTime': 0, 'isDelete': False}, 'users': [{'uid': 'author', 'nickname': '作者'}]}}


def test_catalog_covers_source_pages_and_distinguishes_reviewed_from_original_only():
    catalog = guide_catalog()
    assert len(catalog['guides']) == 23
    reviewed = [g for g in catalog['guides'] if g['status'] == 'reviewed']
    assert len(reviewed) == 5
    for g in reviewed:
        assert {s['key'] for s in g['sections']} == {'weapons', 'teams', 'sets', 'stats', 'skills'}
        assert all(s['items'] and s['pages'] for s in g['sections'])
    catalog['guides'][0]['name'] = 'changed'
    assert guide_catalog()['guides'][0]['name'] != 'changed'


def test_reviewed_image_ordering_keeps_equal_and_strict_priorities_distinct():
    guides = {g['name']:{s['key']:s for s in g['sections']} for g in guide_catalog()['guides']}
    assert '普通攻击 > 极轨终结 > 变轨技能 > 援护技' in guides['娜娜莉']['skills']['items'][0]
    assert '普通攻击 = 极轨终结 = 变轨技能 > 援护技' in guides['残虹']['skills']['items'][0]
    weapons = guides['娜娜莉']['weapons']['items'][0]
    assert weapons.index('预备备') < weapons.index('不屈之绵') < weapons.index('焰魂狂飙')


def test_post_is_plain_text_and_only_approved_source_images_are_exposed():
    data = post('<p>弧盘：罪与罚</p><script>secret()</script><p>词条 &gt; 攻击</p>')
    data['data']['post']['images'] += [{'url': 'javascript:alert(1)'}, {'url': 'https://evil.invalid/a.png'}, {'url': 'https://user:pass@bbs-upload.tajiduo.com/a.png'}]
    result = parse_post(data, 495234)
    assert result['paragraphs'] == ['弧盘：罪与罚', '词条 > 攻击']
    assert result['images'] == ['https://bbs-upload.tajiduo.com/test.png', None, None, None]
    assert result['author'] == '作者'
    assert result['published_at'].startswith('2026-09-24')
    assert result['edited_at'] is None
    assert result['fingerprint'] != parse_post(post('changed'), 495234)['fingerprint']


def test_image_positions_are_preserved_for_unsafe_and_repeated_original_pages():
    data = post(image='javascript:alert(1)')
    data['data']['post']['images'] += [{'url':'https://bbs-upload.tajiduo.com/page2.png'}] * 2
    assert parse_post(data,495234)['images'] == [None,'https://bbs-upload.tajiduo.com/page2.png','https://bbs-upload.tajiduo.com/page2.png']


@pytest.mark.parametrize('mutation', ['deleted', 'wrong_id', 'bad_images', 'failed', 'empty'])
def test_invalid_source_is_rejected(mutation):
    data = post()
    if mutation == 'deleted': data['data']['post']['isDelete'] = True
    if mutation == 'wrong_id': data['data']['post']['postId'] = 1
    if mutation == 'bad_images': data['data']['post']['images'] = 'bad'
    if mutation == 'failed': data['code'] = 500
    if mutation == 'empty': data['data']['post']['content'] = ''; data['data']['post']['images'] = []
    with pytest.raises(GuideSourceError): parse_post(data, 495234)


@respx.mock
async def test_cache_survives_restart_failure_retains_timestamp_and_unknown_id_never_fetches(tmp_path):
    route = respx.get(URL, params={'postId':495234}).respond(200, json=post())
    path = tmp_path / 'guides.sqlite3'
    service = GuideService(path)
    first = await service.read(495234)
    assert not first['stale'] and first['summary_changed']
    await asyncio.gather(service.read(495234), service.read(495234, force=True))
    assert route.call_count == 1
    restarted = GuideService(path)
    assert (await restarted.read(495234))['fetched_at'] == first['fetched_at']
    assert route.call_count == 1
    route.respond(503, text='private-token')
    failed = await restarted.read(495234, force=True)
    assert failed['stale'] and failed['fetched_at'] == first['fetched_at']
    assert 'private-token' not in str(failed)
    with pytest.raises(GuideSourceError): await restarted.read(123)
    assert route.call_count == 2
    after_failure_restart = await GuideService(path).read(495234)
    assert after_failure_restart['stale'] and after_failure_restart['error']
    assert after_failure_restart['fetched_at'] == first['fetched_at']
    assert route.call_count == 3


@respx.mock
async def test_refresh_detects_content_change_and_never_sends_authentication(tmp_path):
    route = respx.get(URL, params={'postId':495234}).respond(200, json=post())
    service = GuideService(tmp_path / 'guides.sqlite3')
    result = await service.read(495234)
    assert 'authorization' not in route.calls[0].request.headers
    service.last_attempt.clear()
    route.respond(200, json=post('<p>新的推荐</p>'))
    updated = await service.read(495234, force=True)
    assert updated['fingerprint'] != result['fingerprint'] and updated['summary_changed']


@respx.mock
async def test_response_limit_and_api_security(tmp_path):
    from game_assistant.api import create_app
    from game_assistant.config import Settings
    settings = Settings(db_path=str(tmp_path/'app.db'), auth_store_path=str(tmp_path/'auth.json'),
                        auth_allowed_origins=['http://testserver'], bilibili_sources={})
    app = create_app(settings=settings, start_scheduler=False)
    route = respx.get(URL).respond(200, content=b' '*(2*1024*1024+1))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        assert (await client.get('/api/nte/guides')).status_code == 200
        assert (await client.post('/api/nte/guides/sources/495234/refresh')).status_code == 403
        assert (await client.get('/api/nte/guides/sources/123')).status_code == 404
        assert route.call_count == 0
        assert (await client.get('/api/nte/guides/sources/495234')).status_code == 502
        assert (await client.get('/api/nte/guides', headers={'Host':'evil.invalid'})).status_code == 403
