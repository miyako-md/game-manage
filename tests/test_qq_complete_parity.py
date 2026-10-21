"""All basic QQ images use safe offline website component snapshots."""
import json
import base64
from io import BytesIO
import os
from datetime import datetime
from types import SimpleNamespace

import pytest

from game_assistant.accounts.models import QueryResult
from game_assistant.qq import render_snapshot as shared
from game_assistant.qq.browser_rendering import validate_snapshot
from game_assistant.qq.rendering import RenderingUnavailable
from tests.test_qq_unified_queries import CachedQuery, IDENTITY, service

NOW=datetime.fromisoformat('2026-10-15T12:00:00+08:00')


def test_capability_projection_is_explicit_and_preserves_zero_unknown_and_safe_assets():
    row=QueryResult({'schema_version':1,'nickname':'合成昵称','level':0,'role_id':'PRIVATE-UID',
        'token':'PRIVATE-TOKEN','path':'C:/PRIVATE/file','extra':{'profile':{'world_level':None,'active_days':0},'role_id':'PRIVATE-UID'}},NOW.isoformat(),'ok',False)
    panel=shared.game_panel('wuthering_waves','kuro','account',row)
    assert panel['snapshot']['payload']=={'schema_version':1,'nickname':'合成昵称','level':0,'extra':{'profile':{'world_level':None,'active_days':0}}}
    snapshot=shared.game_snapshot([panel],NOW,title='概览',command='鸣潮 总览')
    assert snapshot['kind']=='game_snapshot' and snapshot['theme']=='light'
    assert 'PRIVATE' not in json.dumps(snapshot)
    poisoned=json.loads(json.dumps(snapshot));poisoned['display_data']['panels'][0]['snapshot']['payload']['weapon']={'name':'wrong capability'}
    with pytest.raises(RenderingUnavailable):validate_snapshot(poisoned)


def test_notice_is_only_sanitized_user_strings_without_technical_metadata():
    from game_assistant.qq import presentation as view
    card=view.document('status','all','绑定状态',sections=[{'title':'帮助','fields':[view.field('步骤','登录网页'),view.field('完整性','未知')]}],notices=['缓存状态：error','缓存快照','请重新授权'])
    snapshot=shared.notice_snapshot(card,NOW)
    assert snapshot['kind']=='notice'
    data=snapshot['display_data']
    assert data['sections']==[{'title':'帮助','items':['步骤：登录网页']}]
    assert data['notices']==['请重新授权']
    assert '未知' not in json.dumps(data)
    data['sections'][0]['items'].append({'token':'private'})
    with pytest.raises(RenderingUnavailable):validate_snapshot(snapshot)


def test_rich_business_fields_survive_projection_while_dynamic_source_keys_and_paths_do_not():
    row=QueryResult({'hologram':{'data':{'challenge_info':{'raw_source_key':[{'boss_name':'首领','difficulty':0,'boss_level':None,'token':'PRIVATE'}]}}}},None,'ok',False)
    panel=shared.game_panel('wuthering_waves','kuro','combat',row)
    assert panel['snapshot']['payload']['hologram']['data']['challenge_info']=={'bucket_0':[{'boss_name':'首领','difficulty':0,'boss_level':None}]}
    shared.game_snapshot([panel],NOW)
    row=QueryResult({'schema_version':1,'total':2,'pools':[{'key':'pool','label':'角色池','six_star':1,'five_star':0,'history':[{'name':'陈千语','pulls':None,'status':'lower_bound','pool_name':'角色池'}]}]},None,'ok',False)
    panel=shared.game_panel('endfield','hypergryph','gacha',row)
    assert panel['snapshot']['payload']['pools'][0]['history'][0]['pulls'] is None
    assert panel['snapshot']['payload']['pools'][0]['five_star']==0
    shared.game_snapshot([panel],NOW)
    summary=shared.game_panel('endfield','hypergryph','gacha',row,summary=True)
    assert 'history' not in summary['snapshot']['payload']['pools'][0]
    assert summary['snapshot']['payload']['pools'][0]['six_star']==1
    data=shared.panel_payload('nte','tajiduo','account',{'nickname':'C:/private/user/file','token':'secret'})
    assert 'private' not in data['nickname'] and 'secret' not in str(data)
    # Panels that only served retired commands are no longer projectable.
    for game,cap in (('nte','news'),('wuthering_waves','activities'),('endfield','stamina'),('endfield','training'),('endfield','regions'),('endfield','progress')):
        with pytest.raises(RenderingUnavailable,match='unsupported_panel'):shared.panel_payload(game,'public' if cap=='news' else 'skland',cap,{})
    with pytest.raises(RenderingUnavailable,match='data_limit'):shared.panel_payload('nte','tajiduo','account',{'nickname':'长'*8001})


