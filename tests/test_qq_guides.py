from datetime import datetime
import json
import pytest
from game_assistant.qq.commands import parse_command
from game_assistant.qq.guides import reply
from game_assistant.qq.browser_rendering import validate_snapshot
from game_assistant.qq.render_snapshot import asset_requests
from game_assistant.qq.query_routes import QqQueryService
from game_assistant.qq.models import QqIdentity
from game_assistant.qq.rendering import RenderingUnavailable

@pytest.mark.parametrize('text,game,name',[
    ('攻略',None,None),('鸣潮 攻略','wuthering_waves',None),
    ('鸣潮 攻略 散华','wuthering_waves','散华'),
    ('异环 角色攻略 安魂曲','nte','安魂曲'),
    ('攻略 异环 黑羽','nte','黑羽'),('终末地 攻略 伊冯','endfield','伊冯'),
])
def test_guide_commands_are_explicit_public_catalog_queries(text,game,name):
    command=parse_command(text)
    assert (command.command,command.game,command.role_name)==('guide',game,name)

def test_guide_names_and_pages_do_not_accept_other_selectors():
    for text in ['攻略 散华','鸣潮 攻略 散华 other-account','鸣潮 攻略 散华 2']:
        assert parse_command(text).command=='help'

@pytest.mark.parametrize('game,name,kind',[('wuthering_waves','散华','guide'),('nte','安魂曲','guide'),('nte','黑羽','guide'),('endfield',None,'notice')])
def test_guides_use_public_catalog_without_bindings_or_live_accounts(game,name,kind):
    class NoBindings:
        def resolve_qq_identity(self,*args):raise AssertionError('public guide must not read bindings')
    context={};service=QqQueryService(NoBindings(),None,None,clock=lambda:datetime.fromisoformat('2026-10-18T16:30:00+08:00'))
    service.query(QqIdentity('app','group','group','sender'),'guide',game,role_name=name,image_context=context)
    snapshot=context['render_snapshot']
    assert snapshot['kind']==kind and validate_snapshot(snapshot)==snapshot
    assert context['user_id'] is None and not context['grants']
    assert '攻略' in snapshot['next_command']
    assert list(asset_requests(snapshot))

def test_guide_display_still_rejects_private_fields_and_arbitrary_keys():
    _,snapshot=reply('wuthering_waves','散华',datetime.fromisoformat('2026-10-18T00:00:00+08:00'))
    snapshot['display_data']['guide']['user_id']='private'
    with pytest.raises(RenderingUnavailable):validate_snapshot(snapshot)

@pytest.mark.parametrize('game,text',[
    (None,'请发送「鸣潮 攻略 角色名」或「异环 攻略 角色名」查看单个角色攻略；可用角色见网站攻略页。'),
    ('wuthering_waves','请发送「鸣潮 攻略 角色名」查看单个角色攻略；可用角色见网站攻略页。'),
    ('nte','请发送「异环 攻略 角色名」查看单个角色攻略；可用角色见网站攻略页。'),
    ('endfield','暂未收录可核验的终末地角色攻略；可在 B 站搜索 猫冬MT「终末地攻略合集」。'),
])
def test_bare_guide_is_a_text_notice_instead_of_an_index_image(game,text):
    from game_assistant.qq.cards import card_to_text
    card,snapshot=reply(game,None,datetime.fromisoformat('2026-10-18T00:00:00+08:00'))
    assert snapshot['kind']=='notice' and validate_snapshot(snapshot)==snapshot
    assert snapshot['display_data']['sections']==[] and snapshot['display_data']['notices']==[text]
    assert text in card_to_text(card)
    index={**snapshot,'kind':'guide_index','display_data':{'guides':[]}}
    with pytest.raises(RenderingUnavailable):validate_snapshot(index)

def test_missing_sources_are_explicit():
    card,missing=reply('endfield','伊冯',datetime.fromisoformat('2026-10-18T00:00:00+08:00'))
    assert missing['kind']=='notice' and '暂未收录' in str(card)

def test_guide_missing_source_version_stays_null_instead_of_vnone():
    now=datetime.fromisoformat('2026-10-18T00:00:00+08:00')
    _,snapshot=reply('wuthering_waves','赞妮',now)
    sources=snapshot['display_data']['guide']['sources']
    assert [source['version'] for source in sources]==['3.2',None]
    assert 'None' not in json.dumps(snapshot,ensure_ascii=False)


# --- Cache-only overlay of the shared guide services (fakes with the contract shapes) ---
import os
import sqlite3
from pathlib import Path
from game_assistant.qq.cards import card_to_text
from game_assistant.qq.guides import GuideSources

