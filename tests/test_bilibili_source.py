from datetime import datetime, timezone

import pytest

from game_assistant.sources.bilibili import classify_dynamic, collect_pages, SourceError, opus_text

NOW = datetime(2026, 9, 15, tzinfo=timezone.utc)
UID = '3546636978489848'

def post(text, id='1', kind='DYNAMIC_TYPE_DRAW', published=1789401600, pinned=False):
    return {'id_str': id, 'type': kind, 'modules': {
        'module_author': {'mid': int(UID), 'name': '异环', 'pub_ts': published},
        'module_tag': {'text': '置顶' if pinned else ''},
        'module_dynamic': {'major': {'type': 'MAJOR_TYPE_OPUS', 'opus': {'title': '', 'summary': {'text': text}, 'pics': []}}},
    }}

@pytest.mark.parametrize('text', [
    '「逐光破浪」版本更新公告\n维护时间：2026年8月13日06:00—11:00。',
    '「环期赠礼」限时签到活动\n活动时间：8月13日更新后至9月24日05:59。',
    '「逐光破浪」限定盲盒开启通知\n开放时间：08/13 10:00至09/24 05:59。',
])
def test_accepts_dated_ingame_notices(text):
    r = classify_dynamic(post(text), UID, NOW)
    assert r['decision'] == 'accepted'
    assert r['time_evidence'] and r['source_uid'] == UID and r['body'] == text

def test_bilibili_string_timestamp_is_parsed_as_seconds():
    item = post('9月15日活动开启公告', published='1789401600')
    assert classify_dynamic(item, UID, NOW)['decision'] == 'accepted'


@pytest.mark.parametrize('published,text,expected', [
    ('2026-12-28T04:00:00+00:00', '1月7日06:00活动开启', '2027-01-07 06:00'),
    ('2027-01-02T04:00:00+00:00', '12月30日活动开启', '2026-12-30'),
    ('2027-12-28T04:00:00+00:00', '2月29日活动开启', '2028-02-29'),
    ('2026-12-28T04:00:00+00:00', '2026年1月7日活动开启', '2026-01-07'),
])
def test_notice_year_inference_preserves_cross_year_leap_and_explicit_dates(published, text, expected):
    stamp = datetime.fromisoformat(published).timestamp()
    result = classify_dynamic(post(text, published=stamp), UID, NOW)
    assert result['time_evidence'][0]['date'] == expected

@pytest.mark.parametrize('text,kind,reason', [
    ('9月15日版本活动公告', 'DYNAMIC_TYPE_AV', 'video'),
    ('9月15日版本PV正式发布', 'DYNAMIC_TYPE_DRAW', 'promotion'),
    ('9月15日角色EP发布', 'DYNAMIC_TYPE_DRAW', 'promotion'),
    ('9月15日限时时装展示', 'DYNAMIC_TYPE_DRAW', 'promotion'),
    ('9月15日新版本实机演示', 'DYNAMIC_TYPE_DRAW', 'promotion'),
    ('9月15日活动，转发参与抽奖', 'DYNAMIC_TYPE_DRAW', 'lottery'),
    ('限时活动将于版本更新后开启，敬请期待', 'DYNAMIC_TYPE_DRAW', 'no_date'),
    ('9月15日社区同人征集活动', 'DYNAMIC_TYPE_DRAW', 'promotion'),
    ('《异环》1.3版本创作激励计划开启！\n活动截止时间9月23日23:59', 'DYNAMIC_TYPE_DRAW', 'promotion'),
    ('《异环》X 2026ChinaJoy参展情报公开！\n活动时间2026年7月31日', 'DYNAMIC_TYPE_DRAW', 'promotion'),
    ('9月15日天气晴，大家好', 'DYNAMIC_TYPE_DRAW', 'not_ingame'),
    ('活动时间2月30日正式开启', 'DYNAMIC_TYPE_DRAW', 'no_date'),
    ('1.3版本更新公告，敬请期待', 'DYNAMIC_TYPE_DRAW', 'no_date'),
    ('《异环》1.4版本前瞻特别节目丨开播预告\n9月16日直播预约', 'DYNAMIC_TYPE_DRAW', 'promotion'),
    ('《异环》1.4版本前瞻特别节目丨开播预告\n前瞻特别节目将于2026年9月16日19:30正式开播，欢迎前来观看。\n官方直播间地址', 'DYNAMIC_TYPE_DRAW', 'promotion'),
    ('最新消息\n9月16日版本PV发布活动', 'DYNAMIC_TYPE_DRAW', 'promotion'),
    ('“万念证心，一剑清平。”\n角色故事介绍\n——————————————————\n3.6版本将于8月20日开启', 'DYNAMIC_TYPE_DRAW', 'not_ingame'),
    ('「启程！鸣潮巡游巴士」广州站\n9月13日活动开启', 'DYNAMIC_TYPE_DRAW', 'promotion'),
    # Official character/operator intel is news, never calendar input; it wins over promotion words.
    ('后勤备忘 - 独家揭秘! | 祀\n9月15日版本活动', 'DYNAMIC_TYPE_DRAW', 'intel'),
    ('//危境情报//祀//\n版本更新后开启', 'DYNAMIC_TYPE_DRAW', 'intel'),
    ('#异环# 角色档案 | 某角色\n9月15日版本PV', 'DYNAMIC_TYPE_DRAW', 'intel'),
    ('干员情报 | 某干员', 'DYNAMIC_TYPE_DRAW', 'intel'),
    ('后勤备忘 | 某干员\n9月15日活动，转发参与抽奖', 'DYNAMIC_TYPE_DRAW', 'lottery'),
    ('后勤备忘 | 某干员', 'DYNAMIC_TYPE_AV', 'video'),
    ('#鸣潮# #鸣潮3.7版本#\n《鸣潮》3.7版本近期活动汇总\n多项活动正在进行中', 'DYNAMIC_TYPE_DRAW', 'no_date'),
    ('✦ 故影同行✦\n《鸣潮》3.7版本剧情图文', 'DYNAMIC_TYPE_DRAW', 'no_date'),
])
def test_excludes_non_notice_content(text, kind, reason):
    r = classify_dynamic(post(text, kind=kind), UID, NOW)
    assert r['decision'] == 'excluded' and r['reason'] == reason

