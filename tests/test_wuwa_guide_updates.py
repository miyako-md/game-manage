import asyncio

import httpx
import pytest
import respx

from game_assistant.wuwa_guide_updates import GuideUpdates, Search, SEARCH_URL, parse_candidate


def post(title='鸣潮角色 | V3.7<em>心</em>培养攻略一图流', **values):
    return dict(postId='1555005846752059392', postTitle=title, gameId=3, postType=1,
                userName='轩儿Xuaner', userId='10525366', createTimestamp='1790760000000', **values)


def test_public_search_metadata_is_not_a_reviewed_recommendation():
    result = parse_candidate(post(), Search(character_id='1311', name='心', attribute='导电'))
    assert result['title'] == '鸣潮角色 | V3.7心培养攻略一图流'
    assert result['version'] == '3.7' and result['status'] == 'unreviewed'
    assert result['url'] == 'https://www.kurobbs.com/forum/post/1555005846752059392'
    assert result['published_at'].startswith('2026-09-30')


@pytest.mark.parametrize('title', ['鉴心培养攻略', '3.7版本攻略合集：心照红尘', '心突破材料一览', '心前瞻攻略', '心剧情解析'])
def test_single_character_name_does_not_match_unrelated_posts(title):
    assert parse_candidate(post(title), Search(character_id='1311', name='心', attribute='导电')) is None


def test_forms_require_explicit_evidence():
    query = Search(character_id='1408', name='漂泊者', attribute='气动')
    assert parse_candidate(post('湮灭主培养攻略'), query) is None
    assert parse_candidate(post('漂泊者培养攻略'), query) is None
    assert parse_candidate(post('V3.7气动主培养攻略'), query)
    yangyang = Search(character_id='1402', name='秧秧', attribute='气动')
    assert parse_candidate(post('秧秧·玄翎培养攻略'), yangyang) is None
    assert parse_candidate(post('气动秧秧培养攻略'), yangyang)


@respx.mock
async def test_checks_coalesce_persist_and_keep_last_good_on_failure(tmp_path, monkeypatch):
    route = respx.post(SEARCH_URL).respond(200, json={'code': 200, 'data': {'postList': [post()], 'hasNext': False}})
    path = tmp_path / 'guides.db'
    service = GuideUpdates(path,auto_extract=False)
    query = Search(character_id='1311', name='心', attribute='导电')
    first, second = await asyncio.gather(service.check(query), service.check(query))
    assert route.call_count == 1
    assert first['checked_at'] == second['checked_at']
    assert len(service.cached(query)['candidates']) == 1
    assert 'token' not in route.calls[0].request.headers
    assert 'searchType=1' in route.calls[0].request.content.decode()
    route.respond(503, text='DO_NOT_EXPOSE')
    import time
    now = time.time()
    monkeypatch.setattr('game_assistant.wuwa_guide_updates.time.time', lambda: now + 31)
    service = GuideUpdates(path,auto_extract=False)
    failed = await service.check(query)
    assert failed['error'] and failed['checked_at'] == first['checked_at']
    assert failed['candidates'] == first['candidates']
    assert 'DO_NOT_EXPOSE' not in str(failed)
    assert GuideUpdates(path).cached(query)['error']


@respx.mock
async def test_bad_or_partial_response_is_not_reported_as_no_updates(tmp_path):
    route = respx.post(SEARCH_URL).respond(200, json={'code': 200, 'data': {}})
    service = GuideUpdates(tmp_path / 'guides.db',auto_extract=False)
    result = await service.check(Search(character_id='1311', name='心'))
    assert result['error'] and result['checked_at'] is None
    assert len(route.calls) == 1


@respx.mock
async def test_pagination_is_bounded_and_deduplicated(tmp_path):
    route = respx.post(SEARCH_URL).respond(200, json={'code':200,'data':{'postList':[post()],'hasNext':True}})
    result = await GuideUpdates(tmp_path / 'guides.db',auto_extract=False).check(Search(character_id='1311',name='心'))
    assert route.call_count == 2
    assert result['limited'] is True and len(result['candidates']) == 1


