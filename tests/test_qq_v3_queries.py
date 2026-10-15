from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest

from game_assistant.accounts.models import QueryResult
from game_assistant.identity.models import Principal
from game_assistant.qq.commands import parse_command
from game_assistant.qq.query_routes import QqQueryService
from game_assistant.qq import presentation as view
from tests.test_qq_unified_queries import CachedQuery, IDENTITY, no_external_network

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone(timedelta(hours=8)))

@pytest.mark.parametrize('raw,verb,game', [('活动','events',None),('近期活动','recent_events',None),('日历','calendar',None),('鸣潮 活动','events','wuthering_waves'),('异环近期活动','recent_events','nte')])
def test_activity_commands_are_distinct(raw,verb,game):
    parsed=parse_command(raw)
    assert (parsed.command,parsed.game)==(verb,game)

def event(name,start,end,**extra):
    return dict(name=name,start_at=start,end_at=end,source_name='官方公告',source_title='来源说明',**extra)

def test_recent_168_hour_endpoints_and_uncertain_precision():
    from game_assistant.qq.event_views import event_document
    data=[event('恰好七天后开始',(NOW+timedelta(hours=168)).isoformat(),None),
          event('超过七天',(NOW+timedelta(hours=168,minutes=1)).isoformat(),None),
          event('维护前',None,(NOW+timedelta(hours=2)).isoformat(),end_precision='version_end',end_text='维护前'),
          event('日期项','2026-10-15','2026-10-16',start_precision='day',end_precision='day'),
          event('更新后',None,(NOW+timedelta(days=9)).isoformat(),start_date='2026-10-15',start_precision='relative',start_text='版本更新后'),
          event('明确未知',None,None,start_precision='unknown')]
    card=event_document('recent_events',{'nte':QueryResult(data,NOW.isoformat(),'ok',None)},now=NOW)
    sections={s['title']:s for s in card['sections']}
    assert [r['title'] for r in sections['即将开始']['rows']]==['恰好七天后开始']
    assert [r['title'] for r in sections['即将结束']['rows']]==['维护前']
    assert {r['title'] for r in sections['时间待确认']['rows']}=={'日期项','更新后','明确未知'}
    assert '2小时' in str(sections['即将结束'])
    assert '00:00' not in str(sections['时间待确认'])

def test_current_events_and_month_axis_preserve_phase_gaps():
    from game_assistant.qq.event_views import event_document
    data=[event('跨月','2026-09-29T12:00:00+08:00','2026-11-02T12:00:00+08:00',category='战斗'),
          event('未开始','2026-10-20T12:00:00+08:00','2026-10-23T12:00:00+08:00'),
          event('阶段',None,None,phases=[{'start_at':'2026-10-01T12:00:00+08:00','end_at':'2026-10-03T12:00:00+08:00'},{'start_at':'2026-10-20T12:00:00+08:00','end_at':'2026-10-22T12:00:00+08:00'}])]
    snapshots={'nte':QueryResult(data,NOW.isoformat(),'ok',None)}
    current=event_document('events',snapshots,now=NOW)
    assert [r['title'] for s in current['sections'] if s.get('game') for r in s.get('rows',[])]==['跨月']
    calendar=event_document('calendar',snapshots,now=NOW)
    assert calendar['timeline']=={'start':'2026-10-01','end':'2026-11-01','today':'2026-10-14','timezone':'Asia/Shanghai'}
    rows=[r for s in calendar['sections'] for r in s.get('rows',[])]
    phases=[r for r in rows if r['title'].startswith('阶段')]
    assert len(phases)==2 and phases[0]['timeline']['end'] < phases[1]['timeline']['start']
    cross=next(r for r in rows if r['title']=='跨月')['timeline']
    assert cross['continues_before'] and cross['continues_after']

def test_aggregate_only_authorized_games_deduplicates_and_distinguishes_missing_empty():
    query=CachedQuery();query.add('nte','tajiduo','n1',{});query.add('nte','tajiduo','n2',{});query.add('endfield','skland','sk',{})
    calls=[]
    def read(game,cap):
        calls.append((game,cap));return QueryResult([] if game=='nte' else None,NOW.isoformat(),'ok' if game=='nte' else 'never',None)
    api=QqQueryService(SimpleNamespace(resolve_qq_identity=lambda i:Principal('u',False)),query,SimpleNamespace(read=read),clock=lambda:NOW)
    context={};reply=api.query(IDENTITY,'events',image_context=context)
    assert calls==[('nte','events'),('endfield','events')] and query.reads==[]
    assert '列表为空' in reply['text'] and '暂无成功快照' in reply['text']
    assert len(context['grants'])==2

