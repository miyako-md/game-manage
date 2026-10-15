"""Long-card query contract and safe time/media boundaries."""
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from game_assistant.accounts.models import QueryResult
from game_assistant.qq import presentation
from game_assistant.qq.query_routes import QqQueryService
from tests.test_qq_unified_queries import CachedQuery, IDENTITY, service, no_external_network
from game_assistant.identity.models import Principal


@pytest.mark.parametrize('value,expected',[
    ('2026-10-14T00:02:03Z','2026-10-14 08:02'),
    ('2026-10-14T08:02:03+08:00','2026-10-14 08:02'),
    ('2026-10-14T00:02:03','2026-10-14 08:02'),
    ('2026-10-14 08:02','2026-10-14 08:02'),
    (1791936123,'2026-10-14 08:02'),(1791936123000,'2026-10-14 08:02'),
    (None,'未知'),(False,'未知'),('not a date','未知'),(float('nan'),'未知'),
])
def test_beijing_minute_timestamp_formatter(value,expected):
    assert presentation.format_time(value)==expected


def test_forty_character_card_contains_all_rows_no_default_pagination():
    query=CachedQuery()
    query.add('wuthering_waves','kuro','ww',{'roles':[
        {'name':f'角色{i}','level':i,'attribute':'衍射'*12,'chain':0,'icon_url':f'https://web-static.kurobbs.com/role/{i}.png'} for i in range(46)]})
    context={}
    response=service(query).query(IDENTITY,'roles','wuthering_waves',image_context=context)
    card=context['card']
    assert card['version']==3 and 'page' not in card
    assert len(card['sections'][0]['rows'])==46
    assert card['sections'][0]['rows'][-1]['title']=='角色45'
    assert card['sections'][0]['layout']=='grid'
    assert len(response['text'])<=1800
    assert '文字摘要' in response['text'] and '2026-10-14 08:00' in response['text']


def test_legacy_page_requests_return_complete_longcard_with_compatibility_notice():
    query=CachedQuery()
    query.add('nte','tajiduo','n',{'roles':{'entries':[{'name':f'角色{i}','level':None} for i in range(45)]}})
    context={}
    result=service(query).query(IDENTITY,'roles','nte',page=2,image_context=context)
    assert '长图' in result['text']
    assert 'page' not in context['card'] and len(context['card']['sections'][0]['rows'])==45


def test_time_projection_only_changes_time_fields_and_keeps_unknown_metrics():
    query=CachedQuery()
    query.add('nte','tajiduo','n',{'stamina':{'current':None,'maximum':100,'expected_full_at':'2026-10-14T01:23:45Z',
        'city_current':0,'city_maximum':20}})
    context={}
    result=service(query).query(IDENTITY,'stamina','nte',image_context=context)
    fields=context['card']['sections'][0]['fields']
    stamina=next(item for item in fields if item['label']=='体力')
    assert stamina['metric']=={'current':None,'maximum':100}
    assert '未知/100' in result['text'] and '2026-10-14 09:23' in result['text'] and 'Z' not in result['text']
    assert presentation.text('角色2026-10-14T01:23:45Z')=='角色2026-10-14T01:23:45Z'


def test_detail_keeps_all_skills_weapon_and_equipment_on_one_document():
    query=CachedQuery()
    query.add('nte','tajiduo','n',{'roles':{'entries':[{'id':'1001','name':'娜娜莉','level':70,
        'icon_url':'https://webstatic.tajiduo.com/character/1001.png','weapon':{'name':'弧盘','level':60},
        'skills':[{'name':f'技能{i}','level':5} for i in range(15)],
        'properties':[{'name':f'属性{i}','value':str(i)} for i in range(20)]}]}})
    context={}
    service(query).query(IDENTITY,'roles','nte',role_name='娜娜莉',image_context=context)
    card=context['card']
    assert card['version']==3 and 'page' not in card
    assert len(next(section for section in card['sections'] if section['title']=='技能')['rows'])==15
    assert len(next(section for section in card['sections'] if section['title']=='缓存属性')['fields'])==20
    assert next(section for section in card['sections'] if '武器' in section['title'])['layout']=='equipment'


