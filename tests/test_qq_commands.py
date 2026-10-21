from dataclasses import asdict
from types import SimpleNamespace

import pytest

from game_assistant.qq.commands import GAME_NAMES, parse_command, safe_text
from game_assistant.qq.models import QqIdentity
from game_assistant.qq.query_routes import QqQueryService
from game_assistant.accounts.models import QueryResult
from game_assistant.identity.models import Principal
from game_assistant.qq.bindings import QqBindingError

IDENTITY = QqIdentity('app','group','group','sender')


def test_commands_are_explicit_self_queries():
    for raw,command,game in [('/help','help',None),('绑定 CODE','binding',None),
                            ('我的账号','status',None),('/ww','summary','wuthering_waves'),
                            ('/yh','summary','nte'),('/endfield','summary','endfield'),
                            ('鸣潮角色','roles','wuthering_waves'),('活动 鸣潮','events','wuthering_waves'),
                            ('公告 异环','retired','nte'),('刷新 终末地','refresh','endfield'),('看板','dashboard',None)]:
        parsed=parse_command(raw)
        assert parsed.command==command and parsed.game==game
    for raw in ['/ww other-account','异环 123456789','刷新 异环 其他用户','/help https://secret.example']:
        assert parse_command(raw).command=='help'


@pytest.mark.parametrize('raw,command,game',[
    ('ww 查询','summary','wuthering_waves'),('yh 查询','summary','nte'),
    ('终末地 查询','summary','endfield'),('/ww 活动','events','wuthering_waves'),
    ('ww 日历','calendar','wuthering_waves'),('yh 刷新','refresh','nte'),
    ('ww 角色','roles','wuthering_waves'),
])
def test_game_first_command_aliases_remain_self_only(raw,command,game):
    parsed = parse_command(raw)
    assert parsed.command == command and parsed.game == game
    if command == 'roles':
        assert parse_command(raw+' own-role').role_name == 'own-role'
        assert parse_command(raw+' own-role other-user').command == 'help'
    else:
        assert parse_command(raw+' other-user').command == 'help'


@pytest.mark.parametrize('raw',['ww 角色 今汐','/鸣潮 角色 长离','wuthering_waves roles Shorekeeper'])
def test_named_role_filter_targets_own_cached_exact_name(raw):
    from game_assistant.qq.cards import card_to_text
    from game_assistant.qq.presentation import help_document
    parsed = parse_command(raw)
    assert parsed.command == 'roles' and parsed.game == 'wuthering_waves'
    assert parsed.role_name == raw.split()[-1]
    assert '鸣潮 角色 精确名称' in card_to_text(help_document('wuthering_waves'))


def test_named_role_filter_is_bounded_printable_and_roles_only():
    assert parse_command('ww 角色 '+'名'*64).role_name == '名'*64
    for raw in ('ww 角色 '+'名'*65,'ww 角色 名\x00字','ww 角色 名\x1f字','ww 角色 今汐 other-user',
                'ww 查询 今汐','ww 探索 今汐'):
        parsed = parse_command(raw)
        assert parsed.command == 'help' and parsed.role_name is None
    assert parse_command('ww 角色').role_name is None


def test_url_removed_when_not_approved():
    assert 'example' not in safe_text('网址 https://example.com/a 与 www.example.com、example.com',urls_approved=False)
    assert 'https://example.com' in safe_text('https://example.com',urls_approved=True)


def test_reply_masks_uid_preserves_null_and_failed_cache():
    import json
    from tests.test_qq_unified_queries import CachedQuery, service
    query=CachedQuery();query.add('nte','tajiduo','n',{})
    query.data[('n','account')]=QueryResult({'nickname':'User 123456789','level':None,'extra':{'uid':'123456789','token':'private-secret'}},'2026-10-12T00:00:00Z','error',False)
    context={};text=service(query).query(IDENTITY,'summary','nte',image_context=context)['text']
    assert '123456789' not in text and 'private-secret' not in text
    assert '等级：未知' in text and '显示旧快照' in text and '完整性：不完整' in text
    projected=json.dumps(context['render_snapshot'],ensure_ascii=False)
    assert '123456789' not in projected and 'private-secret' not in projected


