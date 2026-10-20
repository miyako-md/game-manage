"""Six-star coverage and fair bounded cards from credential-free synthetic data."""
from copy import deepcopy

import pytest

from game_assistant.accounts.models import QueryResult
from game_assistant.endfield_gacha import _pool_summary
from game_assistant.endfield_reports import build_gacha_report
from game_assistant.qq.cards import card_to_text
from game_assistant.qq.endfield_presentation import gacha_document, operator_document
from game_assistant.qq.presentation import long_document
from tests.test_qq_endfield_reports import snapshot, synthetic_account
from tests.test_qq_unified_queries import CachedQuery, IDENTITY, service, no_external_network


def stress_gacha(count=6, history_count=50):
    pools=[]
    for index in range(count):
        pools.append(dict(key=f'pool_{index}',label=f'合成卡池{index+1:02}',kind='character',
            total=3000,six_star=60,five_star=300,four_star=2639,unknown_rarity=1,free=0,
            gaps=index%2,pending=bool(index%2),since_last_six={'count':index,'status':'lower_bound' if index%2 else 'exact'},
            oldest_at=1791331200000,newest_at=1791950400000,last_sync_at=f'2026-10-14T{index%24:02}:00:00Z',
            history_limit=50,history=[dict(name='佩丽卡' if item%2 else '祀',pool_name='合成轮换'+str(index+1),
                pulls=50+item,status='lower_bound' if item%3==0 else 'exact',obtained_at=1791950400000-item*3600000)
                for item in range(history_count)]))
    return {'schema_version':1,'role_id':'synthetic-only','total':count*3000,'complete':False,'pools':pools}


def test_generated_pool_distinguishes_unknown_rarity_and_reports_recent_fifty_of_sixty_five():
    rows=[{'seq_id':i,'rarity':6,'is_free':False,'name':'合成干员','gacha_ts':1791950400000+i} for i in range(65)]
    rows += [{'seq_id':65+i,'rarity':rarity,'is_free':False,'gacha_ts':None} for i,rarity in enumerate([4,4,5,None,3])]
    pool=_pool_summary('special','character','特许',None,rows,{}).model_dump()
    assert (pool['four_star'],pool['unknown_rarity'],pool['six_star'])==(2,2,65)
    assert (pool['history_total'],pool['history_available'],pool['history_limit'],pool['history_truncated'])==(65,50,50,True)
    assert len(pool['history'])==50 and pool['history'][0]['obtained_at']==1791950400064


def test_old_snapshots_keep_unknown_rarity_and_unknown_limit_without_losing_zero():
    data=stress_gacha(1);pool=data['pools'][0]
    for key in ('four_star','unknown_rarity','history_limit'):pool.pop(key)
    before=deepcopy(data);report=build_gacha_report(data);result=report['pools'][0]
    assert result['four_star'] is result['unknown_rarity'] is result['history_limit'] is None
    assert (result['history_total'],result['history_available'],result['history_truncated'])==(60,50,True)
    assert data==before and report['four_star'] is report['unknown_rarity'] is None
    empty=build_gacha_report({'total':0,'pools':[{'total':0,'six_star':0,'history':[]}]})['pools'][0]
    assert empty['history_total']==empty['history_available']==0 and empty['history_truncated'] is False
    unknown=build_gacha_report({'pools':[{'history':[]}]})['pools'][0]
    assert unknown['history_total'] is unknown['history_truncated'] is None


def _coverage(card):
    stats=next(section['rows'] for section in card['sections'] if section.get('category')=='ef_gacha_pools')
    detail={section['title'].removesuffix(' · 最近 6 星'):len(section['rows']) for section in card['sections'] if section.get('category')=='ef_gacha_pool'}
    for row in stats:
        coverage=next(field['value'] for field in row['fields'] if field['label']=='6 星覆盖')
        assert coverage.startswith('本图 '+str(detail.get(row['title'],0))+' / 报告 50 / 账本 60')
        assert len(row['fields'])==8
    return stats,detail


def test_single_pool_preserves_all_report_history_and_states_earlier_omission():
    card=long_document(gacha_document(snapshot(stress_gacha(1))))
    stats,detail=_coverage(card)
    assert list(detail.values())==[50]
    assert '报告上限 50' in stats[0]['fields'][-1]['value'] and '有省略' in stats[0]['fields'][-1]['value']
    assert any('完整逐抽' in notice for notice in card['notices'])
    assert '合成轮换1' in str(card) and '其他或未知 1' in str(card)