def test_original_article_links_stay_exact_without_allowing_private_urls():
    for url in ('https://www.kurobbs.com/forum/post/1234567001','https://www.kurobbs.com/forum/post/1234567002'):
        assert shared.safe_article_url(url)==url
    for url in ('http://127.0.0.1/private','file:///C:/secret','https://user:secret@www.kurobbs.com/forum/post/1',
        'https://www.kurobbs.com/forum/post/1?token=secret','https://evil.invalid/news/1',
        'https://www.kurobbs.com/forum/../private','https://www.kurobbs.com/C:/Users/private'):
        assert shared.safe_article_url(url) is None


@pytest.mark.parametrize('game,provider,cap,payload',[
 ('nte','tajiduo','progress',{'schema_version':1,'completed':0,'total':100,'gold':None}),
 ('wuthering_waves','kuro','exploration',{'country_groups':[{'name':'区域','progress':None}]}),
 ('endfield','hypergryph','gacha',{'schema_version':1,'total':0,'complete':False,'pools':[]}),
 ('wuthering_waves','kuro','roles',[{'role_id':1304,'name':'今汐','level':0}]),
])
def test_cached_data_commands_emit_component_panel_without_detail_fetch(game,provider,cap,payload):
    query=CachedQuery();query.add(game,provider,'private-account',{cap:payload})
    context={};api=service(query)
    reply=api.query(IDENTITY,cap,game,image_context=context)
    value=context['render_snapshot']
    assert context['shared_required'] is True
    assert value['kind']=='game_snapshot'
    assert value['display_data']['panels'][0]['capability']==cap
    assert 'private-account' not in json.dumps(value)
    assert 'text' in reply
    assert len(context['grants'])==1 and context['fingerprints']


def test_endfield_named_operator_uses_only_selected_cached_operator():
    query=CachedQuery();query.add('endfield','skland','private-account',{'account':{'base':{'name':'昵称','role_id':'PRIVATE'},'operators':[{'id':'1','name':'陈千语','level':0},{'id':'2','name':'另一干员'}]}})
    context={};service(query).query(IDENTITY,'roles','endfield',role_name='陈千语',image_context=context)
    value=context['render_snapshot'];panel=value['display_data']['panels'][0]
    assert [row['name'] for row in panel['snapshot']['payload']['operators']]==['陈千语']
    assert [row['name'] for row in panel['snapshot']['payload']['report']['training']['items']]==['陈千语']
    assert '另一干员' not in json.dumps(panel['snapshot']['payload'],ensure_ascii=False)
    assert 'PRIVATE' not in json.dumps(value)


def test_overview_keeps_both_endfield_providers_and_bounded_roster_summary():
    query=CachedQuery()
    query.add('endfield','hypergryph','hg',{'account':{'nickname':'鹰角'}})
    query.add('endfield','skland','sk',{'account':{'base':{'name':'森空岛'}}})
    query.add('wuthering_waves','kuro','ww',{'account':{'nickname':'鸣潮'},'roles':[{'role_id':i,'name':f'角色{i}'} for i in range(10)]})
    context={};service(query).query(IDENTITY,'overview',image_context=context)
    value=context['render_snapshot'];panels=value['display_data']['panels']
    assert {p['provider'] for p in panels if p['game']=='endfield'}=={'skland','hypergryph'}
    roster=next(p for p in panels if p['capability']=='roles')
    assert len(roster['snapshot']['payload'])==6
    assert any('6' in message and '角色' in message for message in value['display_data']['notices'])
    assert len(context['grants'])==3