NOW=datetime.fromisoformat('2026-10-22T08:00:00+08:00')
STATIC_POST='1482734021209260032'
NEW_POST='1555005846752059392'
PRIVATE_KEYS={'images','fingerprint','fetchedAt','ruleVersion','evidence','locator','candidates','author_id','error_code','checked_at'}

def candidate(post,author_id='10525366',kind='article'):
    return {'id':post,'title':'V3.7 培养攻略','author':'作者','author_id':author_id,'version':'3.7','published_at':'2026-10-20T00:00:00+00:00',
            'kind':kind,'url':'https://www.kurobbs.com/forum/post/'+post,'status':'unreviewed'}

def live(character_id,name,attribute,post,status='extracted',images=6):
    sections=[{'key':key,'text':'' if key=='skill_priority' and status!='reviewed' else '示例建议'+key,
               'status':status if key!='skill_priority' or status=='reviewed' else 'pending',
               'sourceId':post,'locator':'正文第 1 段','note':'自动提炼，待核对原帖；适用条件按来源保留。','evidence':[{'kind':'text','position':1}]}
              for key in ('weapons','teams','echo_sets','echo_stats','skill_priority')]
    return {'id':character_id,'name':name,'attribute':attribute,'sections':sections,'sourceId':post,
            'sources':[{'id':post,'title':'V3.7 示例攻略','author':'作者','version':'3.7','url':'https://www.kurobbs.com/forum/post/'+post,'kind':'article','publishedAt':None}],
            'fetchedAt':'2026-10-21T21:30:00+00:00','reviewedAt':None,'fingerprint':'f'*64,'ruleVersion':1,
            'images':[{'page':i,'url':f'https://prod-alicdn-community.kurobbs.com/forum/{i}.png'} for i in range(1,images+1)],'extractionNote':None}

def check(character_id,name,attribute,candidates=(),active=None,checked_at='2026-10-21T21:31:00+00:00'):
    return {'character_id':character_id,'name':name,'attribute':attribute,'candidates':list(candidates),'checked_at':checked_at,
            'attempted_at':checked_at,'error':None,'error_code':None,'limited':False,'active_guide':active,'extraction_error':None}

class FakeWuwa:
    def __init__(self,rows):self.rows,self.calls=rows,[]
    def cached_by_id(self,character_id):
        self.calls.append(character_id);return self.rows.get(character_id)
    async def check(self,*args,**kwargs):raise AssertionError('QQ must not search upstream')

class FakeNte:
    def __init__(self,status,images=None):self.value,self.images=status,images
    def status(self,post_id):return self.value.get(post_id)
    def cached(self,post_id):return None if self.images is None else {'id':post_id,'images':[{'url':'https://example.invalid/x.png'}]*self.images}
    async def read(self,*args,**kwargs):raise AssertionError('QQ must not read upstream')

@pytest.fixture
def roster(monkeypatch):
    monkeypatch.setattr('game_assistant.guide_jobs.guide_roster',lambda:[
        {'character_id':'1102','name':'散华','attribute':'冷凝','static':True},
        {'character_id':'1311','name':'心','attribute':'','static':False}])

def guide_of(snapshot):
    assert snapshot['kind']=='guide' and validate_snapshot(snapshot)==snapshot
    return snapshot['display_data']['guide']

def keys_of(guide):
    return set(guide)|{key for section in guide['sections'] for key in section}|{key for source in guide['sources'] for key in source}

def test_static_wuwa_guide_gains_one_pending_line_for_an_unreviewed_new_post():
    service=FakeWuwa({'1102':check('1102','散华','冷凝',[candidate(NEW_POST),candidate(STATIC_POST,'1')])})
    card,snapshot=reply('wuthering_waves','散华',NOW,sources=GuideSources(service))
    guide=guide_of(snapshot)
    static=guide_of(reply('wuthering_waves','散华',NOW)[1])
    assert guide['sections']==static['sections'] and guide['asset_hints']==static['asset_hints']
    assert guide['freshness']=={'mark':None,'lines':['库街区有新攻略帖，待核查（检查于 2026-10-22 05:31）']}
    assert '库街区有新攻略帖' in card_to_text(card) and service.calls==['1102']