def unbound_service():
    def resolve(identity):
        raise QqBindingError('qq_link_required',403)
    return QqQueryService(SimpleNamespace(resolve_qq_identity=resolve),None,None)


def test_unbound_user_gets_help_only():
    service=unbound_service()
    assert '帮助' in service.query(IDENTITY,'help')['text']
    assert '绑定' in service.query(IDENTITY,'summary','nte')['text']
    assert '绑定' in service.query(IDENTITY,'status')['text']


def test_public_queries_do_not_require_bound_game():
    service=unbound_service()
    service.public=SimpleNamespace(read=lambda game,cap:QueryResult([{'name':'Public event https://example.com','start_at':'2026-10-01T00:00:00+08:00','end_at':'2099-10-01T00:00:00+08:00'}],None,'never',None))
    assert 'Public event' in service.query(IDENTITY,'calendar','nte')['text']
    assert 'https://' not in service.query(IDENTITY,'calendar','nte')['text']


async def test_web_and_qq_share_snapshot(tmp_path):
    from tests.test_account_queries import query_fixture
    accounts,scope,store,query=await query_fixture(tmp_path)
    store.save_scoped(scope,'account','{"nickname":"Same player","level":17}',1)
    service=QqQueryService(SimpleNamespace(resolve_qq_identity=lambda identity:Principal('a',False)),query,None)
    website=query.read(scope,'account')
    assert 'Same player' in service.query(IDENTITY,'summary','nte')['text']
    assert str(website.payload['level']) in service.query(IDENTITY,'summary','nte')['text']
    accounts.revoke(Principal('a',False),scope.account_id)
    assert 'Same player' not in service.query(IDENTITY,'summary','nte')['text']


def test_self_query_cannot_target_other_account(tmp_path):
    from tests.test_qq_internal_auth import client
    from game_assistant.cloud_app import create_cloud_app
    from game_assistant.config import Settings
    app=create_cloud_app(Settings(cloud_db_path=str(tmp_path/'cloud.db'),cloud_allowed_origins=['https://cloud.example'],qq_app_id='app',qq_service_token='fixture-secret'),start_scheduler=False)
    c=client(app)
    body={'identity':asdict(IDENTITY),'command':'help'}
    assert c.post('/internal/qq/query',json=body).status_code==401
    auth={'Authorization':'Bearer fixture-secret'}
    assert c.post('/internal/qq/query',json=body,headers=auth).status_code==200
    for key in ('user_id','account_id','role_id'):
        response=c.post('/internal/qq/query',json={**body,key:'other-private-value'},headers=auth)
        assert response.status_code==422 and 'other-private-value' not in response.text
    response=c.post('/internal/qq/query',json={**body,'identity':{**asdict(IDENTITY),'app_id':'other'}},headers=auth)
    assert response.status_code==400


def test_endfield_providers_choose_default_separately():
    rows=[dict(account_id='h2',game='endfield',provider='hypergryph',state='active',is_default=0,roles=[dict(role_id='r',is_default=1)]),
          dict(account_id='s',game='endfield',provider='skland',state='active',is_default=0,roles=[dict(role_id='r',is_default=1)]),
          dict(account_id='h1',game='endfield',provider='hypergryph',state='active',is_default=1,roles=[dict(role_id='r',is_default=1)])]
    reads=[]
    class Query:
        accounts=SimpleNamespace(require_scope=lambda p,a,r:SimpleNamespace(user_id=p.user_id,account_id=a,role_id=r))
        def list_accounts(self,p):return rows
        def capabilities(self,scope):return ['account']
        def read(self,scope,cap):
            reads.append(scope.account_id)
            return QueryResult({'nickname':scope.account_id},None,'never',None)
    service=QqQueryService(SimpleNamespace(resolve_qq_identity=lambda i:Principal('a',False)),Query(),None)
    text=service.query(IDENTITY,'summary','endfield')['text']
    assert reads==['h1','s'] and '鹰角寻访' in text and '森空岛' in text


