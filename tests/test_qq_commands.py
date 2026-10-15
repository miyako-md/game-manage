from dataclasses import asdict
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from game_assistant.qq.commands import parse_command, render_result, safe_text
from game_assistant.qq.models import QqIdentity
from game_assistant.qq.query_routes import QqQueryService, install_qq_query_routes
from game_assistant.accounts.models import QueryResult
from game_assistant.identity.models import Principal
from game_assistant.qq.bindings import QqBindingError

IDENTITY = QqIdentity('app','group','group','sender')


def test_commands_are_explicit_self_queries():
    for raw,command,game in [('/help','help',None),('绑定 CODE','binding',None),
                            ('我的账号','status',None),('/ww','summary','wuthering_waves'),
                            ('/yh','summary','nte'),('/endfield','summary','endfield'),
                            ('鸣潮角色','roles','wuthering_waves'),('活动 鸣潮','events','wuthering_waves'),
                            ('公告 异环','news','nte'),('刷新 终末地','refresh','endfield'),('看板','dashboard',None)]:
        parsed=parse_command(raw)
        assert parsed.command==command and parsed.game==game
    for raw in ['/ww other-account','异环 123456789','刷新 异环 其他用户','/help https://secret.example']:
        assert parse_command(raw).command=='help'


@pytest.mark.parametrize('raw,command,game',[
    ('ww 查询','summary','wuthering_waves'),('yh 查询','summary','nte'),
    ('终末地 查询','summary','endfield'),('/ww 活动','events','wuthering_waves'),
    ('ww 公告','news','wuthering_waves'),('yh 刷新','refresh','nte'),
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
    from game_assistant.qq.commands import HELP
    parsed = parse_command(raw)
    assert parsed.command == 'roles' and parsed.game == 'wuthering_waves'
    assert parsed.role_name == raw.split()[-1]
    assert '本人缓存' in HELP and '精确名称' in HELP


def test_named_role_filter_is_bounded_printable_and_roles_only():
    assert parse_command('ww 角色 '+'名'*64).role_name == '名'*64
    for raw in ('ww 角色 '+'名'*65,'ww 角色 名\x00字','ww 角色 名\x1f字','ww 角色 今汐 other-user',
                'ww 查询 今汐','ww 公告 今汐'):
        parsed = parse_command(raw)
        assert parsed.command == 'help' and parsed.role_name is None
    assert parse_command('ww 角色').role_name is None


def test_url_removed_when_not_approved():
    assert 'example' not in safe_text('网址 https://example.com/a 与 www.example.com、example.com',urls_approved=False)
    assert 'https://example.com' in safe_text('https://example.com',urls_approved=True)


def test_render_masks_uid_preserves_null_and_failed_cache():
    text=render_result('账号',QueryResult({'nickname':'User 123456789','level':None,'extra':{'uid':'123456789','token':'private-secret'}},'2026-10-12T00:00:00Z','error',False),'account')
    assert '123456789' not in text and 'private-secret' not in text
    assert '未知' in text and '旧' in text and '完整' in text


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
    service.public=SimpleNamespace(read=lambda game,cap:QueryResult([{'title':'Public notice','url':'https://example.com'}],None,'never',None))
    assert 'Public notice' in service.query(IDENTITY,'news','nte')['text']
    assert 'https://' not in service.query(IDENTITY,'news','nte')['text']


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


def test_endfield_overview_uses_skland_and_separate_gacha_keeps_default_role():
    roles=[dict(role_id='first-role',is_default=0),dict(role_id='default-role',is_default=1)]
    rows=[dict(account_id='h2',game='endfield',provider='hypergryph',state='active',is_default=0,roles=roles),
          dict(account_id='s',game='endfield',provider='skland',state='active',is_default=0,roles=roles),
          dict(account_id='h1',game='endfield',provider='hypergryph',state='active',is_default=1,roles=[dict(role_id='r',is_default=1)])]
    reads=[]
    class Query:
        accounts=SimpleNamespace(require_scope=lambda p,a,r:SimpleNamespace(user_id=p.user_id,account_id=a,role_id=r))
        def list_accounts(self,p):return rows
        def capabilities(self,scope):return ['account'] if scope.account_id=='s' else ['gacha']
        def read(self,scope,cap):
            reads.append((scope.account_id,scope.role_id,cap))
            return QueryResult({'base':{'name':'森空岛角色'}} if scope.account_id=='s' else {'total':0,'pools':[]},None,'never',None)
    service=QqQueryService(SimpleNamespace(resolve_qq_identity=lambda i:Principal('a',False)),Query(),None)
    for command,game in [('overview',None),('summary','endfield')]:
        reads.clear()
        text=service.query(IDENTITY,command,game)['text']
        assert reads==[('s','default-role','account')]
        assert '森空岛角色' in text and '鹰角寻访' not in text
    reads.clear()
    text=service.query(IDENTITY,'gacha','endfield')['text']
    # Website ordering chooses the first passport; its default role still wins.
    assert reads==[('h2','default-role','gacha')]
    assert '鹰角寻访' in text and '森空岛角色' not in text


def test_skland_real_card_shape_has_name_level_stamina_without_uid():
    result=QueryResult({'base':{'name':'Operator','level':24,'role_id':'sensitive-role'},
                        'stamina':{'current':None,'maximum':200}},None,'ok',None)
    text=render_result('森空岛档案',result,'account')
    assert 'Operator' in text and '24' in text and '未知/200' in text
    assert 'sensitive-role' not in text


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