def test_transport_media_validator_accepts_decodable_png_jpeg_and_rejects_fake_or_oversized():
    from game_assistant.qq.client import valid_reply_image
    image=Image.new('RGB',(100,200),'navy')
    for format_ in ('PNG','JPEG'):
        output=BytesIO();image.save(output,format=format_)
        assert valid_reply_image(output.getvalue(),max_bytes=1048576)
    assert not valid_reply_image(b'\x89PNG\r\n\x1a\nfixture',max_bytes=1048576)
    assert not valid_reply_image(b'\xff\xd8\xfffixture',max_bytes=1048576)
    assert not valid_reply_image(b'anything',max_bytes=1048576)


@pytest.fixture
def offline_assets(monkeypatch):
    from game_assistant.qq import assets
    image=Image.new('RGBA',(72,72),(120,180,250,255));output=BytesIO();image.save(output,format='PNG')
    async def download(*args,**kwargs):return output.getvalue()
    monkeypatch.setattr(assets,'_download',download)
    return assets.PublicAssetCache()


def test_source_icons_become_opaque_refs_and_same_card_keeps_complete_rows(offline_assets):
    query=CachedQuery()
    query.add('wuthering_waves','kuro','ww',{'roles':[{'role_id':1101,'name':'今汐','level':80,
        'icon_url':'https://web-static.kurobbs.com/role/1101.png','extra':{'token':'private'}}]})
    api=QqQueryService(SimpleNamespace(resolve_qq_identity=lambda i:Principal('u',False)),query,None,asset_cache=offline_assets)
    context={};api.query(IDENTITY,'roles','wuthering_waves',image_context=context)
    card=context['card']
    assert card['sections'][0]['rows'][0]['image'].startswith('qqasset_')
    assert 'https://' not in str(card) and 'private' not in str(card)
    sections=presentation.wuwa_detail_sections({'weapon_data':{'weapon':{'weapon_name':'武器','weapon_icon':'https://web-static.kurobbs.com/weapon.png'}},
        'skill_list':[{'skill':{'name':'技能','icon_url':'https://web-static.kurobbs.com/skill.png'},'level':8}],
        'phantom_data':{'equip_phantom_list':[{'phantom_prop':{'name':'声骸','icon_url':'https://web-static.kurobbs.com/echo.png'}}]}},offline_assets)
    assert next(s for s in sections if '武器' in s['title'])['image'].startswith('qqasset_')
    assert next(s for s in sections if s['title']=='技能')['rows'][0]['image'].startswith('qqasset_')
    assert next(s for s in sections if s['title'].startswith('声骸 ·'))['image'].startswith('qqasset_')


@pytest.mark.parametrize('event',['revoke','unlink'])
async def test_asset_preparation_cannot_release_private_text_when_authorization_changes(event):
    from game_assistant.qq.bindings import QqBindingError
    query=CachedQuery();query.add('nte','tajiduo','n',{'account':{'nickname':'PRIVATE'}})
    linked=[True]
    def resolve(identity):
        if not linked[0]:raise QqBindingError('qq_link_required',403)
        return Principal('u',False)
    budgets=[]
    class Assets:
        def ref_for(self,*args):return 'qqasset_'+'a'*64
        async def prefetch(self,refs,*,budget_seconds):
            budgets.append(budget_seconds)
            if event=='revoke':query.versions['n']=None
            else:linked[0]=False
    class Queue:
        renderer=SimpleNamespace(invalidate_account=lambda *args:None)
        async def render(self,scope,result,*,budget_seconds):
            budgets.append(budget_seconds)
            # Public asset preparation now belongs to the web renderer.
            await assets.prefetch((),budget_seconds=budget_seconds)
            return None
    assets=Assets()
    api=QqQueryService(SimpleNamespace(resolve_qq_identity=resolve),query,None,asset_cache=assets,render_queue=Queue())
    result=await api.query_reply(IDENTITY,'overview',image_requested=True,budget_seconds=3)
    assert 'PRIVATE' not in result['text'] and '变更' in result['text']
    assert len(budgets)==2 and all(0<=budget<=3 for budget in budgets)


