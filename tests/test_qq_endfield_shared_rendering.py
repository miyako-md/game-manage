"""Endfield commands use the complete, scoped shared Vue display contract."""
from copy import deepcopy
from datetime import datetime
import json
import pytest

from game_assistant.accounts.models import QueryResult
from game_assistant.qq.render_snapshot import game_panel, game_snapshot
from game_assistant.qq.browser_rendering import validate_snapshot
from game_assistant.qq.rendering import RenderingUnavailable
from tests.test_qq_unified_queries import CachedQuery, IDENTITY, service, no_external_network
from tests.test_qq_endfield_reports import synthetic_account, synthetic_gacha
from tests.test_qq_endfield_challenges import setup, synthetic_challenges

NOW = datetime.fromisoformat('2026-10-15T12:00:00+08:00')

@pytest.mark.parametrize('command,cap', [('summary','account'),('roles','roles'),('exploration','exploration'),('ship','ship'),('honor','honor')])
def test_profile_commands_forward_shared_report_and_zero_without_scope_identifiers(command, cap):
    query=CachedQuery();payload=synthetic_account(35)
    payload['base']['role_id']='123456789';payload['uid']='PRIVATE_SOURCE_ID';payload['token']='PRIVATE_TOKEN'
    query.add('endfield','skland','scope-account',{'account':payload},role='internal-role-uuid')
    context={};service(query).query(IDENTITY,command,'endfield',image_context=context)
    snapshot=context['render_snapshot'];assert snapshot['kind']=='game_snapshot'
    panel=next(panel for panel in snapshot['display_data']['panels'] if panel['capability']==cap)
    data=panel['snapshot']['payload'];assert data['report']['overview']['stamina']['current']==0
    assert len(data['report']['training']['items'])==35
    assert data['report']['training']['summary']['rarity_counts']=={'6':12,'5':23}
    assert 'PRIVATE_' not in json.dumps(snapshot) and '123456789' not in json.dumps(snapshot)
    assert context['grants'][0][0].role_id=='internal-role-uuid'
    assert validate_snapshot(snapshot)==snapshot


@pytest.mark.parametrize('command,cap',[('summary','account'),('exploration','exploration')])
def test_regions_projection_preserves_all_collection_labels_keys_zero_and_known_summary(command,cap):
    query=CachedQuery();query.add('endfield','skland','scope-account',{'account':synthetic_account(3)})
    context={};service(query).query(IDENTITY,command,'endfield',image_context=context)
    panel=next(panel for panel in context['render_snapshot']['display_data']['panels'] if panel['capability']==cap)
    report=panel['snapshot']['payload']['report']['regions']
    assert report['summary']=={'region_count':2,'settlement_count':1}
    collections=report['items'][0]['areas'][0]['collections']
    assert [(item['key'],item['label']) for item in collections]==[('chests','宝箱'),('puzzles','醚质'),('blackboxes','协议采录桩'),('equipment_chests','装备制造模板'),('pieces','维修灵感点')]
    assert collections[1]['current']==0 and collections[1]['remaining']==8
    assert collections[2]['current'] is None and collections[2]['remaining'] is None
    assert collections[4]['remaining']==0
    assert 'source_url' not in panel['snapshot']['payload']['report']['ship']['conversion_model']


def test_named_operator_detail_forwards_existing_cache_and_independent_time(tmp_path):
    from tests.test_qq_endfield_cached_details import fixture
    query,scope,grant,bundle,scoped=fixture(tmp_path)
    context={};service(query).query(IDENTITY,'roles','endfield',role_name='佩丽卡',image_context=context)
    panel=context['render_snapshot']['display_data']['panels'][0]
    assert panel['capability']=='operator_detail'
    data=panel['snapshot']['payload']
    assert data['operator_detail']['weapon']['name']=='已观测详情武器'
    assert data['operator_detail_id']=='c1' and data['operator_fetched_at']=='2026-10-14T00:00:00Z'
    assert data['operator_stale'] is False
    assert query.refreshes==[] and not bundle.private_root.exists()