def test_static_wuwa_guide_without_a_new_post_only_shows_the_check_time():
    for rows in ({'1102':check('1102','散华','冷凝',[candidate(STATIC_POST)])},
                 # A video or a stored extraction of the static post itself is not a new post.
                 {'1102':check('1102','散华','冷凝',[candidate(NEW_POST,kind='video'),candidate(STATIC_POST)],live('1102','散华','冷凝',STATIC_POST))}):
        guide=guide_of(reply('wuthering_waves','散华',NOW,sources=GuideSources(FakeWuwa(rows)))[1])
        assert guide['freshness']=={'mark':None,'lines':['攻略检查于 2026-10-22 05:31']}
        assert '自动提炼' not in json.dumps(guide,ensure_ascii=False)

def test_unknown_check_time_is_omitted_instead_of_invented():
    rows={'1102':check('1102','散华','冷凝',[candidate(NEW_POST)],checked_at=None)}
    guide=guide_of(reply('wuthering_waves','散华',NOW,sources=GuideSources(FakeWuwa(rows)))[1])
    assert guide['freshness']['lines']==['库街区有新攻略帖，待核查']

def test_static_wuwa_guide_keeps_static_sections_until_all_five_live_sections_are_reviewed():
    draft=live('1102','散华','冷凝',NEW_POST)
    guide=guide_of(reply('wuthering_waves','散华',NOW,sources=GuideSources(FakeWuwa({'1102':check('1102','散华','冷凝',[candidate(NEW_POST)],draft)})))[1])
    assert guide['sources'][0]['id']==STATIC_POST and '示例建议' not in json.dumps(guide,ensure_ascii=False)
    assert guide['freshness']['lines'][0].startswith('库街区有新攻略帖，待核查')
    reviewed=live('1102','散华','冷凝',NEW_POST,status='reviewed')
    guide=guide_of(reply('wuthering_waves','散华',NOW,sources=GuideSources(FakeWuwa({'1102':check('1102','散华','冷凝',[candidate(NEW_POST)],reviewed)})))[1])
    assert [s['id'] for s in guide['sources']]==[NEW_POST] and guide['sections'][0]['text']=='示例建议weapons'
    assert [s['title'] for s in guide['sections']][:2]==['武器推荐','配队推荐'] and guide['asset_hints']
    assert guide['freshness']=={'mark':None,'lines':['攻略检查于 2026-10-22 05:31','原帖共 6 张图，可在网站攻略页「查看原帖」查看']}
    assert not PRIVATE_KEYS&keys_of(guide)

def test_wuwa_role_without_static_entry_shows_the_live_draft_marked_for_review(roster):
    draft=live('1311','心','导电',NEW_POST,images=10)
    card,snapshot=reply('wuthering_waves','心',NOW,sources=GuideSources(FakeWuwa({'1311':check('1311','心','导电',[candidate(NEW_POST)],draft)})))
    guide=guide_of(snapshot)
    assert guide['freshness']['mark']=='自动提炼·待校对' and snapshot['title'].endswith('心 · 自动提炼·待校对')
    assert guide['freshness']['lines']==['攻略检查于 2026-10-22 05:31','原帖至少 10 张图，可在网站攻略页「查看原帖」查看']
    assert guide['id']=='1311' and guide['asset_hints'] and len(guide['sections'])==5  # role image at least
    assert guide['sections'][4]['title']=='技能加点优先级' and guide['sections'][4]['text']==''
    assert all('待核对' in s['note'] for s in guide['sections'])
    assert not PRIVATE_KEYS&keys_of(guide)
    text=card_to_text(card)
    assert '自动提炼·待校对' in text and '未经人工核对' in text

def test_wuwa_role_without_static_entry_and_a_reviewed_extraction_is_not_marked_as_draft(roster):
    reviewed=live('1311','心','导电',NEW_POST,status='reviewed')
    card,snapshot=reply('wuthering_waves','心',NOW,sources=GuideSources(FakeWuwa({'1311':check('1311','心','导电',[candidate(NEW_POST)],reviewed)})))
    guide=guide_of(snapshot)
    assert guide['freshness']['mark'] is None and not snapshot['title'].endswith('待校对')
    assert '未经人工核对' not in card_to_text(card)

def test_new_role_draft_needs_a_roster_entry_and_a_stored_extraction(roster):
    for rows in ({},{'1311':check('1311','心','导电',[candidate(NEW_POST)])}):
        _,snapshot=reply('wuthering_waves','心',NOW,sources=GuideSources(FakeWuwa(rows)))
        assert snapshot['kind']=='notice' and '尚未收录' in json.dumps(snapshot,ensure_ascii=False)
    assert reply('wuthering_waves','心',NOW)[1]['kind']=='notice'

