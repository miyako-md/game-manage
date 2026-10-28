import asyncio

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
async def test_status_is_cache_only_and_unknown_until_first_fetch(tmp_path):
    from game_assistant.nte_guides_catalog import SOURCES
    route = respx.get(URL, params={'postId':495234}).respond(200, json=post())
    service = GuideService(tmp_path / 'guides.sqlite3')
    assert service.status(495234) is None and service.status(123) is None
    first = await service.read(495234)
    assert service.status(495234) == {'fetched_at': first['fetched_at'], 'summary_changed': True,
                                      'stale': False, 'error': False}
    service.last_attempt.clear()
    route.respond(503, text='private-token')
    await service.read(495234, force=True)
    status = GuideService(tmp_path / 'guides.sqlite3').status(495234)
    assert status['error'] and status['stale'] and status['fetched_at'] == first['fetched_at']
    assert service.error_codes[495234] == 'http:503' and service.cached(495234)['error_code'] == 'http:503'
    assert route.call_count == 2 and 'private-token' not in str(status)
    assert SOURCES[495234]['fingerprint'] != first['fingerprint']


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


def test_partial_summaries_keep_source_version_pages_and_explicit_gaps():
    partial = [g for g in guide_catalog()['guides'] if g['status'] == 'original_only']
    assert len(partial) == 18
    for g in partial:
        assert g['partial_reviewed_at'] == '2026-10-18'
        assert g['source_id'] == 491439
        assert len([s for s in g['sections'] if s['items']]) >= 3
        assert any(s['note'] and not s['items'] for s in g['sections'])
        assert all(s['pages'] == g['pages'] for s in g['sections'])
        assert g['gap_note']


AUTHOR_URL = 'https://bbs-api.tajiduo.com/bbs/wapi/getUserPostList'


def author_list(*rows):
    return {'code': 0, 'data': {'hasMore': False, 'page': 0, 'posts': [
        {'postId': pid, 'subject': title, 'createTime': 1792038957281, 'images': [{}] * images, 'isDelete': False, 'deleteTime': 0}
        for pid, title, images in rows]}}


def test_author_posts_find_only_guides_newer_than_the_catalog():
    from game_assistant.nte_guides import new_guide_posts, parse_author_posts
    posts = parse_author_posts(author_list(
        (515374, '异环角色 | V1.4明音凛培养攻略一图流', 5),   # role without a catalog entry
        (513951, '异环V1.4全角色弧盘推荐', 4),               # not a guide pattern
        (495234, '异环角色 | V1.4黑羽培养攻略一图流', 5),     # already the catalog source
        (477485, '异环角色 | V1.3灵可培养攻略一图流', 5),     # older than 灵可's catalog source 491439
        (530000, '异环角色 ｜ V1.5灵可培养攻略一图流', 6),    # newer than it (full-width bar)
        (530001, '异环V1.5全角色养成一图流', 6),
        (530002, '异环角色 | V1.5哈妮娅培养攻略一图流', 4)))  # an alias names the catalog entry
    found = {p['id']: (p['role'], p['known_role'], p['version']) for p in new_guide_posts(posts)}
    assert found == {515374: ('明音凛', False, '1.4'), 530000: ('灵可', True, '1.5'),
                     530001: (None, None, '1.5'), 530002: ('哈妮娅', True, '1.5')}
    assert parse_author_posts(author_list((0, 'x', 1), (1, None, 1))) == []
    with pytest.raises(GuideSourceError):
        parse_author_posts({'code': 0, 'data': {'posts': [{}] * 51}})


def test_catalog_shows_a_new_role_as_original_images_and_flags_a_newer_source():
    from game_assistant.nte_guides import new_guide_posts, parse_author_posts
    posts = new_guide_posts(parse_author_posts(author_list((515374, '异环角色 | V1.4明音凛培养攻略一图流', 5),
                                                           (530000, '异环角色 | V1.5灵可培养攻略一图流', 6))))
    catalog = guide_catalog(posts)
    new = next(g for g in catalog['guides'] if g['name'] == '明音凛')
    assert (new['status'], new['discovered'], new['source_id'], new['pages']) == ('original_only', True, 515374, [1, 2, 3, 4, 5])
    assert all(not s['items'] for s in new['sections'])
    linke = next(g for g in catalog['guides'] if g['name'] == '灵可')
    assert linke['newer_source']['id'] == 530000 and linke['source_id'] == 491439 and linke['status'] == 'reviewed'
    assert {s['id'] for s in catalog['sources'] if s.get('discovered')} == {515374, 530000}
    assert guide_catalog() == {**guide_catalog(), 'new_posts': []} and 'newer_source' not in str(guide_catalog())


@respx.mock
async def test_author_list_is_read_daily_and_unlocks_only_reported_posts(tmp_path):
    service = GuideService(tmp_path / 'guides.sqlite3')
    assert service.new_posts() == [] and not service.known(515374)
    route = respx.get(AUTHOR_URL).respond(200, json=author_list((515374, '异环角色 | V1.4明音凛培养攻略一图流', 5)))
    await service.read_author()
    await service.read_author()
    assert route.call_count == 1 and route.calls[0].request.url.params['uid'] == '10208854'
    assert 'cookie' not in route.calls[0].request.headers and 'authorization' not in route.calls[0].request.headers
    assert service.known(515374) and not service.known(513951)
    detail = respx.get(URL, params={'postId': 515374}).respond(200, json={**post(), 'data': {**post()['data'], 'post': {**post()['data']['post'], 'postId': 515374}}})
    value = await service.read(515374)
    assert detail.call_count == 1 and value['summary_changed'] is False and value['url'].endswith('postId=515374&id=2')
    # A failed list read keeps the last one.
    respx.get(AUTHOR_URL).respond(503)
    with pytest.raises(GuideSourceError):
        await service.read_author(force=True)
    assert service.known(515374)