def test_single_public_game_needs_no_binding_and_unbound_guide_has_no_roundtrip():
    def unbound(identity):
        from game_assistant.qq.bindings import QqBindingError
        raise QqBindingError('qq_link_required',403)
    api=QqQueryService(SimpleNamespace(resolve_qq_identity=unbound),None,SimpleNamespace(read=lambda *args:QueryResult([],None,'ok',None)),clock=lambda:NOW)
    assert '列表为空' in api.query(IDENTITY,'events','nte')['text']
    guide=api.query(IDENTITY,'events')['text']
    assert '绑定' in guide and '填回' not in guide and '邀请' in guide

def test_nte_all_pool_details_source_colors_and_missing_guarantee():
    data={'schema_version':1,'luck_type':1,'luck_title':'社区评价','total_draws':200,'pools':[
        {'name':'角色池','total_draws':100,'s_count':2,'average':50,'guarantee':80,'details':[{'name':'A','pity':20,'lucky_type':1,'obtained_at':'2026-10-14 08:00'},{'name':'B','pity':80,'lucky_type':0}]},
        {'name':'武器池','total_draws':100,'details':[{'name':'C','pity':30,'lucky_type':4}]}]}
    card=view.gacha_document('nte','tajiduo',QueryResult(data,NOW.isoformat(),'ok',None))
    pools=[s for s in card['sections'] if s.get('layout')=='gacha']
    assert [s['title'] for s in pools]==['角色池','武器池']
    assert [r['title'] for s in pools for r in s['rows']]==['A','B','C']
    assert pools[0]['rows'][0]['gacha']['color']=='green'
    assert pools[0]['rows'][1]['gacha']['lucky_text']==''
    assert pools[1]['rows'][0]['gacha']['guarantee'] is None
    assert '未导入' in str(card) and '当前垫抽' in str(card)

def test_help_one_command_each_and_overview_known_equipment():
    card=view.help_document('nte')
    assert all('/' not in f['value'] for s in card['sections'] for f in s.get('fields',[]))
    assert '填回' not in str(card)
    query=CachedQuery();query.add('nte','tajiduo','n',{'account':{'nickname':'玩家','achievement_count':0},'stamina':{'current':5,'maximum':100,'city_current':None,'city_maximum':20,'daily_activity':80},'roles':{'entries':[{'name':'娜娜莉','level':70,'weapon':{'name':'弧盘','level':60}}]}})
    api=QqQueryService(SimpleNamespace(resolve_qq_identity=lambda i:Principal('u',False)),query,None)
    context={};result=api.query(IDENTITY,'overview',image_context=context)
    assert '弧盘' in result['text'] and '都市体力' in result['text'] and '每日活跃' in result['text']
    assert '未知/20' in result['text'] and any(s.get('layout')=='equipment' for s in context['card']['sections'])

def test_nte_imported_ledger_is_queryable_without_community_capability():
    query=CachedQuery();query.add('nte','tajiduo','n',{})
    query.private=SimpleNamespace(ledger=lambda *args:SimpleNamespace(summary=lambda scope:{'total_records':2,'pools':[{'pool_id':'known','total_records':2}]}))
    api=QqQueryService(SimpleNamespace(resolve_qq_identity=lambda i:Principal('u',False)),query,None)
    result=api.query(IDENTITY,'gacha','nte')
    assert '本人逐抽账本' in result['text'] and '2' in result['text'] and '暂无成功快照' in result['text']

def test_other_games_keep_their_own_record_boundary_and_types():
    ww=QueryResult({'total':20,'gold_total':1,'pools':[{'pool':'1','name':'角色精准调谐','total':20,'rarity_distribution':{'5':1}}],
        'gold':[{'pool':'1','name':'今汐','resource_type':'角色','time':'2026-10-14T08:00:00'}],'coverage':{'complete':False}},NOW.isoformat(),'ok',False)
    card=view.gacha_document('wuthering_waves','kuro',ww)
    row=next(s for s in card['sections'] if s['title']=='角色精准调谐')['rows'][0]
    assert next(f for f in row['fields'] if f['label']=='类型')['value']=='角色'
    ef=view.gacha_document('endfield','hypergryph',QueryResult({'total':70,'pools':[{'label':'寻访','total':70,'since_last_six':{'count':12,'status':'lower_bound'},'history':[{'name':'陈千语','pulls':58,'status':'lower_bound'}]}]},NOW.isoformat(),'ok',False))
    assert '至少 12' in str(ef) and '至少 58' in str(ef) and not any('gacha' in r for s in ef['sections'] for r in s.get('rows',[]))