def test_skland_reply_has_name_level_stamina_without_role_id():
    import json
    from tests.test_qq_unified_queries import CachedQuery, service
    query=CachedQuery()
    query.add('endfield','skland','sk',{'account':{'base':{'name':'Operator','level':24,'role_id':'sensitive-role'},
                                                    'stamina':{'current':None,'maximum':200}}})
    context={};text=service(query).query(IDENTITY,'summary','endfield',image_context=context)['text']
    assert 'Operator' in text and '账号等级：24' in text and '未知/200' in text
    assert 'sensitive-role' not in text and 'sensitive-role' not in json.dumps(context['render_snapshot'],ensure_ascii=False)


async def test_internal_binding_redeems_once_with_trusted_message_id():
    from datetime import datetime,timezone,timedelta
    import httpx
    from game_assistant.qq.client import InternalQqClient
    from game_assistant.qq.models import InboundMessage
    requests=[]
    def respond(request):
        requests.append(request)
        return httpx.Response(200,json={'status':'linked','link_id':'fixture-link'})
    http=httpx.AsyncClient(transport=httpx.MockTransport(respond))
    client=InternalQqClient('http://127.0.0.1:8000','secret',http=http)
    now=datetime.now(timezone.utc)
    message=InboundMessage(IDENTITY,'msg','绑定 CODE',now.isoformat(),(now+timedelta(minutes=5)).isoformat())
    text=await client.execute(message)
    assert '绑定成功' in text and 'CODE' not in text and '填回' not in text
    assert requests[0].url.path=='/internal/qq/link-redemptions'
    import json
    assert json.loads(requests[0].content)['message_id']=='msg'
    assert requests[0].headers['authorization']=='Bearer secret'
    await http.aclose()


def test_internal_client_rejects_remote_or_redirect_endpoint():
    from game_assistant.qq.client import InternalQqClient,QqClientError
    for url in ('https://example.com','http://localhost:8000','http://127.0.0.1@evil.example','http://127.0.0.1/x'):
        with pytest.raises(QqClientError):InternalQqClient(url,'fixture-secret')


def test_unapproved_dashboard_has_no_url_and_approved_dashboard_works():
    service=unbound_service()
    service.dashboard_url='https://dashboard.example.com'
    assert 'example' not in service.query(IDENTITY,'dashboard')['text']
    service.urls_approved=True
    assert service.query(IDENTITY,'dashboard')['text']=='https://dashboard.example.com'


async def test_internal_remote_failure_does_not_echo_details():
    import httpx
    from game_assistant.qq.client import InternalQqClient,QqClientError
    http=httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(503,json={'detail':'private-token'})))
    client=InternalQqClient('http://127.0.0.1:8000','fixture-secret',http=http)
    with pytest.raises(QqClientError) as error:await client.post('/internal/qq/query',{})
    assert 'private-token' not in str(error.value)
    await http.aclose()


async def test_loopback_client_sends_explicit_host_for_actual_cloud_boundary(tmp_path):
    import httpx
    from game_assistant.qq.client import InternalQqClient
    from game_assistant.cloud_app import create_cloud_app
    from game_assistant.config import Settings
    app=create_cloud_app(Settings(cloud_db_path=str(tmp_path/'cloud.db'),
        cloud_allowed_origins=['https://dashboard.example'],qq_app_id='app',qq_service_token='fixture-secret'),start_scheduler=False)
    http=httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1234)))
    client=InternalQqClient('http://127.0.0.1:8020','fixture-secret',internal_host='dashboard.example',http=http)
    result=await client.post('/internal/qq/query',{'identity':asdict(IDENTITY),'command':'help'})
    assert '帮助' in result['text']
    await http.aclose()


def test_domains_written_right_after_chinese_text_are_masked():
    from game_assistant.qq.commands import safe_text
    assert safe_text('官网kurogames.com领取') == '官网[链接未启用]领取'
    assert safe_text('详见 www.kurogames.com。') == '详见 [链接未启用]'
    # An email address still keeps its domain; only standalone domains are links.
    assert safe_text('邮箱 a@kurogames.com') == '邮箱 a@kurogames.com'


