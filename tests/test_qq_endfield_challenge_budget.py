"""Long cached challenge reports retain all independently timed categories."""
from copy import deepcopy

import pytest

from game_assistant.endfield_challenges import build_challenge_report
from game_assistant.qq.cards import card_to_text
from game_assistant.qq.endfield_presentation import challenge_document
from game_assistant.qq.presentation import long_document
from tests.test_qq_endfield_challenges import setup, synthetic_challenges
from tests.test_qq_unified_queries import IDENTITY, service, no_external_network


def stress_challenges(*, all_categories=False):
    values=synthetic_challenges()
    season=values['war']['records'][0]
    week=deepcopy(season['weeks'][0])
    season['weeks']=[{**deepcopy(week),'id':f'w{i}','name':f'第 {i+1} 周'} for i in range(40)]
    if all_categories:
        record=values['monument']['records'][0]
        values['monument']['records']=[{**deepcopy(record),'id':f'm{i}','name':f'合成丰碑 {i+1}'} for i in range(40)]
        values['crisis']['records']=[{'id':f'r{i}','name':f'合成危机 {i+1}','score':i,'isPass':False} for i in range(40)]
    return values


def query_card(tmp_path, values):
    query,scope,grant=setup(values=deepcopy(values))
    context={};reply=service(query).query(IDENTITY,'combat','endfield',image_context=context)
    assert query.refreshes==[] and query.reads==[(scope,'combat')]
    return context['card'],reply['text']


def coverage(card):
    result={}
    for section in card['sections'][:3]:
        assert section['category']=='ef_challenge'
        result[section['title'].split(' · ')[0]]={
            item['label'].split('（')[0]:item['value'] for item in section['fields'] if '本图 / 已观测' in item['label']}
    return result


def assert_final_coverage(card):
    actual={'战争':{'赛季':0,'周次':0,'关卡组':0,'荣誉':0},'丰碑':{'记录':0,'关卡组':0},'危机':{'记录':0}}
    for section in card['sections'][3:]:
        fields={item['label']:item['value'] for item in section['fields']}
        if section['category']=='ef_war':
            actual['战争']['赛季']+=int('赛季星数' in fields)
            actual['战争']['周次']+=int('周星数' in fields)
            actual['战争']['荣誉' if '已观测荣誉' in section['title'] else '关卡组']+=len(section['rows'])
        elif section['category']=='ef_monument':
            actual['丰碑']['记录']+=int('开始时间' in fields)
            actual['丰碑']['关卡组']+=len(section['rows'])
        elif section['category']=='ef_crisis':
            actual['危机']['记录']+=int('通关状态' in fields)
    for label,counts in coverage(card).items():
        for unit,value in counts.items():
            if value!='未知 / 未采集':assert int(value.split(' / ')[0])==actual[label][unit]
    assert not any('单张长图显示上限' in notice for notice in card['notices'])


def test_normal_report_preserves_every_detail_and_exact_hierarchy_counts(tmp_path):
    values=synthetic_challenges();before=deepcopy(values)
    card,text=query_card(tmp_path,values)
    assert values==before
    assert coverage(card)=={'战争':{'赛季':'1 / 1','周次':'1 / 1','关卡组':'1 / 1','荣誉':'1 / 1'},
                           '丰碑':{'记录':'1 / 1','关卡组':'1 / 1'},'危机':{'记录':'2 / 2'}}
    assert_final_coverage(card)
    assert '省略' not in text and '首次通关：未知' in text and '记录结果：0' in text


def test_forty_war_weeks_keep_later_categories_and_times(tmp_path):
    card,text=query_card(tmp_path,stress_challenges())
    counts=coverage(card)
    shown,total=map(int,counts['战争']['周次'].split(' / '))
    assert 0<shown<total==40
    assert counts['战争']['荣誉']=='0 / 1'
    assert counts['丰碑']['记录']=='1 / 1' and counts['危机']['记录']=='2 / 2'
    assert '超限部分已省略' in text and len(text)<=1800 and '三类状态优先' in text
    for moment in ('09:30','10:30','11:30'):assert '2026-10-14 '+moment in text
    assert '最近读取失败，显示旧观测' in text and '最高值：0' in text and '挑战次数：未知' in text
    assert_final_coverage(card)


def test_three_large_categories_receive_details_without_losing_summary_fields(tmp_path):
    card,text=query_card(tmp_path,stress_challenges(all_categories=True))
    for label,unit in (('战争','周次'),('丰碑','记录'),('危机','记录')):
        shown,total=map(int,coverage(card)[label][unit].split(' / '))
        assert 0<shown<total==40
        assert label+' · 缓存状态' in text
    assert_final_coverage(card)
    assert long_document(card)==card


def test_large_single_group_list_splits_without_counting_record_twice(tmp_path):
    values=synthetic_challenges();record=values['monument']['records'][0]
    record['groups']=[{**deepcopy(record['groups'][0]),'name':'关卡组 '+str(index+1)} for index in range(100)]
    card,text=query_card(tmp_path,values)
    counts=coverage(card)
    assert counts['丰碑']['记录']=='1 / 1'
    shown,total=map(int,counts['丰碑']['关卡组'].split(' / '))
    assert 0<shown<total==100
    assert counts['危机']['记录']=='2 / 2' and '续 2' in str(card)
    assert_final_coverage(card)


def test_failed_unknown_and_successful_empty_stay_distinct_in_long_fallback():
    values=stress_challenges()
    values['monument'].update(fetched_at=None,stale=True,records=[])
    values['crisis']['records']=[]
    reports=[build_challenge_report(value) for value in values.values()]
    card=long_document(challenge_document(reports));text=card_to_text(card)
    assert coverage(card)['丰碑']=={'记录':'未知 / 未采集','关卡组':'未知 / 未采集'}
    assert coverage(card)['危机']=={'记录':'0 / 0'}
    assert '最近读取失败，尚无成功观测' in text and '本分类抓取时间：未知' in text
    assert '当前快照没有挑战记录' in text
    assert '暂无通关记录' not in text
    assert '最高值：0' in text and '挑战次数：未知' in text
    assert_final_coverage(card)


def test_long_titles_cannot_trigger_normalizer_after_counts_are_calculated():
    values=stress_challenges(all_categories=True)
    for value in values.values():
        for record in value['records']:
            record['name']='合成极长标题'*20
            for week in record.get('weeks',[]):
                week['name']='合成极长周次'*20
                for group in week['groups']:group['name']='合成极长关卡'*20
    raw=challenge_document([build_challenge_report(value) for value in values.values()])
    card=long_document(raw)
    assert len(raw['sections'])==len(card['sections'])
    assert [len(section['rows']) for section in raw['sections']]==[len(section['rows']) for section in card['sections']]
    assert_final_coverage(card)


@pytest.mark.parametrize('value,expected', [
    ({'kind':'war'}, None),
    ({'kind':'war','fetched_at':'2026-10-17T00:00:00Z','supported':False}, None),
    ({'kind':'war','fetched_at':'2026-10-17T00:00:00Z','records':[]}, '当前快照没有挑战记录'),
])
def test_empty_challenge_list_only_describes_available_snapshot(value,expected):
    card=challenge_document([build_challenge_report(value)])
    fields={item['label']:item['value'] for item in card['sections'][0]['fields']}
    assert fields.get('记录说明')==expected
    assert '暂无通关记录' not in card_to_text(card)