async def test_aggregated_public_render_revalidates_private_grants_and_binding():
    query=CachedQuery();query.add('nte','tajiduo','n',{})
    class Queue:
        renderer=SimpleNamespace(invalidate_account=lambda *args:None)
        async def render(self,*args,**kwargs):query.versions['n']=None;return b'image'
    api=QqQueryService(SimpleNamespace(resolve_qq_identity=lambda i:Principal('u',False)),query,SimpleNamespace(read=lambda *args:QueryResult([],NOW.isoformat(),'ok',None)),clock=lambda:NOW,render_queue=Queue())
    reply=await api.query_reply(IDENTITY,'calendar',image_requested=True,budget_seconds=3)
    assert 'image' not in reply and '变更' in reply['text']

def test_countdown_and_month_axis_change_render_cache_key_without_upstream_refresh():
    from game_assistant.qq.event_views import event_document
    from game_assistant.qq.rendering import SummaryRenderer
    from game_assistant.accounts.models import AccountScope
    snapshots={'nte':QueryResult([event('即将截止',NOW.isoformat(),(NOW+timedelta(hours=2)).isoformat())],NOW.isoformat(),'ok',None)}
    renderer=SummaryRenderer();scope=AccountScope('public','summary','summary')
    a=event_document('recent_events',snapshots,now=NOW);b=event_document('recent_events',snapshots,now=NOW+timedelta(minutes=1))
    assert renderer.cache_key(scope,QueryResult({'card':a},NOW.isoformat(),'ok',None))!=renderer.cache_key(scope,QueryResult({'card':b},NOW.isoformat(),'ok',None))

def test_current_success_snapshot_with_only_future_events_has_explicit_empty_state():
    from game_assistant.qq.event_views import event_document
    card=event_document('events',{'nte':QueryResult([event('未来','2026-10-20T08:00:00+08:00','2026-10-23T08:00:00+08:00')],NOW.isoformat(),'ok',None)},now=NOW)
    assert '无已确认正在进行的活动' in str(card)

def test_overview_equipment_refs_and_top_source_tone_use_real_cached_fields():
    cache=SimpleNamespace(ref_for=lambda *args:'qqasset_'+'a'*64,register_url=lambda url:'qqasset_'+'b'*64)
    sections=view.overview_roles('nte','tajiduo',QueryResult({'entries':[{'name':'娜娜莉','level':70,'weapon':{'name':'弧盘','level':60}}]},NOW.isoformat(),'ok',None),cache)
    equipment=sections[0]['rows'][0]['equipment']
    assert equipment[0]['title']=='弧盘' and equipment[0]['subtitle']=='等级 60' and equipment[0]['image'].startswith('qqasset_')
    card=view.gacha_document('nte','tajiduo',QueryResult({'schema_version':1,'luck_type':7,'luck_title':'社区评价','pools':[]},NOW.isoformat(),'ok',None))
    assert card['sections'][0]['tone']=='yellow'

def test_overview_wuwa_embeds_observed_weapon_echoes_not_basic_weapon_type():
    snapshot=QueryResult([{'role_id':1101,'name':'今汐','weapon':'长刃','level':80}],NOW.isoformat(),'ok',None)
    details={'1101':{'weapon_data':{'level':90,'weapon':{'weapon_name':'时和岁稔'}},'phantom_data':{'equip_phantom_list':[{'level':25,'phantom_prop':{'name':'角'}}]}}}
    sections=view.overview_roles('wuthering_waves','kuro',snapshot,details=details)
    equipment=sections[0]['rows'][0]['equipment']
    assert [item['title'] for item in equipment]==['时和岁稔','角']
    assert '长刃' not in str(equipment)