@pytest.mark.parametrize('alias,command',[
    ('日历','calendar'),('calendar','calendar'),('活动','events'),('events','events'),
    ('近期活动','recent_events'),('recent_events','recent_events'),
])
@pytest.mark.parametrize('page',[1,2,100])
def test_public_cross_game_page_commands(alias,command,page):
    parsed=parse_command(f'/{alias} {page}')
    assert (parsed.command,parsed.game,parsed.page)==(command,None,page)
    assert parsed.role_name is None and parsed.code is None


@pytest.mark.parametrize('raw',[
    '日历 0','活动 101','近期活动 -1','日历 +2','日历 2.0','日历 ２',
    '日历 2 other-user','活动 other-user 2','近期活动 2 3',
    '绑定 CODE 2','看板 2','体力 2','刷新 2',
    '终末地 刷新 2',
])
def test_page_syntax_keeps_invalid_and_unpaged_commands_rejected(raw):
    parsed=parse_command(raw)
    assert parsed.command=='help' and parsed.page==1 and parsed.code is None


@pytest.mark.parametrize('alias,command',[
    ('总览','overview'),('我的总览','overview'),('overview','overview'),
    ('状态','status'),('我的账号','status'),('status','status'),
])
def test_overview_and_status_existing_continuations_keep_their_meaning(alias,command):
    assert parse_command(f'{alias} 2').command==command
    assert parse_command(f'{alias} 2').page==2
    assert parse_command(f'{alias} 101').command=='help'


def test_snapshot_next_commands_parse_back_into_their_public_or_scoped_query():
    from datetime import datetime
    from game_assistant.qq.render_snapshot import (
        calendar_snapshot, filtered_events_snapshot, game_snapshot, role_snapshot, gacha_snapshot,
    )
    now=datetime.fromisoformat('2026-10-17T12:00:00+08:00')
    empty=QueryResult([],now.isoformat(),'ok',True)
    rows={game:empty for game in ('wuthering_waves','nte','endfield')}
    snapshots=[(calendar_snapshot(rows,now),'calendar',None,None)]
    for command in ('events','recent_events'):
        snapshots.append((filtered_events_snapshot(rows,command,now),command,None,None))
    for game,label in (('wuthering_waves','鸣潮'),('nte','异环'),('endfield','终末地')):
        snapshots.append((calendar_snapshot({game:empty},now),'calendar',game,None))
        snapshots.append((game_snapshot([],now,command=label+' 总览'),'summary',game,None))
    nte=QueryResult({'schema_version':1,'entries':[{'id':'9001','name':'合成角色','level':0}]},now.isoformat(),'ok',True)
    wuwa=QueryResult({'role':{'role_name':'合成角色','level':0}},now.isoformat(),'ok',True)
    snapshots.extend([
        (role_snapshot('nte',nte,now),'roles','nte',None),
        (role_snapshot('nte',nte,now,resolved_id='9001'),'roles','nte','9001'),
        (role_snapshot('wuthering_waves',wuwa,now,detail=wuwa,resolved_id='1501'),'roles','wuthering_waves','1501'),
        (gacha_snapshot('wuthering_waves',empty,now),'gacha','wuthering_waves',None),
        (gacha_snapshot('nte',empty,now),'gacha','nte',None),
        (game_snapshot([],now,command='终末地 寻访战报'),'gacha','endfield',None),
    ])
    for snapshot,command,game,role in snapshots:
        continuation=snapshot['next_command']+' 2'
        parsed=parse_command(continuation)
        assert (parsed.command,parsed.game,parsed.page,parsed.role_name)==(command,game,2,role),continuation


@pytest.mark.parametrize('raw,command,game',[
    ('帮助 2','help',None),('help 100','help',None),('鸣潮 帮助 2','help','wuthering_waves'),
    ('异环 探索 2','exploration','nte'),('鸣潮 资源 2','resources','wuthering_waves'),
    ('终末地 帝江号 2','ship','endfield'),
])
def test_read_only_queries_can_continue_without_enabling_action_pagination(raw,command,game):
    from game_assistant.qq.query_routes import QueryBody
    parsed=parse_command(raw)
    assert (parsed.command,parsed.game)==(command,game) and parsed.page>=2
    body=QueryBody(identity=asdict(IDENTITY),command=parsed.command,game=parsed.game,page=parsed.page)
    assert body.page==parsed.page
    assert parse_command(raw.rsplit(' ',1)[0]+' 101').command=='help'