def test_overview_account_panels_carry_full_role_totals_before_six_role_truncation():
    query=CachedQuery()
    query.add('wuthering_waves','kuro','ww',{'account':{'nickname':'鸣潮'},
        'roles':[{'role_id':i,'name':f'角色{i}','star_level':5 if i<7 else 4} for i in range(10)]})
    query.add('nte','tajiduo','nte',{'account':{'nickname':'异环'},
        'roles':{'entries':[{'id':str(i),'name':f'异能者{i}','quality':'S' if i%2 else 'A'} for i in range(9)]}})
    context={};service(query).query(IDENTITY,'overview',image_context=context)
    panels=context['render_snapshot']['display_data']['panels']
    account={p['game']:p['snapshot']['payload'] for p in panels if p['capability']=='account'}
    roles={p['game']:p['snapshot']['payload'] for p in panels if p['capability']=='roles'}
    assert len(roles['wuthering_waves'])==6 and len(roles['nte']['entries'])==6
    assert (account['wuthering_waves']['role_total'],account['wuthering_waves']['gold_role_total'])==(10,7)
    assert (account['nte']['role_total'],account['nte']['gold_role_total'])==(9,4)
    validate_snapshot(context['render_snapshot'])


def test_role_totals_omit_gold_count_when_any_rarity_is_unknown():
    assert shared.role_totals('wuthering_waves',[{'star_level':5},{'star_level':None}])=={'role_total':2}
    assert shared.role_totals('nte',{'entries':[{'quality':'S'},{}]})=={'role_total':2}
    assert shared.role_totals('nte',{'entries':[]})=={} and shared.role_totals('endfield',{'operators':[{}]})=={}


def test_shared_full_roster_does_not_inherit_legacy_document_clipping_notices():
    query=CachedQuery();query.add('wuthering_waves','kuro','private-account',{'roles':[{'role_id':i,'name':f'合成角色{i:03}','level':0} for i in range(300)]})
    context={};service(query).query(IDENTITY,'roles','wuthering_waves',image_context=context)
    value=context['render_snapshot'];payload=value['display_data']['panels'][0]['snapshot']['payload']
    assert len(payload)==300
    assert not any('省略' in text or '缓存快照' in text for text in value['display_data']['notices'])


@pytest.mark.parametrize('command',['help','status','refresh'])
def test_structural_responses_always_use_notice(command):
    query=CachedQuery();query.add('nte','tajiduo','private-account',{'stamina':{'current':0}})
    context={};service(query).query(IDENTITY,command,'nte' if command=='refresh' else None,image_context=context)
    assert context['shared_required'] is True
    assert context['render_snapshot']['kind']=='notice'
    assert '覆盖待核验' not in json.dumps(context['render_snapshot'],ensure_ascii=False)


def test_current_and_recent_event_panels_filter_original_events_without_invented_times():
    from game_assistant.qq.query_routes import QqQueryService
    rows=[{'name':'进行中','start_at':'2026-10-14T00:00:00+08:00','end_at':'2026-10-16T00:00:00+08:00'},
        {'name':'未来','start_at':'2026-10-17T00:00:00+08:00','end_at':'2026-10-30T00:00:00+08:00'},
        {'name':'已结束','start_at':'2026-10-01T00:00:00+08:00','end_at':'2026-10-02T00:00:00+08:00'},
        {'name':'预计','start_date':'2026-10-18','start_precision':'relative','start_estimated':True}]
    api=QqQueryService(None,None,SimpleNamespace(read=lambda *args:QueryResult(rows,NOW.isoformat(),'ok',False)),clock=lambda:NOW)
    for command,names in [('events',['进行中','预计']),('recent_events',['进行中','未来','预计'])]:
        context={};api.query(IDENTITY,command,'nte',image_context=context)
        value=context['render_snapshot'];events=value['display_data']['panels'][0]['snapshot']['payload']
        assert [row['name'] for row in events]==names
        assert 'start_at' not in events[-1] and events[-1]['start_estimated'] is True