def test_current_unknown_start_does_not_include_confirmed_ended_events():
    from game_assistant.qq.event_views import event_document
    card=event_document('events',{'nte':QueryResult([event('已结束',None,'2026-10-10T08:00:00+08:00',start_text='版本更新后',start_precision='relative'),event('开放未知',None,'2026-10-19T08:00:00+08:00',start_text='版本更新后',start_precision='relative')],NOW.isoformat(),'ok',None)},now=NOW)
    titles=[r['title'] for s in card['sections'] if s['title']=='时间待确认' for r in s['rows']]
    assert titles==['开放未知']

def test_reversed_day_range_is_uncertain_without_invalid_timeline():
    from game_assistant.qq.event_views import event_document
    card=event_document('calendar',{'nte':QueryResult([event('错误日期','2026-10-20','2026-10-10',start_precision='day',end_precision='day')],NOW.isoformat(),'ok',None)},now=NOW)
    pending=next(s for s in card['sections'] if s['title']=='时间待确认')
    assert 'timeline' not in pending['rows'][0]

def test_recent_window_excludes_now_and_includes_exact_168h_for_both_endpoints():
    from game_assistant.qq.event_views import event_document
    data=[event('当前时刻开始',NOW.isoformat(),None),event('当前时刻结束',None,NOW.isoformat()),
          event('七天边界开始',(NOW+timedelta(hours=168)).isoformat(),None),event('七天边界结束',None,(NOW+timedelta(hours=168)).isoformat()),
          event('边界外结束',None,(NOW+timedelta(hours=168,seconds=1)).isoformat())]
    card=event_document('recent_events',{'nte':QueryResult(data,NOW.isoformat(),'ok',None)},now=NOW)
    sections={s['title']:s for s in card['sections']}
    assert [r['title'] for r in sections['即将开始']['rows']]==['七天边界开始']
    assert [r['title'] for r in sections['即将结束']['rows']]==['七天边界结束']

def test_nte_gacha_weapon_uses_audited_weapon_icon_lookup():
    from game_assistant.qq.assets import PublicAssetCache
    cache=PublicAssetCache()
    snapshot=QueryResult({'schema_version':1,'pools':[{'name':'弧盘池','details':[{'item_id':'fork_whale','name':'鲸歌','pity':40}]}]},NOW.isoformat(),'ok',None)
    card=view.gacha_document('nte','tajiduo',snapshot,cache)
    row=next(s for s in card['sections'] if s.get('layout')=='gacha')['rows'][0]
    assert row.get('image')==cache.ref_for('nte','weapon','fork_whale') and row.get('image') is not None

def test_partial_source_failure_does_not_mark_fresh_activity_source_stale():
    from game_assistant.qq.event_views import event_document
    snapshot=SimpleNamespace(payload=[event('可用来源','2026-10-10T08:00:00+08:00','2026-10-16T08:00:00+08:00')],state='error',fetched_at=NOW.isoformat(),complete=None,stale=False,poll_status={'source_statuses':{'community':{'state':'ok'},'bilibili':{'state':'error'}}})
    card=event_document('events',{'nte':snapshot},now=NOW)
    row=next(s for s in card['sections'] if s.get('game')=='nte')['rows'][0]
    assert not any(f['label']=='来源状态' for f in row['fields'])
    assert '部分来源不可用' in str(card)

def test_calendar_date_only_start_at_exact_midnight_end_is_uncertain():
    from game_assistant.qq.event_views import event_document
    card=event_document('calendar',{'nte':QueryResult([event('边界待确认',None,'2026-10-10T00:00:00+08:00',start_date='2026-10-10',start_precision='day')],NOW.isoformat(),'ok',None)},now=NOW)
    pending=next(s for s in card['sections'] if s['title']=='时间待确认')
    assert 'timeline' not in pending['rows'][0]
    assert view.long_document(card)['version']==3

def test_aggregate_one_public_reader_failure_preserves_other_game():
    query=CachedQuery();query.add('nte','tajiduo','n',{});query.add('wuthering_waves','kuro','ww',{})
    def read(game,cap):
        if game=='nte':raise RuntimeError('source fixture failure')
        return QueryResult([event('正常活动','2026-10-10T08:00:00+08:00','2026-10-16T08:00:00+08:00')],NOW.isoformat(),'ok',None)
    api=QqQueryService(SimpleNamespace(resolve_qq_identity=lambda i:Principal('u',False)),query,SimpleNamespace(read=read),clock=lambda:NOW)
    reply=api.query(IDENTITY,'events')
    assert '正常活动' in reply['text'] and '暂无成功快照' in reply['text'] and 'fixture failure' not in reply['text']