@respx.mock
async def test_routes_allow_anonymous_reads_but_protect_checks_and_validate_inputs(tmp_path):
    from game_assistant.api import create_app
    from game_assistant.config import Settings
    settings = Settings(db_path=str(tmp_path / 'app.db'), auth_store_path=str(tmp_path / 'auth.json'),
                        auth_allowed_origins=['http://testserver'], bilibili_sources={})
    app = create_app(settings=settings, start_scheduler=False)
    route = respx.post(SEARCH_URL).respond(200, content=b' ' * (2 * 1024 * 1024 + 1))
    query = {'character_id': '1311', 'name': '心', 'attribute': '导电'}
    url = '/api/wuwa/guides/updates'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        assert (await client.get(url, params=query)).json()['checked_at'] is None
        assert route.call_count == 0
        assert (await client.post(url, json=query)).status_code == 403
        assert (await client.get(url, params={**query, 'character_id': 'bad'})).status_code == 422
        assert (await client.get(url, params=query, headers={'Host': 'evil.invalid'})).status_code == 403
        headers = {'X-Game-Assistant': '1'}
        assert (await client.post(url, json={**query, 'name': 'https://evil.invalid'}, headers=headers)).status_code == 422
        result = (await client.post(url, json=query, headers=headers)).json()
        assert result['error'] and result['checked_at'] is None
        assert route.call_count == 1


@respx.mock
async def test_check_extracts_a_real_post_and_unknown_or_video_selections_never_fetch(tmp_path):
    from game_assistant.wuwa_guide_extract import POST_URL
    from fastapi import HTTPException
    respx.post(SEARCH_URL).respond(200,json={'code':200,'data':{'postList':[post()],'hasNext':False}})
    detail = respx.post(POST_URL).respond(200,json={'code':200,'data':{'postDetail':{
        'id':'1555005846752059392','postTitle':'V3.7心培养攻略','gameId':3,'postType':1,
        'postContent':[{'contentType':1,'content':'武器推荐：玉阙玄华。'}]}}})
    service = GuideUpdates(tmp_path/'guides.db')
    query = Search(character_id='1311',name='心',attribute='导电')
    result = await service.check(query)
    assert result['active_guide']['sections'][0]['text'] == '武器推荐：玉阙玄华。'
    assert result['active_guide']['sections'][0]['status'] == 'extracted'
    assert detail.call_count == 1
    assert service.cached(query)['active_guide'] == result['active_guide']
    with pytest.raises(HTTPException) as error:
        await service.extract(query,'1')
    assert error.value.status_code == 404 and detail.call_count == 1
    candidate = result['candidates'][0]; candidate['kind']='video'
    service.save(query,{**result,'candidates':[candidate]})
    with pytest.raises(HTTPException) as error:
        await service.extract(query,candidate['id'])
    assert error.value.status_code == 422 and detail.call_count == 1


@respx.mock
async def test_first_extraction_failure_reaches_the_page_and_a_later_success_clears_it(tmp_path):
    from game_assistant.wuwa_guide_extract import POST_URL
    respx.post(SEARCH_URL).respond(200,json={'code':200,'data':{'postList':[post()],'hasNext':False}})
    detail = respx.post(POST_URL).respond(503,text='DO_NOT_EXPOSE')
    service = GuideUpdates(tmp_path/'guides.db')
    query = Search(character_id='1311',name='心',attribute='导电')
    result = await service.check(query)  # 自动提炼首次失败，此前没有任何培养建议
    assert result['active_guide'] is None and result['extraction_error']
    assert 'DO_NOT_EXPOSE' not in str(result)
    assert GuideUpdates(tmp_path/'guides.db').cached(query)['extraction_error'] == result['extraction_error']
    detail.respond(200,json={'code':200,'data':{'postDetail':{
        'id':'1555005846752059392','postTitle':'V3.7心培养攻略','gameId':3,'postType':1,
        'postContent':[{'contentType':1,'content':'武器推荐：玉阙玄华。'}]}}})
    service.extractor.attempts.clear()
    fixed = await service.extract(query,'1555005846752059392')
    assert fixed['active_guide']['sections'][0]['text'] == '武器推荐：玉阙玄华。'
    assert fixed['extraction_error'] is None