def test_forwarded_video_and_wrong_author_fail_closed():
    item = post('9月15日活动通知', kind='DYNAMIC_TYPE_FORWARD')
    item['orig'] = post('9月15日更新演示', kind='DYNAMIC_TYPE_AV')
    assert classify_dynamic(item, UID, NOW)['reason'] == 'video'
    item = post('9月15日活动通知')
    item['modules']['module_author']['mid'] = 123
    with pytest.raises(SourceError): classify_dynamic(item, UID, NOW)

async def test_pagination_collects_all_new_posts_ignoring_old_pin_and_deduplicates():
    pages = {
        '': {'items': [post('旧置顶', '99', published=1, pinned=True), post('9月15日活动', '2')], 'has_more': True, 'offset': 'next'},
        'next': {'items': [post('9月15日活动', '2'), post('9月14日活动', '3')], 'has_more': False},
    }
    async def fetch(offset): return pages[offset]
    result = await collect_pages(fetch, UID, NOW, pause=0)
    assert result['complete'] and result['pages'] == 2
    assert [r['id'] for r in result['rows']] == ['2', '3']

async def test_empty_first_page_and_repeated_cursor_do_not_claim_success():
    async def empty(offset): return {'items': [], 'has_more': False}
    with pytest.raises(SourceError): await collect_pages(empty, UID, NOW, pause=0)
    async def repeat(offset): return {'items': [post('9月15日活动')], 'has_more': True, 'offset': 'same'}
    with pytest.raises(SourceError): await collect_pages(repeat, UID, NOW, pause=0)

async def test_empty_following_page_does_not_prove_sixty_day_coverage():
    async def fetch(offset): return {'items': [] if offset else [post('9月15日活动')], 'has_more': not bool(offset), 'offset':'next'}
    with pytest.raises(SourceError): await collect_pages(fetch, UID, NOW, pause=0)

def test_opus_full_text_verifies_identity_and_replaces_truncated_summary():
    raw = {'item': {'id_str':'1','basic':{'uid':UID},'modules':[
        {'module_type':'MODULE_TYPE_TITLE','module_title':{'text':'维护公告'}},
        {'module_type':'MODULE_TYPE_CONTENT','module_content':{'paragraphs':[{'para_type':1,'text':{'nodes':[{'word':{'words':'9月3日06:00停服维护'}}]}}]}}
    ]}}
    assert '9月3日06:00停服维护' in opus_text(raw, UID, '1')
    with pytest.raises(SourceError): opus_text(raw, '999', '1')


def test_official_cdn_http_picture_is_upgraded_without_admitting_arbitrary_http():
    value=post('9月15日版本更新公告')
    value['modules']['module_dynamic']['major']['opus']['pics']=[
        {'url':'http://i0.hdslb.com/bfs/new_dyn/verified.jpg'},
        {'url':'http://unverified.example/picture.jpg'}, {'url':'javascript:bad'},
        {'url':'//i0.hdslb.com/bfs/new_dyn/verified.jpg'}]
    assert classify_dynamic(value,UID,NOW)['images']==['https://i0.hdslb.com/bfs/new_dyn/verified.jpg']


@pytest.mark.parametrize('text,reason', [
    ('#鸣潮# #鸣潮3.7版本#\n《鸣潮》3.7版本近期活动汇总\n多项活动正在进行中', 'no_date'),
    ('✦ 故影同行✦\n《鸣潮》3.7版本剧情图文', 'no_date'),
    ('后勤备忘 - 独家揭秘! | 祀\n9月15日版本活动', 'intel'),
    ('//危境情报//祀//\n版本更新后开启', 'intel'),
])
def test_dateless_posts_and_intel_are_news_but_never_calendar_input(text, reason):
    from game_assistant.sources.public_content import calendar_from_posts, visible_article
    row = classify_dynamic(post(text), UID, NOW)
    assert (row['decision'], row['reason']) == ('excluded', reason)
    assert visible_article(row)
    for game in ('wuthering_waves', 'nte', 'endfield'):
        assert calendar_from_posts([row], game, now=NOW)['events'] == []


@pytest.mark.parametrize('reason', ['video', 'incomplete', 'unsupported'])
def test_video_incomplete_and_unsupported_posts_stay_out_of_news(reason):
    from game_assistant.sources.public_content import visible_article
    assert not visible_article({'decision': 'excluded', 'reason': reason, 'body': '网页活动开启'})
    assert not visible_article({'decision': 'excluded', 'reason': 'no_date', 'body': ''})