def test_nte_guide_overlays_summary_change_check_time_and_source_images():
    status={491439:{'fetched_at':'2026-10-21T22:00:00+00:00','summary_changed':True,'stale':False,'error':False}}
    card,snapshot=reply('nte','安魂曲',NOW,sources=GuideSources(None,FakeNte(status,images=12)))
    guide=guide_of(snapshot)
    assert guide['sections']==guide_of(reply('nte','安魂曲',NOW)[1])['sections']
    assert guide['freshness']=={'mark':None,'lines':['原帖有更新，摘要待复核','攻略检查于 2026-10-22 06:00','原帖共 12 张图，可在网站「原图与来源」查看']}
    assert '摘要待复核' in card_to_text(card)
    status[491439].update(summary_changed=False)
    guide=guide_of(reply('nte','安魂曲',NOW,sources=GuideSources(None,FakeNte(status)))[1])
    assert guide['freshness']['lines']==['攻略检查于 2026-10-22 06:00']

@pytest.mark.parametrize('sources',[None,GuideSources(),GuideSources(object(),object()),GuideSources(FakeWuwa({}),FakeNte({}))])
def test_unavailable_or_unchecked_services_keep_todays_static_reply(sources):
    for game,name in (('wuthering_waves','散华'),('nte','安魂曲'),('nte','黑羽'),('wuthering_waves','赞妮')):
        assert reply(game,name,NOW,sources=sources)==reply(game,name,NOW)
        assert 'freshness' not in reply(game,name,NOW,sources=sources)[1]['display_data']['guide']

def test_service_errors_fall_back_to_the_static_reply():
    class Broken:
        def cached_by_id(self,character_id):raise sqlite3.OperationalError('locked')
        def status(self,post_id):raise sqlite3.OperationalError('locked')
    assert reply('wuthering_waves','散华',NOW,sources=GuideSources(Broken(),Broken()))==reply('wuthering_waves','散华',NOW)
    assert reply('nte','安魂曲',NOW,sources=GuideSources(Broken(),Broken()))==reply('nte','安魂曲',NOW)

def test_live_state_is_read_on_every_reply_not_cached():
    rows={'1102':check('1102','散华','冷凝',[candidate(STATIC_POST)])}
    service=FakeWuwa(rows);sources=GuideSources(service)
    assert guide_of(reply('wuthering_waves','散华',NOW,sources=sources)[1])['freshness']['lines']==['攻略检查于 2026-10-22 05:31']
    rows['1102']=check('1102','散华','冷凝',[candidate(NEW_POST)])
    assert guide_of(reply('wuthering_waves','散华',NOW,sources=sources)[1])['freshness']['lines'][0].startswith('库街区有新攻略帖')
    assert service.calls==['1102','1102']

def test_freshness_is_whitelisted_short_text_only():
    service=FakeWuwa({'1102':check('1102','散华','冷凝',[candidate(NEW_POST)])})
    _,snapshot=reply('wuthering_waves','散华',NOW,sources=GuideSources(service))
    for bad in ({'mark':None,'lines':['x']*5},{'mark':None,'lines':['x'*121]},{'mark':None,'lines':[1]},
                {'mark':None,'lines':[],'user_id':'1'},{'mark':'x'*33,'lines':[]},['x']):
        copy=json.loads(json.dumps(snapshot));copy['display_data']['guide']['freshness']=bad
        with pytest.raises(RenderingUnavailable):validate_snapshot(copy)

def test_endfield_guide_names_the_external_source_without_a_link():
    text='暂未收录可核验的终末地角色攻略；可在 B 站搜索 猫冬MT「终末地攻略合集」。'
    for name in (None,'伊冯'):
        card,snapshot=reply('endfield',name,NOW,sources=GuideSources(FakeWuwa({}),FakeNte({})))
        assert snapshot['kind']=='notice' and snapshot['display_data']['notices']==[text]
        assert text in card_to_text(card) and 'http' not in json.dumps(snapshot['display_data'],ensure_ascii=False)

def test_query_service_passes_its_guide_sources_without_bindings():
    class NoBindings:
        def resolve_qq_identity(self,*args):raise AssertionError('public guide must not read bindings')
    service=FakeWuwa({'1102':check('1102','散华','冷凝',[candidate(NEW_POST)])})
    context={};query=QqQueryService(NoBindings(),None,None,clock=lambda:NOW,guides=GuideSources(service))
    query.query(QqIdentity('app','group','group','sender'),'guide','wuthering_waves',role_name='散华',image_context=context)
    assert context['render_snapshot']['display_data']['guide']['freshness']['lines'][0].startswith('库街区有新攻略帖')
    assert context['user_id'] is None and not context['grants']