def test_all_challenge_categories_forward_every_returned_week_and_independent_times(tmp_path):
    query,scope,grant,bundle,scoped=setup(tmp_path)
    values=synthetic_challenges();week=values['war']['records'][0]['weeks'][0]
    values['war']['records'][0]['weeks']=[{**deepcopy(week),'name':f'周次{i}'} for i in range(40)]
    scoped._service._challenge_cache.update({(kind,None,None,None):value for kind,value in values.items()})
    context={};service(query).query(IDENTITY,'combat','endfield',image_context=context)
    panel=context['render_snapshot']['display_data']['panels'][0]
    assert panel['capability']=='combat'
    reports=panel['snapshot']['payload']['reports']
    assert [report['kind'] for report in reports]==['war','monument','crisis']
    assert len(reports[0]['records'][0]['weeks'])==40
    assert [report['fetched_at'] for report in reports]==[value['fetched_at'] for value in values.values()]
    assert reports[1]['stale'] is True and reports[2]['summary']['highest']==0
    assert 'RAW_ERROR_MUST_NOT_LEAK' not in json.dumps(reports)


def test_gacha_keeps_all_seventeen_returned_pools_and_history_rows():
    query=CachedQuery();payload=synthetic_gacha();payload['schema_version']=1;sample=payload['pools'][0]
    payload['pools']=[{**deepcopy(sample),'key':f'pool-{i}','label':f'合成池{i}'} for i in range(17)]
    query.add('endfield','hypergryph','scope-account',{'gacha':payload})
    context={};service(query).query(IDENTITY,'gacha','endfield',image_context=context)
    panel=context['render_snapshot']['display_data']['panels'][0]
    assert panel['capability']=='gacha'
    report=panel['snapshot']['payload']['report']
    assert not any('省略' in notice or '本图' in notice for notice in context['render_snapshot']['display_data']['notices'])
    assert len(report['pools'])==17 and sum(len(pool['history']) for pool in report['pools'])==51


def test_report_maps_keep_only_bounded_business_counts_and_validator_rejects_unknown_map_keys():
    payload={'report':{'schema_version':1,'training':{'summary':{'rarity_counts':{'6':0,'token':9,'1000':1},'phase_counts':{'0':0,'3':4,'-1':5}}}}}
    row=QueryResult(payload,NOW.isoformat(),'ok',None)
    panel=game_panel('endfield','skland','roles',row)
    summary=panel['snapshot']['payload']['report']['training']['summary']
    assert summary=={'rarity_counts':{'6':0},'phase_counts':{'0':0,'3':4}}
    snapshot=game_snapshot([panel],NOW)
    snapshot['display_data']['panels'][0]['snapshot']['payload']['report']['training']['summary']['rarity_counts']['unexpected']=1
    with pytest.raises(RenderingUnavailable):validate_snapshot(snapshot)


def test_noncredential_roster_identifiers_survive_text_sanitization_for_exact_joins():
    identity='123456789abcdef0123456789abcdef0'
    row=QueryResult({'operators':[{'id':identity,'char_id':'chr_0001_sample','name':'合成干员'}]},NOW.isoformat(),'ok',None)
    data=game_panel('endfield','skland','roles',row)['snapshot']['payload']
    assert data['operators'][0]['id']==identity