@pytest.mark.parametrize('command',['events','recent_events'])
def test_filtered_events_match_existing_timezone_phase_unknown_invalid_and_inclusive_window_semantics(command):
    from game_assistant.qq.event_views import event_document
    raw=[{'name':'分期活动','phases':[
        {'start_at':'2026-10-15T03:00:00Z','end_at':'2026-10-15T05:00:00Z'},
        {'start_at':'2026-10-16T00:00:00+08:00','end_at':'2026-10-18T00:00:00+08:00'}]},
        {'name':'窗口右边界','start_at':'2026-10-22T12:00:00+08:00'},
        {'name':'窗口外','start_at':'2026-10-22T12:00:01+08:00'},
        {'name':'无精度时刻','start_at':'2026-10-15 11:00:00','end_at':'2026-10-15 13:00:00'},
        {'name':'相对时间','start_date':'2026-10-16','start_precision':'relative','start_estimated':True},
        {'name':'仅日期','start_date':'2026-10-18','start_precision':'day'},
        {'name':'截止未知','start_at':'2026-10-01T00:00:00+08:00'},
        {'name':'异常区间','start_at':'2026-10-16T00:00:00+08:00','end_at':'2026-10-14T00:00:00+08:00'},
        {'name':'刚结束','start_at':'2026-10-14T00:00:00+08:00','end_at':NOW.isoformat()}]
    row=QueryResult(raw,NOW.isoformat(),'ok',False)
    original=event_document(command,{'nte':row},now=NOW)
    expected={item['title'] for section in original['sections'] if section['title']!='公共快照状态' for item in section.get('rows',[])}
    value=shared.filtered_events_snapshot({'nte':row},command,NOW)
    events=value['display_data']['panels'][0]['snapshot']['payload']
    assert {item['name'] for item in events}==expected
    assert '分期活动 · 阶段 1' in expected
    if command=='recent_events':assert '分期活动 · 阶段 2' in expected and '窗口右边界' in expected and '窗口外' not in expected
    assert json.dumps(raw,ensure_ascii=False).count('display_title')==0


def test_typed_assets_only_prefetch_actually_visible_urls_and_deduplicate_safely():
    icon='https://webstatic.tajiduo.com/role.png'
    hidden='https://webstatic.tajiduo.com/hidden.png'
    panels=[shared.game_panel('nte','tajiduo','roles',QueryResult({'schema_version':1,'entries':[{'name':'角色','icon_url':icon,'weapon':{'icon_url':hidden}}]},None,'ok',False)),
        shared.game_panel('endfield','skland','account',QueryResult({'operators':[{'name':'隐藏','avatar_url':hidden}]},None,'ok',False))]
    assert list(shared.asset_urls(shared.game_snapshot(panels,NOW)))==[icon]


async def test_shared_required_missing_snapshot_is_refused():
    from game_assistant.accounts.models import AccountScope
    from game_assistant.qq.browser_rendering import BrowserRenderer
    renderer=BrowserRenderer()
    with pytest.raises(RenderingUnavailable,match='shared_content_unavailable'):
        await renderer.render_summary_async(AccountScope('u','a','r'),QueryResult({'shared_required':True},None,'ok',False),budget_seconds=1)


async def test_new_component_images_still_recheck_authorization_after_render():
    query=CachedQuery();query.add('nte','tajiduo','private-account',{'exploration':{'areas':[]}})
    class Queue:
        renderer=SimpleNamespace(invalidate_account=lambda *args:None)
        async def render(self,scope,result,**kwargs):
            assert result.payload['render_snapshot']['kind']=='game_snapshot'
            query.versions['private-account']+=1
            return b'png'
    reply=await service(query,queue=Queue()).query_reply(IDENTITY,'exploration','nte',image_requested=True,budget_seconds=5)
    assert 'image' not in reply and '变更' in reply['text']