def test_six_pool_long_card_keeps_every_stat_and_fair_counts():
    query=CachedQuery();query.add('endfield','hypergryph','hg',{'gacha':stress_gacha()})
    context={};service(query).query(IDENTITY,'gacha','endfield',image_context=context)
    card=context['card'];stats,detail=_coverage(card)
    assert len(stats)==6 and len(set(detail.values()))==1 and 0<min(detail.values())<50
    text=card_to_text(card)
    for index in range(6):
        assert f'合成卡池{index+1:02}' in text and f'2026-10-14 {index+8:02}:00' in text
    assert len(text)<=1800 and '逐条明细见图片或网站' in text
    assert query.refreshes==[]


def test_too_many_pools_keep_complete_stats_for_declared_subset_and_label_omission():
    card=long_document(gacha_document(snapshot(stress_gacha(30))))
    stats,detail=_coverage(card)
    assert len(stats)==16 and all(len(row['fields'])==8 for row in stats)
    assert any('卡池 16 / 30' in notice for notice in card['notices'])
    text=card_to_text(card)
    assert len(text)<=1800 and '文字统计 ' in text and '其余卡池' in text


@pytest.mark.parametrize('state',['error','never','ok'])
def test_ledger_success_time_does_not_replace_latest_cached_source_status(state):
    query=CachedQuery();scope=query.add('endfield','hypergryph','hg',{'gacha':{'total':0}})
    query.data[('hg','gacha')]=QueryResult({'total':0},'2026-10-15T00:00:00Z',state,None)
    api=service(query);data=stress_gacha(1)
    api._ledger_snapshot=lambda *args:QueryResult(data,'2026-10-14T00:00:00Z','ok',False)
    context={};api.query(IDENTITY,'gacha','endfield',image_context=context)
    assert context['snapshots'][0].state==state and context['snapshots'][0].fetched_at=='2026-10-14T00:00:00Z'
    expected='最近查询成功' if state=='ok' else '同步状态未确认' if state=='never' else '最近查询失败'
    assert expected in str(context['card'])


def test_ledger_without_valid_source_status_is_unknown_and_does_not_request_it():
    query=CachedQuery();query.add('endfield','hypergryph','hg',{'account':{}})
    api=service(query);api._ledger_snapshot=lambda *args:QueryResult(stress_gacha(1),None,'ok',None)
    context={};api.query(IDENTITY,'gacha','endfield',image_context=context)
    assert context['snapshots'][0].state=='unknown' and query.reads==query.refreshes==[]
    assert '同步状态未确认' in str(context['card'])


def test_operator_skill_mastery_zero_is_visible_and_missing_stays_absent():
    account=synthetic_account();account['operators'][0]['skills'][0]['mastery']=0
    card=operator_document(snapshot(account),'陈千语')
    skills=next(section['rows'] for section in card['sections'] if section.get('category')=='ef_skills')
    assert any(field['label']=='专精' and field['value']=='0' for field in skills[0]['fields'])
    assert all(field['label']!='专精' for field in skills[1]['fields'])


def test_banner_breakdowns_and_six_star_banner_ids_reach_the_shared_image_view():
    from game_assistant.qq.render_snapshot import game_panel
    rows=[{'seq_id':i,'rarity':6 if i in (3,8) else 4,'is_free':False,'name':f'合成{i}','pool_id':'s2' if i>5 else 's1',
           'pool_name':'晨星' if i>5 else '冬猎','gacha_ts':1791950400000+i} for i in range(1,11)]
    pool=_pool_summary('special','character','特许',None,rows,{}).model_dump(mode='json')
    errors=[{'key':'weapon:w1','label':'熔铸申领','message':'接口错误 code=1001'}]
    data=game_panel('endfield','hypergryph','gacha',QueryResult({'schema_version':1,'role_id':'r','pools':[pool],'errors':errors},'2026-10-14T08:00:00+00:00','ok',None))['snapshot']['payload']
    projected=data['pools'][0]
    assert [(b['pool_id'],b['name'],b['total'],b['six_star'],b['four_star']) for b in projected['banners']]==[('s2','晨星',5,1,4),('s1','冬猎',5,1,4)]
    assert [(h['name'],h['pool_id']) for h in projected['history']]==[('合成8','s2'),('合成3','s1')]
    assert data['errors']==errors


def test_weapon_rewards_and_unverified_history_are_preserved_in_image_and_text_notices():
    from game_assistant.qq.render_snapshot import game_panel
    from game_assistant.qq.endfield_presentation import gacha_document
    payload=stress_gacha(1)
    payload['pools'][0].update(kind='weapon',gifts=1,unverified_records=10)
    row=QueryResult(payload,'2026-10-20T07:00:00+00:00','ok',None)
    projected=game_panel('endfield','hypergryph','gacha',row)['snapshot']['payload']['pools'][0]
    assert (projected['gifts'],projected['unverified_records'])==(1,10)
    card=gacha_document(row)
    assert any('1 条额外奖励' in notice for notice in card['notices'])
    assert any('10 条旧武器记录' in notice for notice in card['notices'])