def test_preferred_candidate_is_the_established_author_then_the_newest_article():
    from game_assistant.wuwa_guide_updates import preferred_candidate
    video = {'id': '1', 'kind': 'video', 'author_id': '10525366'}
    newest = {'id': '2', 'kind': 'article', 'author_id': '1'}
    author = {'id': '3', 'kind': 'article', 'author_id': '10525366'}
    assert preferred_candidate([video, newest, author]) is author
    assert preferred_candidate([video, newest]) is newest
    assert preferred_candidate([video]) is None and preferred_candidate([]) is None


def detail_response(post_id='1555005846752059392'):
    return {'code':200,'data':{'postDetail':{'id':post_id,'postTitle':'V3.7心培养攻略','gameId':3,'postType':1,
            'postContent':[{'contentType':1,'content':'武器推荐：玉阙玄华。'}]}}}


@respx.mock
async def test_extract_policy_reads_only_changed_posts_unless_asked(tmp_path, monkeypatch):
    import time
    from game_assistant.wuwa_guide_extract import POST_URL
    respx.post(SEARCH_URL).respond(200,json={'code':200,'data':{'postList':[post()],'hasNext':False}})
    detail = respx.post(POST_URL).respond(200,json=detail_response())
    service = GuideUpdates(tmp_path/'guides.db')
    query = Search(character_id='1311',name='心',attribute='导电')
    now = [time.time()]
    monkeypatch.setattr('game_assistant.wuwa_guide_updates.time.time', lambda: now[0])
    async def check(**kwargs):
        now[0] += 31
        service.extractor.attempts.clear()
        return await service.check(query, **kwargs)
    result = await check(extract='never')
    assert detail.call_count == 0 and 'extracted' not in result and result['candidates']
    result = await check(extract='changed', known={'1555005846752059392'})  # a static source is not news
    assert detail.call_count == 0 and 'extracted' not in result
    result = await check(extract='changed')
    assert detail.call_count == 1 and result['extracted'] and result['active_guide']['sourceId'] == '1555005846752059392'
    result = await check(extract='changed')  # already the active guide's source
    assert detail.call_count == 1 and 'extracted' not in result
    assert (await check())['extracted'] and detail.call_count == 2  # the page button keeps re-reading


@respx.mock
@pytest.mark.parametrize('response,code', [
    (httpx.Response(429, text='DO_NOT_EXPOSE'), 'http:429'),
    (httpx.Response(403, text='DO_NOT_EXPOSE'), 'http:403'),
    (httpx.ConnectError('DO_NOT_EXPOSE'), 'transport:ConnectError'),
    (httpx.ReadTimeout('DO_NOT_EXPOSE'), 'timeout'),
    (httpx.Response(200, text='DO_NOT_EXPOSE{'), 'parse:json'),
    (httpx.Response(200, json={'code': 500, 'msg': 'DO_NOT_EXPOSE'}), 'parse:value'),
])
async def test_failures_keep_the_message_and_record_only_a_short_code(tmp_path, response, code):
    route = respx.post(SEARCH_URL)
    if isinstance(response, Exception):
        route.mock(side_effect=response)
    else:
        route.mock(return_value=response)
    service = GuideUpdates(tmp_path / 'guides.db', auto_extract=False)
    query = Search(character_id='1311', name='心', attribute='导电')
    result = await service.check(query)
    assert result['error'] == '社区搜索暂时不可用，保留上次结果，请稍后重试。'
    assert result['error_code'] == code and 'DO_NOT_EXPOSE' not in str(result)
    assert service.cached(query)['error_code'] == code
    assert service.cached_by_id('1311')['error_code'] == code


