"""Challenge cards read only the scheduler's same-grant ``combat`` snapshot."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from game_assistant.accounts.models import QueryResult
from game_assistant.endfield_challenges import (
    CHALLENGE_KINDS, build_challenge_report, challenge_reports, merge_challenge_snapshot,
)
from game_assistant.qq.commands import parse_command
from game_assistant.qq.presentation import long_document
from tests.test_qq_endfield_cached_details import forbidden
from tests.test_qq_unified_queries import CachedQuery, IDENTITY, service, no_external_network


def synthetic_challenges():
    group={'name':'合成关卡组','star':0,
           'normalDungeon':{'name':'普通试炼','isPass':True},
           'hardDungeon':{'name':'困难试炼','isPass':False},
           'cruelDungeon':{'name':'险境试炼','isPass':None}}
    war={'supported':True,'kind':'war','fetched_at':'2026-10-14T01:30:00Z','stale':False,'error':None,
         'records':[{'id':'s1','name':'合成赛季','stars':0,'start_at':None,'end_at':None,
                     'weeks':[{'id':'w1','name':'第一周','stars':0,'groups':[group]}]}],
         'summary':{'honors':[{'name':'合成荣誉','star':0,'first_pass_at':None}]}}
    monument={'supported':True,'kind':'monument','fetched_at':'2026-10-14T02:30:00Z','stale':True,
              'error':'RAW_ERROR_MUST_NOT_LEAK','records':[{'id':'m1','name':'合成丰碑','groups':[deepcopy(group)]}],
              'summary':{'count':1}}
    crisis={'supported':True,'kind':'crisis','fetched_at':'2026-10-14T03:30:00Z','stale':False,'error':None,
            'records':[{'id':'r1','score':0,'isPass':False},{'id':'r2','grade':None}],
            'summary':{'highest':0,'challenge_count':None}}
    return {'war':war,'monument':monument,'crisis':crisis}


def stored(values=None):
    """The persisted snapshot: only the allowlisted projection of each kind."""
    values=values or synthetic_challenges()
    return {'schema_version':1,'reports':[build_challenge_report(values[kind],kind=kind) for kind in CHALLENGE_KINDS]}


def setup(*, payload=True, state='ok', values=None):
    query=CachedQuery()
    scope=query.add('endfield','skland','sk',{'account':{'base':{'name':'本人档案'},'operators':[]}})
    query.data[('sk','combat')]=QueryResult(stored(values) if payload else None,'2026-10-14T04:00:00Z' if payload else None,state,None)
    grant={'id':'grant-sk','provider':'skland'}
    original=query.describe
    query.accounts.describe=lambda checked:{**original(checked),'game':'endfield','provider':grant['provider'],'grant_id':grant['id']}
    query.accounts.credentials=SimpleNamespace(load_grant=forbidden)
    # No live Skland service, credential load or per-user capability decoration.
    query.private=SimpleNamespace(skland=forbidden)
    query.list_accounts=query.adapter=forbidden
    return query,scope,grant


def test_qq_challenge_keeps_zero_unknown_separate_times_and_only_default_provider():
    query,scope,grant=setup()
    query.add('endfield','hypergryph','hg',{'account':{}})
    other=query.add('endfield','skland','other',{'combat':stored({**synthetic_challenges(),
        'war':{**synthetic_challenges()['war'],'records':[{'id':'x','name':'其他授权赛季'}]}})},default=False)
    context={};reply=service(query).query(IDENTITY,'combat','endfield',image_context=context)
    text=reply['text']
    assert '合成赛季' in text and '合成丰碑' in text and '最高值：0' in text and '其他授权赛季' not in text
    assert '挑战次数：未知' in text and '记录结果：0' in text and '通关状态：未知' in text
    assert '普通 · 普通试炼：已通关' in text and '困难 · 困难试炼：未通关' in text
    assert '险境 · 险境试炼：未知' in text and '赛季星数：0' in text
    for moment in ('09:30','10:30','11:30'):assert '2026-10-14 '+moment in text
    assert '显示旧观测' in text and 'RAW_ERROR_MUST_NOT_LEAK' not in text
    assert context['grants']==[(scope,1)] and len(context['snapshots'])==3
    assert [s.state for s in context['snapshots']]==['ok','error','ok']
    assert all(s.complete is None for s in context['snapshots'])
    assert query.reads==[(scope,'combat')] and query.refreshes==[]
    assert all(read[0]!=other for read in query.reads)


def test_unpolled_snapshot_says_collection_is_scheduled_not_empty():
    query,scope,grant=setup(payload=False,state='never')
    context={};text=service(query).query(IDENTITY,'combat','endfield',image_context=context)['text']
    assert text.count('尚未采集；后台定时采集后显示')==3
    assert '已采集记录：0' not in text and text.count('已采集记录：未知')==3
    assert all(s.fetched_at is None for s in context['snapshots']) and query.refreshes==[]


def test_failed_latest_poll_keeps_old_observation_and_its_time():
    query,scope,grant=setup(state='error')
    context={};text=service(query).query(IDENTITY,'combat','endfield',image_context=context)['text']
    assert text.count('最近读取失败，显示旧观测')==3 and '合成赛季' in text
    assert [s.fetched_at for s in context['snapshots']]==['2026-10-14T01:30:00Z','2026-10-14T02:30:00Z','2026-10-14T03:30:00Z']
    assert [s.state for s in context['snapshots']]==['error']*3
    query,scope,grant=setup(payload=False,state='error')
    text=service(query).query(IDENTITY,'combat','endfield')['text']
    assert text.count('最近读取失败，尚无成功观测')==3 and '已采集记录：0' not in text


def test_partially_failed_kind_without_success_is_not_reported_as_empty():
    values=synthetic_challenges()
    values['crisis']={'supported':True,'kind':'crisis','fetched_at':None,'stale':True}
    query,scope,grant=setup()
    query.data[('sk','combat')]=QueryResult(stored(values),'2026-10-14T04:00:00Z','ok',None)
    context={};text=service(query).query(IDENTITY,'combat','endfield',image_context=context)['text']
    assert '最近读取失败，尚无成功观测' in text and '最高值：未知' in text and '最高值：0' not in text
    assert [s.state for s in context['snapshots']]==['ok','error','error']


def test_hypergryph_only_cannot_supply_challenge_records():
    query,scope,grant=setup()
    query.rows[0]['provider']='hypergryph'
    query.read=forbidden
    assert '挑战需要本人森空岛档案授权' in service(query).query(IDENTITY,'combat','endfield')['text']


def test_projection_is_allowlisted_nonmutating_and_does_not_infer_empty_progress():
    value=synthetic_challenges()['crisis']
    value['summary']['best_record']={'secret':'DO_NOT_PROJECT'}
    value['records'][0].update(cred='DO_NOT_PROJECT',chars=[{'secret':'DO_NOT_PROJECT'}])
    before=deepcopy(value);report=build_challenge_report(value)
    assert 'DO_NOT_PROJECT' not in str(report) and value==before
    assert report['summary']['highest']==0 and report['summary']['challenge_count'] is None
    empty=build_challenge_report({**value,'records':[]})
    assert empty['available'] and empty['summary']['listed_count']==0
    unknown=build_challenge_report({**value,'fetched_at':None,'stale':True})
    assert not unknown['available'] and unknown['summary']['listed_count'] is None and unknown['records']==[]
    mismatch=build_challenge_report(value,kind='war')
    assert not mismatch['available'] and mismatch['records']==[]
    malformed=build_challenge_report({**value,'records':[{'id':float('nan'),'score':float('inf'),'isPass':1}]})
    assert malformed['records'][0]['id'] is None and malformed['records'][0]['result'] is None
    assert malformed['records'][0]['passed'] is None


def test_stored_reports_are_validated_per_kind_and_merge_keeps_last_success():
    good=stored()
    assert [r['kind'] for r in challenge_reports(good)]==list(CHALLENGE_KINDS)
    broken={'schema_version':1,'reports':[{**good['reports'][0],'records':'bad'},{'kind':'crisis'},'junk']}
    reports=challenge_reports(broken)
    assert [(r['kind'],r['available'],r['stale']) for r in reports]==[(k,False,False) for k in CHALLENGE_KINDS]
    assert all(not r['available'] for r in challenge_reports({'reports':good['reports']}))  # schema required
    assert all(r['stale'] for r in challenge_reports(good,stale=True))
    failed=stored({kind:{'supported':True,'kind':kind,'fetched_at':None,'stale':True} for kind in CHALLENGE_KINDS})
    merged=merge_challenge_snapshot(good,failed)
    assert [r['fetched_at'] for r in merged['reports']]==[r['fetched_at'] for r in good['reports']]
    assert all(r['stale'] for r in merged['reports'])
    assert merge_challenge_snapshot(None,failed)==failed
    assert merge_challenge_snapshot(failed,good)==good


def test_changed_content_or_failure_changes_independent_image_fingerprint():
    query,scope,grant=setup()
    api=service(query);first={};second={};third={}
    api.query(IDENTITY,'combat','endfield',image_context=first)
    query.data[('sk','combat')].payload['reports'][2]['summary']['highest']=10
    api.query(IDENTITY,'combat','endfield',image_context=second)
    assert first['fingerprints'][:2]==second['fingerprints'][:2]
    assert first['fingerprints'][2]!=second['fingerprints'][2]
    query.data[('sk','combat')].payload['reports'][2]['stale']=True
    api.query(IDENTITY,'combat','endfield',image_context=third)
    assert second['fingerprints'][2]!=third['fingerprints'][2]
    assert second['snapshots'][2].fetched_at==third['snapshots'][2].fetched_at


@pytest.mark.parametrize('change',['version','grant'])
async def test_grant_change_during_image_render_suppresses_challenge_reply(change):
    query,scope,grant=setup()
    class Queue:
        renderer=SimpleNamespace(invalidate_account=lambda *args:None)
        async def render(self,scope,result,**kwargs):
            assert len(result.payload['snapshot_fingerprints'])==3
            if change=='version':query.versions['sk']+=1
            else:grant['id']='replacement-with-same-version'
            return b'image'
    reply=await service(query,queue=Queue()).query_reply(IDENTITY,'combat','endfield',image_requested=True,budget_seconds=5)
    assert 'image' not in reply and '变更' in reply['text'] and '合成赛季' not in reply['text']


def test_challenge_command_and_long_card_are_bounded():
    assert parse_command('终末地 挑战').command=='combat'
    query,scope,grant=setup()
    context={};service(query).query(IDENTITY,'combat','endfield',image_context=context)
    huge=deepcopy(context['card']);huge['sections']*=100
    assert any('省略' in notice for notice in long_document(huge)['notices'])


def shaped_challenges(seasons, weeks, honors, monuments, groups, crises):
    """Synthetic counts only: real war seasons carry two weeks; four groups per week is assumed."""
    def group(index):
        return {'name':f'合成关卡组{index}','star':index%4,'normalDungeon':{'name':'普通试炼','isPass':True},
                'hardDungeon':{'name':'困难试炼','isPass':index%2==0},'cruelDungeon':{'name':'险境试炼','isPass':None}}
    # Oldest first, so the projection has to pick the newest by time rather than position.
    def at(index):return f'2026-{1+index//28:02d}-{1+index%28:02d}T02:00:00Z'
    war={'supported':True,'kind':'war','fetched_at':'2026-10-21T01:30:00Z','stale':False,'error':None,
         'records':[{'id':f's{i}','name':f'合成赛季{i}','stars':i,'start_at':at(i),'end_at':None,
                     'weeks':[{'id':f'w{i}-{j}','name':f'第{j+1}周','stars':j,'groups':[group(k) for k in range(4)]} for j in range(weeks)]}
                    for i in range(seasons)],
         'summary':{'honors':[{'name':f'合成荣誉{i}','star':i%3,'first_pass_at':at(i)} for i in range(honors)]}}
    monument={'supported':True,'kind':'monument','fetched_at':'2026-10-21T02:30:00Z','stale':False,'error':None,
              'records':[{'id':f'm{i}','name':f'合成丰碑{i}','start_at':at(i),'end_at':None,
                          'groups':[group(k) for k in range(groups)]} for i in range(monuments)],'summary':{}}
    crisis={'supported':True,'kind':'crisis','fetched_at':'2026-10-21T03:30:00Z','stale':False,'error':None,
            'records':[{'id':f'r{i}','score':i,'isPass':i%2==0} for i in range(crises)],
            'summary':{'highest':crises,'challenge_count':crises}}
    return {'war':war,'monument':monument,'crisis':crisis}


# (seasons, weeks per season, honors, monument records, groups per monument, crisis records)
REALISTIC=(5,2,20,7,4,0)
WORST=(10,4,40,15,6,10)


@pytest.mark.parametrize('shape',[REALISTIC,WORST],ids=['realistic','worst'])
def test_image_keeps_latest_records_full_counts_and_says_so(shape):
    seasons,weeks,honors,monuments,groups,crises=shape
    query,scope,grant=setup(values=shaped_challenges(*shape))
    context={};text=service(query).query(IDENTITY,'combat','endfield',image_context=context)['text']
    display=context['render_snapshot']['display_data']
    war,monument,crisis=display['panels'][0]['snapshot']['payload']['reports']
    # Newest by start time, in upstream order; every week of the kept season stays.
    assert [r['name'] for r in war['records']]==[f'合成赛季{seasons-1}']
    assert len(war['records'][0]['weeks'])==weeks
    assert [h['name'] for h in war['honors']]==[f'合成荣誉{i}' for i in range(honors-6,honors)]
    assert [r['name'] for r in monument['records']]==[f'合成丰碑{i}' for i in range(monuments-3,monuments)]
    assert len(monument['records'][0]['groups'])==groups
    assert [r['id'] for r in crisis['records']]==['r0','r1'][:crises]
    assert [r['summary']['listed_count'] for r in (war,monument,crisis)]==[seasons,monuments,crises]
    notice=next(n for n in display['notices'] if n.startswith('挑战图片最多展示'))
    assert f'战争最近 1 个赛季（共 {seasons}）' in notice and f'战争荣誉最近 6 条（共 {honors}）' in notice
    assert f'丰碑最近 3 条记录（共 {monuments}）' in notice and '完整列表请到网站查看' in notice
    assert ('危机' in notice)==(crises>2)
    # The text card and the per-kind snapshots keep every record.
    assert f'已采集记录：{seasons}' in text
    assert [len(s.payload['records']) for s in context['snapshots']]==[seasons,monuments,crises]


def test_image_cap_keeps_unknown_and_short_lists_unchanged():
    from game_assistant.qq.endfield_presentation import challenge_image_reports
    query,scope,grant=setup()
    context={};service(query).query(IDENTITY,'combat','endfield',image_context=context)
    display=context['render_snapshot']['display_data']
    assert len(display['panels'][0]['snapshot']['payload']['reports'][2]['records'])==2
    assert not any('最多展示' in n for n in display['notices'])
    query,scope,grant=setup(payload=False,state='never')
    context={};service(query).query(IDENTITY,'combat','endfield',image_context=context)
    reports=context['render_snapshot']['display_data']['panels'][0]['snapshot']['payload']['reports']
    assert [r['summary']['listed_count'] for r in reports]==[None]*3 and not any(r['records'] for r in reports)
    assert challenge_image_reports(challenge_reports(None))==(challenge_reports(None),[])
    # Without a time for every record the upstream (newest-first) order decides.
    value={**shaped_challenges(*REALISTIC)['monument'],
           'records':[{'id':f'm{i}','start_at':None if i==1 else 'x','groups':[]} for i in range(5)]}
    shown,notices=challenge_image_reports([build_challenge_report(value)])
    assert [r['id'] for r in shown[0]['records']]==['m0','m1','m2'] and shown[0]['summary']['listed_count']==5
    assert notices==['挑战图片最多展示丰碑最近 3 条记录（共 5）；完整列表请到网站查看。']


@pytest.mark.parametrize('shape,limit',[(REALISTIC,8000),(WORST,14000)],ids=['realistic','worst'])
async def test_real_challenge_image_stays_under_pixel_limit(shape,limit,tmp_path):
    import base64,os
    from io import BytesIO
    from PIL import Image
    from game_assistant.qq.browser_rendering import BrowserRenderer
    from game_assistant.qq.rendering import RenderQueue
    executable=os.environ.get('QQ_RENDER_TEST_EXECUTABLE');font=os.environ.get('QQ_RENDER_TEST_FONT')
    if not executable or not font:pytest.skip('Real challenge rendering requires QQ_RENDER_TEST_EXECUTABLE and QQ_RENDER_TEST_FONT')
    renderer=BrowserRenderer(template='a',executable_path=executable,font_path=font,dist_path=os.environ.get('QQ_RENDER_TEST_DIST',''))
    query,scope,grant=setup(values=shaped_challenges(*shape))
    try:
        await renderer._a_ready()  # cold Chromium start outside the 10 s reply budget
        reply=await service(query,queue=RenderQueue(renderer)).query_reply(IDENTITY,'combat','endfield',image_requested=True,budget_seconds=10)
        assert 'image' in reply,(renderer.last_state.get('height'),reply['text'][:120])
        png=base64.b64decode(reply['image']);(tmp_path/'challenge.png').write_bytes(png)
        with Image.open(BytesIO(png)) as picture:
            assert picture.width==1080 and picture.height<=limit
        assert len(png)<=renderer.max_bytes
        state=renderer.last_state
        assert state['state']=='ready' and not state['overflow'] and state['layout_issues']==0
    finally:await renderer.aclose()
