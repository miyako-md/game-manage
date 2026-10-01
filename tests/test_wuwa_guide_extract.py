import pytest
import respx

from game_assistant.wuwa_guide_updates import Search
from game_assistant.wuwa_guide_extract import GuideExtractor, SourceError, parse_source, extract_sections, source_fingerprint, safe_image, POST_URL

QUERY = Search(character_id='1311', name='心', attribute='导电')
POST_ID = '1555005846752059392'
IMAGE = 'https://prod-alicdn-community.kurobbs.com/forum/page.png'


def raw(title='鸣潮角色 | V3.7心培养攻略一图流', body=None):
    return {'code':200,'data':{'postDetail':{'id':POST_ID,'postTitle':title,'gameId':3,'postType':1,
            'postUserId':'author','userName':'作者','createTimestamp':'1790783884000',
            'postContent':body if body is not None else [
                {'contentType':1,'content':'心武器首选玉阙玄华。同奏模态可用常驻五星。'},
                {'contentType':1,'content':'声骸选择衔梦照世之心5件套。同奏COST3一攻一属，电磁COST3双攻。'},
                {'contentType':1,'content':'配队：心／导电漂泊者／穗穗。锁暝尚未上线，配队为猜测。'},
                {'contentType':1,'content':'游戏内UID：123456789'},
                {'contentType':2,'url':IMAGE}]}}}


def test_source_requires_identity_full_content_and_exact_character_form():
    source = parse_source(raw(), POST_ID, QUERY)
    assert len(source['paragraphs']) == 3 and len(source['images']) == 1
    assert '123456789' not in str(source)
    wrong = raw('鉴心培养攻略')
    with pytest.raises(SourceError): parse_source(wrong, POST_ID, QUERY)
    wrong = raw(); wrong['data']['postDetail']['id'] = '1'
    with pytest.raises(SourceError): parse_source(wrong, POST_ID, QUERY)
    wrong = raw(); wrong['data']['postDetail']['postContent'] = []
    with pytest.raises(SourceError): parse_source(wrong, POST_ID, QUERY)


def test_five_sections_keep_modal_conditions_and_do_not_invent_skill_order():
    source = parse_source(raw(), POST_ID, QUERY)
    sections = {s['key']:s for s in extract_sections(source, [], '未安装图文识别组件')}
    assert set(sections) == {'weapons','teams','echo_sets','echo_stats','skill_priority'}
    assert '同奏' in sections['weapons']['text']
    assert '电磁' in sections['echo_stats']['text'] and '猜测' in sections['teams']['text']
    assert sections['skill_priority']['status'] == 'pending' and sections['skill_priority']['text'] == ''
    assert all(s['status'] != 'reviewed' for s in sections.values())


def test_ocr_keeps_page_and_coordinates_without_guessing_icon_priority():
    source = parse_source(raw(), POST_ID, QUERY)
    page = {'page':1,'lines':[
        {'text':'技能升级优先级','confidence':.99,'box':[[0,100],[100,100],[100,120],[0,120]]},
        {'text':'共鸣回路','confidence':.99,'box':[[0,200],[100,200],[100,220],[0,220]]},
        {'text':'共鸣解放','confidence':.99,'box':[[150,200],[250,200],[250,220],[150,220]]},
        {'text':'共鸣技能','confidence':.3,'box':[[300,200],[400,200],[400,220],[300,220]]}]}
    skill = extract_sections(source, [page], None)[4]
    assert skill['status'] == 'extracted'
    assert '共鸣回路' in skill['text'] and '共鸣解放' in skill['text']
    assert '＞' not in skill['text'] and '共鸣技能' not in skill['text']
    assert skill['evidence'][0]['page'] == 1
    assert '未确认' in skill['note']


def test_image_allowlist_and_source_fingerprint_cover_body_and_image_bytes():
    assert safe_image(IMAGE)
    for url in ('http://127.0.0.1/a.png','https://evil.invalid/a.png',
                'https://user:pass@prod-alicdn-community.kurobbs.com/a.png',
                'https://prod-alicdn-community.kurobbs.com:444/a.png'):
        assert safe_image(url) is None
    source = parse_source(raw(), POST_ID, QUERY)
    first = source_fingerprint(source, ['hash1'])
    assert first != source_fingerprint(source, ['hash2'])
    source['paragraphs'][0]['text'] += ' 修改'
    assert first != source_fingerprint(source, ['hash1'])


@respx.mock
async def test_extraction_is_anonymous_cached_and_preserves_last_good_on_failure(tmp_path):
    source = respx.post(POST_URL).respond(200,json=raw(body=[{'contentType':1,'content':'武器推荐：玉阙玄华。'}]))
    extractor = GuideExtractor(tmp_path / 'guides.db')
    first = await extractor.extract(QUERY, POST_ID)
    assert first['guide']['sections'][0]['text'] and first['guide']['id'] == '1311'
    assert 'token' not in source.calls[0].request.headers
    assert (await extractor.extract(QUERY,POST_ID))['guide'] == first['guide']
    assert source.call_count == 1
    restarted = GuideExtractor(tmp_path / 'guides.db')
    assert restarted.active(QUERY)['guide'] == first['guide']
    source.respond(503,text='DO_NOT_EXPOSE')
    restarted.attempts.clear()
    failed = await restarted.extract(QUERY,POST_ID,force=True)
    assert failed['error'] and failed['guide'] == first['guide']
    assert failed['guide']['fetchedAt'] == first['guide']['fetchedAt']
    assert 'DO_NOT_EXPOSE' not in str(failed)


@respx.mock
async def test_changed_source_never_reuses_reviewed_summary(tmp_path):
    source = parse_source(raw(body=[{'contentType':1,'content':'武器推荐：玉阙玄华。'}]),POST_ID,QUERY)
    fingerprint = source_fingerprint(source, [])
    reviewed = {'character_id':'1311','fingerprint':fingerprint,'reviewedAt':'2026-10-01',
                'sections':[{'key':'weapons','text':'已核对的玉阙玄华','locator':'正文','note':''}]}
    route = respx.post(POST_URL).respond(200,json=raw(body=[{'contentType':1,'content':'武器推荐：玉阙玄华。'}]))
    service = GuideExtractor(tmp_path / 'guides.db', reviewed={POST_ID:reviewed})
    first = await service.extract(QUERY,POST_ID)
    assert first['guide']['sections'][0]['status'] == 'reviewed'
    service.attempts.clear()
    route.respond(200,json=raw(body=[{'contentType':1,'content':'武器推荐：其他武器。'}]))
    changed = await service.extract(QUERY,POST_ID,force=True)
    assert changed['guide']['sections'][0]['status'] == 'extracted'
    assert '已核对的' not in changed['guide']['sections'][0]['text']