async def test_failed_render_text_is_complete_labelled_summary_with_source_timestamp():
    query=CachedQuery()
    query.add('nte','tajiduo','n',{'roles':{'entries':[{'name':'角色'*8+str(i),'level':None} for i in range(90)]}})
    class Queue:
        renderer=SimpleNamespace(invalidate_account=lambda *args:None)
        async def render(self,*args,**kwargs):return None
    result=await service(query,queue=Queue()).query_reply(IDENTITY,'roles','nte',image_requested=True,budget_seconds=2)
    assert '图片暂不可用' in result['text'] and '文字摘要' in result['text'] and '2026-10-14 08:00' in result['text']
    assert len(result['text'])<=1800 and 'image' not in result


async def test_text_fallback_does_not_mutate_inflight_renderer_document():
    from copy import deepcopy
    query=CachedQuery();query.add('nte','tajiduo','n',{'account':{'nickname':'玩家'}})
    retained=[]
    class Queue:
        renderer=SimpleNamespace(invalidate_account=lambda *args:None)
        async def render(self,scope,result,**kwargs):
            # A timed-out CPU worker can retain this exact result after returning None.
            retained.append((result,deepcopy(result.payload['card'])))
            return None
    response=await service(query,queue=Queue()).query_reply(IDENTITY,'summary','nte',image_requested=True,budget_seconds=2)
    result,original=retained[0]
    assert result.payload['card']==original
    assert not any('图片暂不可用' in notice for notice in result.payload['card']['notices'])
    assert '图片暂不可用' in response['text']


@pytest.mark.parametrize('has_queue,budget',[(False,5),(True,0)])
async def test_disabled_renderer_or_exhausted_budget_explicitly_labels_text_fallback(has_queue,budget):
    query=CachedQuery();query.add('nte','tajiduo','n',{'account':{'nickname':'玩家'}})
    class Queue:
        renderer=SimpleNamespace(invalidate_account=lambda *args:None)
        async def render(self,*args,**kwargs):pytest.fail('No image budget remains')
    api=service(query,queue=Queue() if has_queue else None)
    response=await api.query_reply(IDENTITY,'summary','nte',image_requested=True,budget_seconds=budget)
    assert '图片暂不可用' in response['text'] and '2026-10-14 08:00' in response['text']


async def test_jpeg_internal_reply_is_verified_then_accepted_without_other_format():
    import base64
    import httpx
    from datetime import datetime,timedelta,timezone
    from game_assistant.qq.client import InternalQqClient,QqReply
    from game_assistant.qq.models import InboundMessage
    output=BytesIO();Image.new('RGB',(40,200),'navy').save(output,format='JPEG')
    http=httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'text':'长图摘要',
        'image':base64.b64encode(output.getvalue()).decode()})))
    api=InternalQqClient('http://127.0.0.1:8020','fixture',http=http,images_enabled=True,max_image_bytes=1048576)
    now=datetime.now(timezone.utc)
    reply=await api.execute(InboundMessage(IDENTITY,'m','鸣潮',now.isoformat(),(now+timedelta(minutes=5)).isoformat()))
    assert isinstance(reply,QqReply) and reply.image==output.getvalue()
    await http.aclose()


def test_summary_uses_existing_role_grid_without_inventing_private_fetches():
    query=CachedQuery()
    query.add('nte','tajiduo','n',{'account':{'nickname':'玩家'},'roles':{'entries':[{'name':f'角色{i}','level':None} for i in range(46)]}})
    context={};service(query).query(IDENTITY,'summary','nte',image_context=context)
    grid=next(section for section in context['card']['sections'] if section.get('layout')=='grid')
    assert len(grid['rows'])==46
    assert {cap for scope,cap in query.reads}=={'account','roles'}


def test_long_document_hard_limits_mark_omissions_without_reintroducing_pages():
    query=CachedQuery()
    query.add('nte','tajiduo','n',{'roles':{'entries':[{'name':f'角色{i}','level':None} for i in range(300)]}})
    context={};service(query).query(IDENTITY,'roles','nte',image_context=context)
    card=context['card']
    assert len(card['sections'][0]['rows'])==256 and 'page' not in card
    assert any('上限' in notice and '省略' in notice for notice in card['notices'])