@pytest.mark.parametrize('command',['refresh','dashboard'])
def test_action_query_bodies_still_reject_pagination(command):
    from game_assistant.qq.query_routes import QueryBody
    with pytest.raises(ValueError,match='page_not_supported'):
        QueryBody(identity=asdict(IDENTITY),command=command,game='nte',page=2)


@pytest.mark.parametrize('command,game,role',[
    ('help',None,None),('help','nte',None),('status',None,None),('overview',None,None),
    ('summary','nte',None),('combat','wuthering_waves',None),
    ('exploration','nte',None),('progress','nte',None),
    ('resources','wuthering_waves',None),('realestate','nte',None),
    ('vehicles','nte',None),('teams','nte',None),('gacha','nte',None),
    ('roles','wuthering_waves',None),('exploration','endfield',None),('ship','endfield',None),
    ('roles','endfield','陈千语'),('honor','endfield',None),
    ('calendar','nte',None),('events','nte',None),('recent_events','nte',None),
    ('events',None,None),('recent_events',None,None),('calendar',None,None),
])
def test_query_snapshot_continuation_preserves_the_query(command,game,role):
    from tests.test_qq_unified_queries import CachedQuery,service
    query=CachedQuery()
    query.add('nte','tajiduo','n',{'account':{'nickname':'测试'},'stamina':{'current':0}})
    query.add('wuthering_waves','kuro','w',{'roles':[{'role_id':'1','name':'今汐','level':0}]})
    query.add('endfield','skland','e',{'account':{'operators':[{'id':'1','name':'陈千语','level':0}]}})
    api=service(query)
    api.public=SimpleNamespace(read=lambda *args:QueryResult([],None,'ok',True))
    context={}
    api.query(IDENTITY,command,game,role_name=role,image_context=context)
    snapshot=context['render_snapshot']
    parsed=parse_command(snapshot['next_command']+' 2')
    assert (parsed.command,parsed.game,parsed.role_name,parsed.page)==(command,game,role,2),snapshot['next_command']


async def test_multipage_action_reply_falls_back_without_exposing_action_continuation():
    from game_assistant.qq.rendering import RenderedImage
    from tests.test_qq_unified_queries import CachedQuery,service
    query=CachedQuery();query.add('nte','tajiduo','n',{'stamina':{'current':0}})
    class Queue:
        renderer=SimpleNamespace(invalidate_account=lambda *args:None)
        async def render(self,scope,result,**kwargs):return RenderedImage(b'png',page=1,total_pages=2)
    api=service(query);api.render_queue=Queue()
    reply=await api.query_reply(IDENTITY,'refresh','nte',image_requested=True,budget_seconds=5)
    assert 'image' not in reply and '图片暂不可用' in reply['text'] and '下一页' not in reply['text']
    assert len(query.refreshes)==1 and query.refreshes[0][1]=='stamina'


RETIRED_FORMS=[
    ('公告',None,'公告资讯'),('资讯',None,'公告资讯'),('news',None,'公告资讯'),('鸣潮 公告','wuthering_waves','公告资讯'),
    ('公告 异环','nte','公告资讯'),('终末地资讯','endfield','公告资讯'),
    ('体力',None,'帮助'),('鸣潮 体力','wuthering_waves','帮助'),('异环体力 2','nte','帮助'),('终末地 理智','endfield','帮助'),
    ('鸣潮 数据坞','wuthering_waves','帮助'),('鸣潮 活动进度','wuthering_waves','帮助'),
    ('异环 挑战','nte','帮助'),('异环 战斗','nte','帮助'),('异环 档案','nte','帮助'),
    ('终末地 进度','endfield','帮助'),('终末地 练度','endfield','终末地 角色'),('终末地 全员练度','endfield','终末地 角色'),
    ('练度',None,'终末地 角色'),('终末地 地区','endfield','终末地 探索'),('地区建设 终末地','endfield','终末地 探索'),
]


