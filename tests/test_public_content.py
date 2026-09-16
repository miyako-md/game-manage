from datetime import datetime, timezone

from game_assistant.sources.public_content import calendar_from_posts, merge_events, merge_news, parse_post_events

NOW = datetime(2026, 9, 16, tzinfo=timezone.utc)

def notice(body, id='1', published='2026-08-12T04:00:00+00:00'):
    return dict(id=id, title=body.splitlines()[0], body=body, decision='accepted',
                published_at=published, fetched_at=NOW.isoformat(), source='bilibili',
                source_name='B站官方动态', url='https://t.bilibili.com/'+id)

def test_wuwa_cross_line_and_relative_start_preserves_date_precision():
    p = notice('3.6版本内容说明\n[签到]七日签到活动\n活动时间\n3.6版本更新后 ~ 2026年9月29日03:59')
    e = parse_post_events(p, 'wuthering_waves', '3.6')[0]
    assert e['start_at'] is None and e['start_text'] == '3.6版本更新后'
    assert e['end_at'] == '2026-09-29T03:59:00+08:00'
    assert e['source_url'] == p['url']

def test_nte_quotes_short_dates_and_pass_are_parsed_but_permanent_is_not():
    p = notice('《异环》1.3版本更新公告\n五、全新盲盒「逐光破浪」上线\n活动时间：8月13日版本更新后-9月24日05:59\n● 「排球之星」限时活动\n活动时间：8月13日版本更新后-9月24日05:59\n● 1.3版本「环期赏令」说明\n开启时间：8月13日版本更新后 - 9月23日23:59\n● 「永久奖励」活动\n活动时间：永久')
    e = parse_post_events(p, 'nte', '1.3')
    assert [x['name'] for x in e] == ['逐光破浪', '排球之星', '环期赏令']
    assert e[0]['start_at'] is None and e[0]['start_date'] == '2026-08-13'
    assert e[0]['end_at'] == '2026-09-24T05:59:00+08:00'

def test_next_version_is_not_selected_and_independent_current_gacha_is_added():
    base=notice('3.6版本内容说明\n更新维护时间：2026年8月20日04:00 ~ 11:00\n[签到]七日签到活动\n活动时间：3.6版本更新后 ~ 2026年9月29日03:59')
    future=notice('3.7版本内容说明\n更新维护时间：2026年9月30日04:00 ~ 11:00\n[新活动]活动\n活动时间：2026年9月30日12:00 ~ 2026年10月10日03:59','2','2026-09-15T00:00:00+00:00')
    card=notice('#鸣潮# #鸣潮3.6版本#\n[身赴三途]角色活动唤取\n活动时间\n2026年9月10日10:00 ~ 2026年9月29日11:59','3','2026-09-09T00:00:00+00:00')
    result=calendar_from_posts([future,card,base], 'wuthering_waves', NOW)
    assert result['version']=='3.6'
    assert {e['name'] for e in result['events']}=={'签到','身赴三途'}

def test_malformed_ranges_and_unrelated_sections_do_not_borrow_dates():
    p=notice('3.6版本内容说明\n[无日期]活动\n[有效]活动\n活动时间：2026年9月1日10:00 ~ 2026年9月2日10:00\n[错误]活动\n活动时间：2026年9月30日10:00 ~ 2026年9月1日10:00')
    assert [e['name'] for e in parse_post_events(p,'wuthering_waves','3.6')]==['有效']

def test_bilibili_wins_conflict_and_manual_midnight_does_not_fill_unknown():
    primary=[dict(name='环期赠礼',version='1.3',start_at=None,start_text='版本更新后',end_at='2026-09-24T05:59:00+08:00',source='bilibili')]
    native=[dict(name='环期赠礼签到',source_title='手动配置',start_at='2026-08-13T00:00:00+08:00',end_at='2026-09-24T05:59:00+08:00')]
    result=merge_events(primary,native,'1.3')
    assert len(result)==1 and result[0]['start_at'] is None
    assert result[0]['supplement_sources']

def test_supplement_only_current_version_and_keep_different_phases():
    p=[dict(name='挑战',version='3.6',start_at='2026-09-01T00:00:00+08:00',end_at='2026-09-07T00:00:00+08:00',source='bilibili')]
    s=[dict(name='挑战',source_title='3.6版本内容说明',start_at='2026-09-08T00:00:00+08:00',end_at='2026-09-15T00:00:00+08:00'),dict(name='旧活动',source_title='3.5版本内容说明')]
    assert len(merge_events(p,s,'3.6'))==2
    assert len(merge_events([],s,None))==2