def test_install_reads_the_shared_guide_services_only_when_present():
    from types import SimpleNamespace
    from fastapi import FastAPI
    from game_assistant.qq.query_routes import install_qq_query_routes
    for wuwa,nte in ((None,None),(FakeWuwa({}),None),(None,FakeNte({}))):
        app=FastAPI()
        app.state.settings=SimpleNamespace(cloud_data_root='',qq_images_enabled=False)
        app.state.qq_bindings=object();app.state.cloud_route_policy=[]
        if wuwa is not None:app.state.wuwa_guide_updates=wuwa
        if nte is not None:app.state.nte_guides=nte
        service=install_qq_query_routes(app,app_id='app')
        if wuwa is None and nte is None:assert service.guides is None
        else:assert service.guides.wuwa is wuwa and service.guides.nte is nte


@pytest.mark.parametrize('case',['wuwa_pending','wuwa_draft','nte_changed','endfield'])
async def test_real_guide_freshness_renders_clean_images(case,tmp_path,roster):
    from io import BytesIO
    from PIL import Image
    from game_assistant.accounts.models import AccountScope,QueryResult
    from game_assistant.qq.browser_rendering import BrowserRenderer
    executable=os.environ.get('QQ_RENDER_TEST_EXECUTABLE');font=os.environ.get('QQ_RENDER_TEST_FONT')
    if not executable or not font:pytest.skip('Set isolated Chromium/font paths for native acceptance')
    wuwa=FakeWuwa({'1102':check('1102','散华','冷凝',[candidate(NEW_POST)]),
                   '1311':check('1311','心','导电',[candidate(NEW_POST)],live('1311','心','导电',NEW_POST))})
    nte=FakeNte({491439:{'fetched_at':'2026-10-21T22:00:00+00:00','summary_changed':True,'stale':False,'error':False}},images=12)
    game,name={'wuwa_pending':('wuthering_waves','散华'),'wuwa_draft':('wuthering_waves','心'),'nte_changed':('nte','安魂曲'),'endfield':('endfield',None)}[case]
    renderer=BrowserRenderer(template='a',executable_path=executable,font_path=font,dist_path=os.environ.get('QQ_RENDER_TEST_DIST',''))
    out=Path(os.environ.get('QQ_GUIDE_RENDER_OUT') or tmp_path);out.mkdir(parents=True,exist_ok=True)
    try:
        page=1
        while True:
            _,snap=reply(game,name,NOW,page,sources=GuideSources(wuwa,nte))
            value=QueryResult({'text':'合成检查','render_snapshot':snap,'snapshot_fingerprints':['a'*64]},NOW.isoformat(),'ok',True)
            image=await renderer.render_summary_async(AccountScope('fixture','account','role'),value,budget_seconds=10)
            state=renderer.last_state
            assert state['state']=='ready' and not state['overflow'] and state['layout_issues']==0,state
            assert Image.open(BytesIO(image)).size[0]<=1080
            (out/f'guide-{case}-p{image.page}.png').write_bytes(bytes(image))
            if image.page>=image.total_pages:break
            page+=1
    finally:await renderer.aclose()


def test_live_wuwa_text_gets_the_icon_hints_the_static_export_would_give():
    from game_assistant.qq.guides import _wuwa_hints, catalog
    # Every static guide: the Python hints cover what the page's tokenizer exported for the same text.
    for row in catalog()['guides']['wuthering_waves']:
        guide={'id':row['id'],'image':row.get('image'),'sections':row['sections']}
        assert set(row['asset_hints'])<=set(_wuwa_hints(guide)),row['name']

def test_live_draft_carries_its_role_image_and_icon_hints(roster):
    draft=live('1311','心','导电',NEW_POST)
    for section in draft['sections']:
        if section['key']=='weapons':section['text']='首选玉阙玄华，四星可考虑今州守望。'
        if section['key']=='echo_stats':section['text']='副词条先满足共鸣效率，再按双暴。'
    _,snapshot=reply('wuthering_waves','心',NOW,sources=GuideSources(FakeWuwa({'1311':check('1311','心','导电',[candidate(NEW_POST)],draft)})))
    guide=guide_of(snapshot)
    from game_assistant.qq.public_asset_catalog import CATALOG
    icons=CATALOG['games']['wuthering_waves']
    assert guide['image']==icons['role']['心']
    assert {icons['weapon']['玉阙玄华'],icons['weapon']['今州守望'],icons['stat']['共鸣效率']}<=set(guide['asset_hints'])
    requested={url for url,_ in asset_requests(snapshot)}
    assert set(guide['asset_hints'])<=requested