@pytest.mark.parametrize('raw,game,pointer',RETIRED_FORMS)
def test_retired_commands_parse_to_a_fixed_notice_with_a_replacement(raw,game,pointer):
    from game_assistant.qq.commands import RETIRED, retired_reply
    parsed=parse_command(raw)
    assert (parsed.command,parsed.game,parsed.role_name,parsed.page)==('retired',game,None,1) and parsed.retired in RETIRED
    notice=retired_reply(parsed.retired,parsed.game)
    assert notice.startswith('该指令已下线') and pointer in notice


@pytest.mark.parametrize('raw,command,game',[
    ('鸣潮 挑战','combat','wuthering_waves'),('终末地 挑战','combat','endfield'),('鸣潮 战斗','combat','wuthering_waves'),
    ('鸣潮 进度','progress','wuthering_waves'),('异环 进度','progress','nte'),('终末地 干员','roles','endfield'),
    ('终末地 探索','exploration','endfield'),('进度','help',None),('挑战','help',None),
])
def test_partially_retired_words_keep_their_other_games(raw,command,game):
    parsed=parse_command(raw)
    assert (parsed.command,parsed.game)==(command,game)


async def test_retired_commands_send_only_the_retired_word_to_the_query_route():
    from game_assistant.qq.client import InternalQqClient
    from game_assistant.qq.models import InboundMessage
    sent=[]
    class Client(InternalQqClient):
        async def post(self,path,body):
            sent.append((path,body));return {'text':'fixed'}
    client=Client('http://127.0.0.1:8020','service')
    message=InboundMessage(IDENTITY,'m','终末地 练度','2026-10-21T00:00:00+00:00','2026-10-21T00:05:00+00:00')
    assert await client.execute(message)=='fixed'
    assert sent==[('/internal/qq/query',{'identity':asdict(IDENTITY),'command':'retired','game':'endfield','retired':'training'})]
    await client.aclose()


@pytest.mark.parametrize('retired,game,pointer',[('training','endfield','终末地 角色'),('regions','endfield','终末地 探索'),
    ('news',None,'公告资讯'),('stamina','nte','帮助'),('combat','nte','帮助')])
def test_retired_reply_is_a_fixed_notice_image_without_any_binding_or_data_read(retired,game,pointer):
    from game_assistant.qq.query_routes import QueryBody
    QueryBody(identity=asdict(IDENTITY),command='retired',game=game,retired=retired)
    class Never:
        def __getattr__(self,name):raise AssertionError('retired commands must not read '+name)
    service=QqQueryService(Never(),Never(),Never())
    context={}
    text=service.query(IDENTITY,'retired',game,image_context=context,retired=retired)['text']
    assert '该指令已下线' in text and pointer in text
    snapshot=context['render_snapshot']
    assert snapshot['kind']=='notice' and not context['panels'] and not context['snapshots'] and not context['grants']
    assert pointer in str(snapshot['display_data']['notices'])


@pytest.mark.parametrize('body',[dict(command='retired',game='nte',retired='calendar'),dict(command='retired',game='nte'),
    dict(command='retired',game='nte',retired='progress'),dict(command='summary',game='nte',retired='stamina')])
def test_query_body_accepts_only_known_retired_words(body):
    from pydantic import ValidationError
    from game_assistant.qq.query_routes import QueryBody
    with pytest.raises(ValidationError):
        QueryBody(identity=asdict(IDENTITY),**body)


@pytest.mark.parametrize('command,game',[('stamina','nte'),('news','nte'),('calabash','wuthering_waves'),('activities','wuthering_waves'),
    ('record','nte'),('training','endfield'),('regions','endfield'),('combat','nte'),('progress','endfield'),('resources','nte'),('refresh',None)])
def test_query_body_rejects_retired_and_unregistered_commands(command,game):
    from pydantic import ValidationError
    from game_assistant.qq.query_routes import QueryBody
    with pytest.raises(ValidationError):
        QueryBody(identity=asdict(IDENTITY),command=command,game=game)