def test_news_bilibili_first_and_same_title_community_collapsed():
    p=notice('#鸣潮#\n[身赴三途]角色活动唤取\n9月10日活动开启')
    s=[dict(title='[身赴三途]角色活动唤取',url='https://community.example/1'),dict(title='补充公告',url='https://community.example/2')]
    result=merge_news([p],s)
    assert len(result)==2 and result[0]['source']=='bilibili'
    assert result[0]['title']=='[身赴三途]角色活动唤取'
    assert result[1]['source']=='community'

def test_grouped_weapon_and_character_pools_and_nte_aliases():
    p=notice('3.6版本\n「卡池甲」、「卡池乙」角色活动唤取，「武器甲」、「武器乙」武器活动唤取限时开启！\n活动时间：2026年9月10日10:00 ~ 2026年9月29日11:59')
    assert len(parse_post_events(p,'wuthering_waves','3.6'))==4
    p=notice('「独酌胧月流」限定棋盘、「名月特刊」弧盘研募计划即将返场，可获得限定S级角色「浔」和限定S级弧盘「行进于时间之外」！\n开放时间\n2026/9/3 更新维护后~2026/9/24 5:59')
    events=parse_post_events(p,'nte','1.3')
    assert len(events)==2 and events[0]['category']=='角色卡池'
    assert '浔' in events[0]['aliases'] and '行进于时间之外' in events[1]['aliases']

def test_lol_calendar_is_not_changed_by_mobile_source_parser():
    p=notice('3.6版本内容说明\n[活动]战斗活动\n活动时间：2026年9月1日10:00 ~ 2026年9月2日10:00')
    assert calendar_from_posts([p],'league_of_legends',NOW)['events']==[]

def test_current_version_deadline_extension_overrides_original_version_end():
    base=notice('3.6版本内容说明\n[测试]活动\n活动时间：2026年8月20日10:00 ~ 2026年9月29日03:59')
    later=notice('3.6版本活动延期通知\n[测试]活动\n活动时间：2026年8月20日10:00 ~ 2026年9月30日03:59','2','2026-09-15T00:00:00+00:00')
    events=calendar_from_posts([base,later],'wuthering_waves',NOW)['events']
    assert len(events)==1 and events[0]['end_at']=='2026-09-30T03:59:00+08:00'

def test_relative_start_with_date_still_detects_conflicting_community_deadline():
    primary=[dict(name='测试',start_at=None,start_date='2026-08-13',end_at='2026-09-24T05:59:00+08:00',source='bilibili')]
    native=[dict(name='测试',source_title='1.3版本更新公告',start_at='2026-08-13T00:00:00+08:00',end_at='2026-09-25T05:59:00+08:00')]
    rows=merge_events(primary,native,'1.3')
    assert len(rows)==1 and rows[0]['end_at']==primary[0]['end_at'] and rows[0]['source_note']

def test_unknown_or_cross_line_future_maintenance_cannot_promote_new_version():
    base=notice('3.6版本内容说明\n[活动]活动\n活动时间：2026年8月20日10:00 ~ 2026年9月29日03:59')
    for maintenance in ['', '维护时间：2026年9月30日04:00', '更新维护时间\n2026年9月30日04:00']:
        future=notice('3.7版本内容说明\n'+maintenance+'\n[新活动]活动\n活动时间：3.7版本更新后 ~ 2026年10月29日03:59','2','2026-09-15T00:00:00+00:00')
        assert calendar_from_posts([base,future],'wuthering_waves',NOW)['version']=='3.6'

def test_separate_phases_do_not_fill_the_gap_between_them():
    for times in [
        '活动时间：第一期 2026年9月1日04:00 ~ 2026年9月7日03:59；第二期 2026年9月10日04:00 ~ 2026年9月15日03:59',
        '活动时间：2026年9月1日04:00 ~ 2026年9月7日03:59\n活动时间：2026年9月10日04:00 ~ 2026年9月15日03:59',
    ]:
        events=parse_post_events(notice('3.6版本内容说明\n[分期活动]战斗活动\n'+times),'wuthering_waves','3.6')
        assert len(events)==2
        assert events[0]['end_at']=='2026-09-07T03:59:00+08:00'
        assert events[1]['start_at']=='2026-09-10T04:00:00+08:00'