@pytest.mark.parametrize('case',['wuwa_roster','endfield_selected','help_notice'])
async def test_real_basic_command_through_projection_queue_and_browser(case,tmp_path):
    from PIL import Image
    from game_assistant.qq.browser_rendering import BrowserRenderer
    from game_assistant.qq.rendering import RenderQueue
    executable,font=os.environ.get('QQ_RENDER_TEST_EXECUTABLE'),os.environ.get('QQ_RENDER_TEST_FONT')
    if not executable or not font:pytest.skip('Explicit isolated Chromium/font required')
    class Inspectable(BrowserRenderer):
        text=''
        async def _bounded_close(self,operation):
            if self._browser and self._browser.contexts and self.last_state and self.last_state.get('state')=='ready':
                self.text='\n'.join(await self._browser.contexts[0].pages[0].locator('.render-page').all_inner_texts())
            return await super()._bounded_close(operation)
    renderer=Inspectable(executable_path=executable,font_path=font)
    queue=RenderQueue(renderer)
    query=CachedQuery()
    if case=='wuwa_roster':
        query.add('wuthering_waves','kuro','PRIVATE-ACCOUNT',{'roles':[{'role_id':f'char-{i}','name':f'合成共鸣者{i:02}','level':0,'extra':{'total_skill_level':None,'token':'PRIVATE'}} for i in range(21)]})
        command,game,role='roles','wuthering_waves',None
        expected=('合成共鸣者00','合成共鸣者20','Lv.0')
    elif case=='endfield_selected':
        query.add('endfield','skland','PRIVATE-ACCOUNT',{'account':{'base':{'name':'合成档案','role_id':'PRIVATE'},'operators':[
            {'id':'1','name':'陈千语','level':0,'potential':None,'weapon':{'name':'缓存长剑','level':0,'refine_level':None,'gem':{'name':'合成基质','terms':[{'name':'词条末尾','cost':0}]}},'equipment':[{'name':'合成护甲','level':None}],'skills':[{'name':'合成技能末尾','level':0}]},
            {'id':'2','name':'未选干员'}]}})
        command,game,role='roles','endfield','陈千语'
        expected=('陈千语','缓存长剑','合成护甲','合成技能末尾','词条末尾')
    else:
        command,game,role='help',None,None
        expected=('帮助','角色')
    api=service(query,queue=queue)
    try:
        reply=await api.query_reply(IDENTITY,command,game,role_name=role,image_requested=True,budget_seconds=10)
        assert 'image' in reply,reply
        raw=base64.b64decode(reply['image'])
        image=Image.open(BytesIO(raw))
        assert image.width==720 and 0<image.height<=1440 and len(raw)<=1048576
        assert renderer.last_state['state']=='ready'
        assert renderer.last_state['content_blocks']==renderer.last_state['displayed_blocks']
        assert 1<=len(renderer.last_state['pages'])<=100 and not renderer._browser.contexts
        assert reply['page']==1 and reply['total_pages']==len(renderer.last_state['pages'])
        assert all(row['width']==720 and 0<row['height']<=1440 for row in renderer.last_state['pages'])
        assert all(text in renderer.text for text in expected),renderer.text
        assert not any(text in renderer.text for text in ('PRIVATE','未选干员','role_id','server_id','来源补充字段'))
        assert all(cap!='role_detail' for _,cap in query.reads)
        (tmp_path/f'{case}.png').write_bytes(raw)
        (tmp_path/f'{case}.json').write_text(json.dumps({'dimensions':image.size,'bytes':len(raw),'state':renderer.last_state,'text':renderer.text},ensure_ascii=False),encoding='utf-8')
    finally:await api.aclose()