@respx.mock
async def test_extraction_failure_code_is_stored_but_not_shown_as_text(tmp_path):
    from game_assistant.wuwa_guide_extract import POST_URL
    respx.post(SEARCH_URL).respond(200,json={'code':200,'data':{'postList':[post()],'hasNext':False}})
    respx.post(POST_URL).respond(429,text='DO_NOT_EXPOSE')
    service = GuideUpdates(tmp_path/'guides.db')
    query = Search(character_id='1311',name='心',attribute='导电')
    result = await service.check(query, extract='changed')
    assert result['extracted'] and result['extraction_error'] == '原帖提炼失败，保留上次培养建议，请稍后重试。'
    assert service.extractor.active(query)['error_code'] == 'http:429'
    assert 'DO_NOT_EXPOSE' not in str(result)


def test_cached_falls_back_to_the_same_character_id(tmp_path):
    service = GuideUpdates(tmp_path / 'guides.db', auto_extract=False)
    def row(name, attribute, checked, candidates=()):
        return {'character_id': '1311', 'name': name, 'attribute': attribute, 'candidates': list(candidates),
                'checked_at': checked, 'attempted_at': checked, 'error': None, 'limited': False}
    web = Search(character_id='1311', name='心', attribute='导电')
    job = Search(character_id='1311', name='心', attribute='')
    assert service.cached_by_id('1311') is None and service.cached_by_id('1/') is None
    assert service.cached(web)['checked_at'] is None and service.cached(web)['error_code'] is None
    service.save(job, row('心', '', '2026-10-20T00:00:00+00:00', [{'id': '1', 'kind': 'article'}]))
    service.extractor.save(job, {'guide': {'sourceId': '1', 'sections': []}, 'error': None, 'error_code': None})
    fallback = service.cached(web)
    assert fallback['candidates'][0]['id'] == '1' and fallback['active_guide']['sourceId'] == '1'
    assert fallback['error_code'] is None
    by_id = service.cached_by_id('1311')
    assert set(by_id) >= {'character_id', 'name', 'attribute', 'candidates', 'checked_at', 'attempted_at', 'error',
                          'error_code', 'limited', 'active_guide', 'extraction_error'}
    # The newest check wins whichever spelling wrote it; an older exact key does not hide it.
    service.save(web, row('心', '导电', '2026-10-19T00:00:00+00:00'))
    assert service.cached(web)['candidates'][0]['id'] == '1' and service.cached_by_id('1311')['attribute'] == ''
    service.save(web, row('心', '导电', '2026-10-21T00:00:00+00:00'))
    assert service.cached(web)['candidates'] == [] and service.cached_by_id('1311')['attribute'] == '导电'
    # The page's key has no extraction of its own: the job's extraction for the same id is shown.
    assert service.cached(web)['active_guide']['sourceId'] == '1'
    reviewed = [{'key': 'weapons', 'status': 'reviewed'}]
    service.extractor.save(Search(character_id='1311', name='心', attribute='衍射'),
                           {'guide': {'sourceId': '2', 'sections': reviewed, 'fetchedAt': '2026-10-01'}, 'error': None})
    other = Search(character_id='1311', name='心', attribute='湮灭')
    assert service.active_for(other.key, '1311')['guide']['sourceId'] == '2'  # fully reviewed first, then newest
    assert service.cached_by_id('13') is None  # an id prefix is not the same character


async def test_local_routes_report_an_idle_background(tmp_path):
    from game_assistant.api import create_app
    from game_assistant.config import Settings
    settings = Settings(db_path=str(tmp_path / 'app.db'), auth_store_path=str(tmp_path / 'auth.json'),
                        auth_allowed_origins=['http://testserver'], bilibili_sources={})
    app = create_app(settings=settings, start_scheduler=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        data = (await client.get('/api/wuwa/guides/updates', params={'character_id': '1311', 'name': '心'})).json()
    assert data['background'] == {'running': False, 'last_run_at': None}