def _help_pairs(game):
    """Parse every help line back, expanding the 游戏 placeholder to each named game."""
    from game_assistant.qq.presentation import help_document
    pairs=set()
    for section in help_document(game)['sections']:
        for field in section['fields']:
            syntax=field['value'].replace('实际绑定码','CODE1234').replace('精确名称','合成角色')
            assert not any(word in syntax for word in ('体力','理智','公告','资讯','数据坞','活动进度','档案','练度','地区')),syntax
            # A line for some games names them in its label, e.g. 成长进度（鸣潮、异环）.
            names=[name for name in GAME_NAMES.values() if name in field['label']] or list(GAME_NAMES.values())
            for name in (names if '游戏' in syntax else (None,)):
                parsed=parse_command(syntax.replace('游戏',name) if name else syntax)
                assert parsed.command!='retired' and (parsed.command!='help' or syntax.endswith('帮助')),syntax
                pairs.add((parsed.command,parsed.game))
    return pairs


def test_help_is_generated_from_the_registry_and_matches_the_parser():
    from game_assistant.qq.commands import ACCEPTED, VERBS
    listed=_help_pairs(None)
    # Help lists exactly the accepted game commands plus the game-less account commands.
    assert listed=={(command,game) for command,game in ACCEPTED if game is not None or command in ('binding','status','overview','dashboard')}
    for game,name in GAME_NAMES.items():
        assert _help_pairs(game)=={pair for pair in listed if pair[1] in (game,None)}
        for word in VERBS:
            parsed=parse_command(name+' '+word)
            assert parsed.command in ('help','retired') or (parsed.command,game) in listed,(name,word)


def test_help_wording_describes_recent_events_without_a_fixed_window():
    from game_assistant.qq.cards import card_to_text
    from game_assistant.qq.presentation import help_document
    for game in (None,'nte'):
        text=card_to_text(help_document(game))
        assert '7 天' not in text and '即将开始或结束' in text and '攻略索引' not in text
    assert '成长进度（鸣潮、异环）：游戏 进度' in card_to_text(help_document())
    assert '游戏 进度' not in card_to_text(help_document('endfield')) and '终末地 进度' not in card_to_text(help_document('endfield'))


KEPT={'鸣潮':'总览 角色 攻略 探索 进度 挑战 抽卡 资源 帮助 活动 近期活动 日历 刷新','异环':'总览 角色 攻略 探索 进度 抽卡 房产 车辆 队伍 帮助 活动 近期活动 日历 刷新',
      '终末地':'总览 角色 干员 攻略 探索 挑战 抽卡 寻访战报 帝江号 光荣之路 帮助 活动 近期活动 日历 刷新'}


def test_every_kept_command_still_parses():
    from game_assistant.qq.commands import GAMES, accepts
    for name,words in KEPT.items():
        for word in words.split():
            parsed=parse_command(name+' '+word)
            assert parsed.game==GAMES[name] and accepts(parsed.command,parsed.game),(name,word)
    for raw in ('帮助','我的账号','我的总览','活动','近期活动','日历','看板','绑定 CODE1234','攻略'):
        assert parse_command(raw).command not in ('retired','help') or raw=='帮助',raw


def test_help_groups_name_their_game_only_when_every_line_belongs_to_it():
    from game_assistant.qq.cards import card_to_text, validate_card_document
    from game_assistant.qq.presentation import help_document
    card=help_document()
    assert {s['title']:s.get('game') for s in card['sections']}=={'绑定与账号':None,'总览与角色':None,'资源与进度':None,'抽卡':None,'活动与日历':None,
        '鸣潮专项':'wuthering_waves','异环专项':'nte','终末地专项':'endfield'}
    assert [s.get('game') for s in help_document('nte')['sections'] if s.get('game')]==['nte']
    # Presentation only: the text reply is the same with or without the field.
    plain={**card,'sections':[{k:v for k,v in s.items() if k!='game'} for s in card['sections']]}
    assert card_to_text(card)==card_to_text(plain) and validate_card_document(card)['sections'][5]['game']=='wuthering_waves'