@pytest.mark.parametrize('command,role_name',[('roster',None),('exploration',None),('ship',None),('honor',None),('roles','佩丽卡'),('roles_icon','佩丽卡'),('combat',None),('gacha',None)])
async def test_real_internal_route_queue_and_browser_reuse_shared_complete_endfield_views(tmp_path,monkeypatch,command,role_name):
    import os
    from io import BytesIO
    import httpx
    from PIL import Image
    from playwright.async_api import Page
    from game_assistant.cloud_app import create_cloud_app
    from game_assistant.config import Settings
    from game_assistant.identity.models import Principal
    from game_assistant.qq.client import InternalQqClient
    from game_assistant.qq.models import QqIdentity,InboundMessage
    from tests.test_qq_endfield_cached_details import fixture
    executable=os.environ.get('QQ_RENDER_TEST_EXECUTABLE');font=os.environ.get('QQ_RENDER_TEST_FONT')
    if not executable or not font:pytest.skip('Real shared rendering requires QQ_RENDER_TEST_EXECUTABLE and QQ_RENDER_TEST_FONT')
    query,scope,grant,bundle,scoped=fixture(tmp_path)
    skill_icon='https://web.hycdn.cn/public/fixture-skill.png'
    if command=='roles_icon':
        scoped._service._operator_cache['c1']['operator']['skills'][0]['icon_url']=skill_icon
    payload=synthetic_account(35);payload['operators'][0].update(id='c1',name='佩丽卡');payload['operators'][1]['name']='祀'
    payload['achievements']={'count':34,'medals':[{'level':1,'achievementData':{'id':f'm{i}','name':f'奖章{i}','cateName':f'类别{i//2}'}} for i in range(34)]};payload['availability']['honor']=True
    query.data[('sk','account')]=QueryResult(payload,NOW.isoformat(),'ok',None)
    gacha=synthetic_gacha();gacha['schema_version']=1;sample=gacha['pools'][0]
    gacha['pools']=[{**deepcopy(sample),'key':f'pool-{i}','label':f'合成池{i}'} for i in range(17)]
    query.add('endfield','hypergryph','hg',{'gacha':gacha})
    query.accounts.describe=lambda checked:{**query.describe(checked),'game':'endfield','provider':'skland' if checked.account_id=='sk' else 'hypergryph','grant_id':grant['id'] if checked.account_id=='sk' else 'grant-hg'}
    scoped._service._challenge_cache.update({(kind,None,None,None):value for kind,value in synthetic_challenges().items()})
    app=create_cloud_app(Settings(cloud_db_path=str(tmp_path/'cloud.db'),cloud_allowed_origins=['https://cloud.example'],qq_app_id='app',qq_service_token='fixture-service',qq_images_enabled=True,qq_image_font_path=font,qq_browser_render_executable_path=executable,qq_browser_render_dist_path=os.environ.get('QQ_RENDER_TEST_DIST', '')),start_scheduler=False)
    svc=app.state.qq_query;svc.query_service=query;query.accounts._listeners.append(svc.invalidate)
    if command=='roles_icon':
        output=BytesIO();Image.new('RGB',(54,54),'#437b75').save(output,'PNG')
        svc.asset_cache._store(svc.asset_cache.register_url(skill_icon),output.getvalue())
    identity=QqIdentity('app','group','fixture-group','fixture-sender')
    with svc.bindings.store.connect(write=True) as db:db.execute("INSERT INTO users(user_id,username,password_hash) VALUES('u','fixture','fixture')")
    svc.bindings.redeem_link_code(identity,svc.bindings.create_link_code(Principal('u',False))['code'],'fixture-binding')
    renderer=svc.render_queue.renderer
    captured=[];original=Page.evaluate
    async def evaluate(page,expression,*args,**kwargs):
        value=await original(page,expression,*args,**kwargs)
        if expression=='window.__LONG_RENDER_STATE__':
            captured.append({'state':value,'text':'\n'.join(await page.locator('.lab-sheet').all_inner_texts()),
                'sheet_count':await page.locator('.lab-sheet').count(),
                'forbidden_requests':list(renderer._a_forbidden),
                'layout':await original(page,"""() => {
                    const box = element => {
                        const rect = element.getBoundingClientRect();
                        return {x:rect.x,y:rect.y,right:rect.right,bottom:rect.bottom,width:rect.width,height:rect.height};
                    };
                    return {
                        skills:[...document.querySelectorAll('.skill-art')].map(element => ({
                            artwork:box(element.querySelector('.endfield-artwork')),
                            level:box(element.querySelector('.skill-level')),
                            level_font:getComputedStyle(element.querySelector('.skill-level')).fontSize,
                            images:element.querySelectorAll('img').length,
                        })),
                        rows:[...document.querySelectorAll('.endfield-gacha .pool-detail .pull-row')].map(element => ({
                            row:box(element),track:box(element.querySelector('.pull-track')),
                            value:element.querySelector('.pull-value').innerText.replace(/\\s+/g,' ').trim(),
                            value_font:getComputedStyle(element.querySelector('.pull-value')).fontSize,
                            fill_width:element.querySelector('.pull-fill').getBoundingClientRect().width,
                        })),
                        pools:[...document.querySelectorAll('.endfield-gacha .pool-detail .detail-head h3')].map(element => element.innerText),
                    };
                }""")})
        return value
    monkeypatch.setattr(Page,'evaluate',evaluate)
    svc.asset_cache.prefetch=__import__('unittest.mock',fromlist=['AsyncMock']).AsyncMock()
    http=httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1234)))
    internal=InternalQqClient('http://127.0.0.1:8020','fixture-service',internal_host='cloud.example',http=http,images_enabled=True)
    try:
        from datetime import timedelta,timezone
        now=datetime.now(timezone.utc)
        raw='终末地 干员 佩丽卡' if role_name else {'roster':'终末地 角色','exploration':'终末地 探索','ship':'终末地 帝江号','honor':'终末地 光荣之路','combat':'终末地 挑战','gacha':'终末地 寻访战报'}[command]
        reply=await internal.execute(InboundMessage(identity,'synthetic-once',raw,now.isoformat(),(now+timedelta(minutes=5)).isoformat()))
        # Synthetic-only diagnostics are captured before the rejected page is
        # recycled. A text fallback must still fail the image contract.
        diagnostic={'command':command,'reply_type':type(reply).__name__,
            'reply_text':getattr(reply,'text',reply),'state':renderer.last_state,
            'capture':captured[-1] if captured else None}
        (tmp_path/'a-render-diagnostic.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8')
        assert getattr(reply,'image',None) is not None,json.dumps(diagnostic,ensure_ascii=False)
        assert renderer.template=='a' and captured[-1]['sheet_count']==1
        with Image.open(BytesIO(reply.image)) as picture:
            assert picture.width==1080 and 0<picture.height<=16000
            assert picture.width*picture.height<=renderer.max_pixels
            assert (picture.width,picture.height)==(renderer.last_state['width'],renderer.last_state['height'])
        assert len(reply.image)<=min(renderer.max_bytes,internal.max_image_bytes)
        state=renderer.last_state
        assert state['state']=='ready' and not state['overflow'] and state['layout_issues']==0 and state['bad_names']==0
        assert not captured[-1]['forbidden_requests']
        text=captured[-1]['text']
        if command=='roster':assert '合成干员34' in text and '35' in text
        elif command=='honor':assert '奖章33' in text and '类别16' in text
        elif command=='gacha':
            assert '合成池16' in text and all(f'合成池{i}' in text for i in range(17))
            assert '本图卡池' not in text and '内容已省略' not in text
            layout=captured[-1]['layout'];rows=layout['rows']
            assert layout['pools']==[f'合成池{i}' for i in range(17)] and len(rows)==51
            # Each pool prints 58 exact, ≥61 and an unknown interval on one 70-pull ruler.
            assert [row['value'] for row in rows]==['58抽','≥61抽','抽数未知']*17
            assert all(row['value_font']=='26px' for row in rows)
            fills=[row['fill_width']/row['track']['width'] for row in rows]
            assert all(abs(fill-58/70)<.01 for fill in fills[0::3]) and all(abs(fill-61/70)<.01 for fill in fills[1::3])
            assert all(fill==0 for fill in fills[2::3])
            # Images print 6★ history three cards to a row, each with a readable bar.
            assert all(len({round(row['row']['y']) for row in rows[i:i+3]})==1 for i in range(0,len(rows),3))
            assert min(row['track']['width'] for row in rows)>=200
        elif command=='combat':
            assert all(label+'观测时间' in text for label in ('战争','丰碑','危机'))
            assert all(moment in text for moment in ('2026-10-14 09:30','2026-10-14 10:30','2026-10-14 11:30'))
            assert '已有资料待更新' in text
        elif command in ('roles','roles_icon'):
            assert '已观测详情武器' in text and '佩丽卡' in text and '已观测详情战技' in text
            skills=captured[-1]['layout']['skills'];assert len(skills)==1
            assert skills[0]['images']==int(command=='roles_icon')
            assert skills[0]['level_font']=='26px'
            assert skills[0]['level']['y']>=skills[0]['artwork']['bottom']+7
        elif command=='ship':assert '0%' in text and '未知' in text
        elif command=='exploration':
            assert '四号谷地' in text and '武陵' in text and '地区数 2' in text
            assert all(label in text for label in ('宝箱','醚质','协议采录桩','装备制造模板','维修灵感点'))
        assert len(renderer._browser.contexts)==1 and renderer._a_context is renderer._browser.contexts[0]
        assert await renderer._a_page.locator('#app').inner_html()=='' and renderer._a_images=={}
        assert query.refreshes==[]
    finally:
        await http.aclose();await svc.aclose();scoped.close()
        assert renderer._browser is None and renderer._a_context is None and renderer._a_page is None
