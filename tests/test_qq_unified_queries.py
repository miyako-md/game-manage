"""Unified cached QQ queries: explicit grammar, projection, and revocation."""
from dataclasses import asdict
from types import SimpleNamespace
import json

import httpx
import pytest

from game_assistant.accounts.models import AccountScope, QueryResult
from game_assistant.accounts.store import AccountNotFoundError
from game_assistant.identity.models import Principal
from game_assistant.qq.commands import parse_command
from game_assistant.qq.models import QqIdentity
from game_assistant.qq.query_routes import QqQueryService, QueryBody

IDENTITY = QqIdentity('app', 'group', 'g', 'sender')


@pytest.mark.parametrize('raw,verb,game,name,page', [
    ('我的', 'overview', None, None, 1), ('总览', 'overview', None, None, 1),
    ('/ww 总览', 'summary', 'wuthering_waves', None, 1),
    ('异环角色 2', 'roles', 'nte', None, 2),
    ('终末地 角色 陈千语', 'roles', 'endfield', '陈千语', 1),
    ('角色 异环 娜娜莉', 'roles', 'nte', '娜娜莉', 1),
    ('鸣潮 角色 今汐 2', 'roles', 'wuthering_waves', '今汐', 2),
    ('异环 体力', 'retired', 'nte', None, 1),
    ('异环 进度 2', 'progress', 'nte', None, 2),
    ('探索 鸣潮 2', 'exploration', 'wuthering_waves', None, 2),
    ('挑战 终末地', 'combat', 'endfield', None, 1),
    ('抽卡 异环', 'gacha', 'nte', None, 1),
    ('日历 鸣潮 3', 'calendar', 'wuthering_waves', None, 3),
])
def test_unified_explicit_grammar(raw, verb, game, name, page):
    parsed = parse_command(raw)
    assert (parsed.command, parsed.game, parsed.role_name, parsed.page) == (verb, game, name, page)


@pytest.mark.parametrize('raw', ['鸣潮 角色 0', '异环 角色 101', '异环 进度 101',
                                 '总览 other-user', '刷新 异环 2', '角色 异环 名字\x00',
                                 'ww 角色 a b', '异环 角色 '+ '名' * 65])
def test_unified_grammar_rejects_invalid_selector(raw):
    assert parse_command(raw).command == 'help'


class CachedQuery:
    def __init__(self):
        self.rows = []
        self.data = {}
        self.versions = {}
        self.reads = []
        self.refreshes = []
        self.accounts = SimpleNamespace(require_scope=self.require_scope, describe=self.describe,
                                        list_accounts=self.list_accounts, _listeners=[])

    def add(self, game, provider, account, payloads, *, default=True, role='default-role'):
        scope = AccountScope('u', account, role)
        self.rows.append(dict(game=game, provider=provider, account_id=account, state='active',
                              is_default=default, roles=[dict(role_id=role, is_default=True)]))
        self.versions[account] = 1
        for cap, payload in payloads.items():
            self.data[(account, cap)] = QueryResult(payload, '2026-10-14T00:00:00Z', 'ok', None)
        return scope

    def list_accounts(self, principal):
        assert principal.user_id == 'u'
        return self.rows

    def require_scope(self, principal, account, role):
        if principal.user_id != 'u' or self.versions.get(account) is None:
            raise AccountNotFoundError()
        return AccountScope('u', account, role)

    def describe(self, scope):
        if self.versions.get(scope.account_id) is None:
            raise AccountNotFoundError()
        return {'version': self.versions[scope.account_id]}

    def capabilities(self, scope):
        return [cap for account, cap in self.data if account == scope.account_id]

    def read(self, scope, capability):
        self.reads.append((scope, capability))
        return self.data[(scope.account_id, capability)]

    def request_refresh(self, scope, capability):
        self.refreshes.append((scope, capability))
        return SimpleNamespace(state='queued')


def service(query, *, queue=None):
    return QqQueryService(SimpleNamespace(resolve_qq_identity=lambda i: Principal('u', False)),
                          query, None, render_queue=queue)


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    import socket
    original_connect = socket.socket.connect
    def forbidden(*args, **kwargs):
        raise AssertionError('QQ cached query attempted network')
    def guarded_connect(sock, address):
        # Windows asyncio's private self-pipe is a loopback socket pair.
        if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
            return original_connect(sock, address)
        return forbidden(sock, address)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', guarded_connect)


def test_three_game_cached_role_lists_and_details():
    query = CachedQuery()
    query.add('wuthering_waves', 'kuro', 'ww', {'roles': [{'name': '今汐', 'level': 80, 'chain': 0, 'weapon': '长刃',
                  'extra': {'token': 'secret', 'score': 999, 'uid': '123456789'}}]})
    query.add('nte', 'tajiduo', 'nte', {'roles': {'entries': [{'name': '娜娜莉', 'level': None, 'element': '灵',
                  'weapon': {'name': '弧盘', 'level': 0}, 'skills': [{'name': '普攻', 'level': 1}]}]}})
    query.add('endfield', 'hypergryph', 'hg', {'account': {'nickname': 'HG identity'}})
    query.add('endfield', 'skland', 'sk', {'account': {'base': {'name': 'SK identity'}, 'operators': [
        {'name': '陈千语', 'level': 0, 'equipment': [{'name': '护甲', 'slot': 'bodyEquip', 'level': None}]}]}})
    api = service(query)
    for game, name in [('wuthering_waves', '今汐'), ('nte', '娜娜莉'), ('endfield', '陈千语')]:
        assert name in api.query(IDENTITY, 'roles', game)['text']
        text = api.query(IDENTITY, 'roles', game, role_name=name)['text']
        assert name in text and '更新时间' in text
        assert 'secret' not in text and '999' not in text and '123456789' not in text
    assert '弧盘' in api.query(IDENTITY, 'roles', 'nte', role_name='娜娜莉')['text']
    assert '护甲' in api.query(IDENTITY, 'roles', 'endfield', role_name='陈千语')['text']
    assert 'HG identity' not in api.query(IDENTITY, 'roles', 'endfield')['text']


def test_legacy_role_page_now_returns_complete_longcard_and_duplicate_disambiguation():
    query = CachedQuery()
    query.add('nte', 'tajiduo', 'nte', {'roles': {'entries': [{'name': f'角色{i}', 'level': None} for i in range(14)]}})
    api = service(query)
    page = api.query(IDENTITY, 'roles', 'nte', page=2)['text']
    assert '角色6' in page and '角色0' in page and '长图' in page and '未知' in page
    assert '长图' in api.query(IDENTITY, 'roles', 'nte', page=4)['text']
    query.data[('nte', 'roles')] = QueryResult({'entries': [{'name': '同名'}, {'name': '同名'}]}, None, 'ok', False)
    assert '同名角色' in api.query(IDENTITY, 'roles', 'nte', role_name='同名')['text']


def test_overview_uses_all_default_scopes_without_merging_endfield_identities():
    query = CachedQuery()
    for game, provider, account in [('wuthering_waves', 'kuro', 'ww'), ('nte', 'tajiduo', 'nte'),
                                    ('endfield', 'hypergryph', 'hg'), ('endfield', 'skland', 'sk')]:
        payload={'base':{'name':'name-'+account,'level':None}} if provider=='skland' else {'nickname':'name-'+account,'level':None}
        query.add(game, provider, account, {'account': payload})
    query.add('nte', 'tajiduo', 'other', {'account': {'nickname': 'NEVER'}}, default=False)
    text = service(query).query(IDENTITY, 'overview')['text']
    assert all('name-'+name in text for name in ['ww', 'nte', 'hg', 'sk'])
    assert 'NEVER' not in text and '鹰角寻访' in text and '森空岛档案' in text
    assert len(text) <= 1800


def test_cache_capability_projection_and_unsupported_are_explicit():
    query = CachedQuery()
    query.add('nte', 'tajiduo', 'nte', {'account': {'nickname': 'N'},
       'stamina': {'current': 0, 'maximum': 100, 'city_current': None, 'city_maximum': 10},
       'exploration': {'areas': [{'name': '海特洛', 'current': None, 'total': 20}]},
       'gacha': {'total_draws': 5, 'total_s': None, 'luck_title': 'DO NOT SHOW', 'pools': [{'name': '常驻', 'total_draws': 5, 'percentile': 99}]}})
    query.add('endfield', 'skland', 'sk', {'account': {'base': {'name': 'S'}, 'stamina': {'current': 0, 'maximum': 240},
                  'regions': [{'name': '四号谷地', 'level': 2}], 'progress': [{'name': '每日活跃', 'cur': None, 'total': 100}]}})
    api = service(query)
    assert '0/100' in api.query(IDENTITY, 'summary', 'nte')['text']
    assert '未知/20' in api.query(IDENTITY, 'exploration', 'nte')['text']
    assert '四号谷地' in api.query(IDENTITY, 'exploration', 'endfield')['text']
    assert '当前缓存不支持' in api.query(IDENTITY, 'realestate', 'nte')['text']
    text = api.query(IDENTITY, 'gacha', 'nte')['text']
    assert '5' in text and 'DO NOT SHOW' not in text and '99' not in text
    api.query(IDENTITY, 'refresh', 'nte')
    assert query.refreshes and all(scope.account_id == 'nte' for scope, _ in query.refreshes)


@pytest.mark.parametrize('change', ['secondary_revoke', 'secondary_rotate', 'unlink', 'rebind'])
@pytest.mark.parametrize('render_exception', [False, True])
async def test_multi_scope_overview_rechecks_every_authorization_after_async_render(change, render_exception):
    from game_assistant.qq.bindings import QqBindingError
    query = CachedQuery()
    query.add('nte', 'tajiduo', 'nte', {'account': {'nickname': 'PRIVATE N'}})
    query.add('endfield', 'skland', 'sk', {'account': {'nickname': 'PRIVATE S'}})
    linked = [True]
    principal = [Principal('u', False)]
    def resolve(i):
        if not linked[0]:
            raise QqBindingError('qq_link_required', 403)
        return principal[0]
    class Queue:
        renderer = SimpleNamespace(invalidate_account=lambda *args: None)
        async def render(self, scope, result, **kwargs):
            assert set(result.payload) <= {'card', 'grant_version', 'snapshot_times', 'scopes', 'snapshot_fingerprints','shared_required','render_snapshot'}
            assert result.payload['shared_required'] is True and result.payload['render_snapshot']['kind']=='game_snapshot'
            assert len(result.payload['scopes']) == 2
            if change == 'secondary_revoke': query.versions['sk'] = None
            elif change == 'secondary_rotate': query.versions['sk'] += 1
            elif change == 'unlink': linked[0] = False
            else: principal[0] = Principal('other', False)
            if render_exception:raise RuntimeError('fixture_render_failed_after_authorization_change')
            return b'png'
    api = QqQueryService(SimpleNamespace(resolve_qq_identity=resolve), query, None, render_queue=Queue())
    reply = await api.query_reply(IDENTITY, 'overview', image_requested=True, budget_seconds=5)
    assert 'image' not in reply and 'PRIVATE' not in reply['text'] and '变更' in reply['text']


async def test_image_reply_keeps_the_full_text_for_a_failed_delivery():
    # The bot sends only the image; this text is what members get if the upload fails.
    from game_assistant.qq.rendering import RenderedImage
    query = CachedQuery()
    query.add('nte', 'tajiduo', 'n', {'roles': {'entries': [{'name': '娜娜莉', 'level': 70}, {'name': '白藏', 'level': 60}]}})
    class Queue:
        renderer = SimpleNamespace(invalidate_account=lambda *args: None)
        async def render(self, scope, result, **kwargs):
            return RenderedImage(b'png', page=1, total_pages=1)
    reply = await service(query, queue=Queue()).query_reply(IDENTITY, 'roles', 'nte', image_requested=True, budget_seconds=5)
    assert 'image' in reply and '娜娜莉' in reply['text'] and '白藏' in reply['text']


async def test_new_parser_fields_propagate_through_internal_http_client():
    from datetime import datetime, timedelta, timezone
    from game_assistant.qq.client import InternalQqClient
    from game_assistant.qq.models import InboundMessage
    bodies = []
    def respond(request):
        bodies.append(QueryBody.model_validate(json.loads(request.content)))
        return httpx.Response(200, json={'text': 'ok'})
    http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    api = InternalQqClient('http://127.0.0.1:8020', 'fixture', http=http)
    now = datetime.now(timezone.utc)
    message = InboundMessage(IDENTITY, 'm', '异环 角色 娜娜莉 2', now.isoformat(), (now+timedelta(minutes=5)).isoformat())
    assert await api.execute(message) == 'ok'
    assert bodies[0].game == 'nte' and bodies[0].page == 2 and bodies[0].role_name == '娜娜莉'
    await http.aclose()


def test_internal_page_contract_rejects_cross_account_and_bad_page():
    for changes in ({'page': 0}, {'page': 101}, {'page': True}, {'page': 1.5}, {'page': '2'}, {'account_id': 'other'},
                    {'command': 'refresh', 'page': 2}, {'command': 'summary', 'role_name': 'name'}):
        with pytest.raises(ValueError):
            QueryBody.model_validate({'identity': asdict(IDENTITY), 'command': 'roles', 'game': 'nte', **changes})


def test_wuwa_gacha_reads_existing_owned_ledger_with_no_import_or_upstream(tmp_path):
    from game_assistant.wuwa_gacha import GachaStore
    query = CachedQuery()
    scope = query.add('wuthering_waves', 'kuro', 'ww', {'account': {'nickname': 'W'}})
    root = tmp_path/'private'
    ledger = GachaStore.for_scope(scope, root, role_uid='123456789', server_id='server')
    # Scoped physical file with a real record; QQ only calls read after setup.
    ledger.import_records(scope, [{'uid':'123456789','server_id':'server','time':'2026-10-14 01:00:00','cardPoolType':'1', 'resourceType':'角色',
                                  'resourceId':'1101','name':'今汐','qualityLevel':5}], source='json_import')
    query.private = SimpleNamespace(private_root=root, ledger=lambda s,k: ledger if s==scope and k=='wuwa_gacha' else None)
    text = service(query).query(IDENTITY, 'gacha', 'wuthering_waves')['text']
    assert '记录数：1' in text and '不完整' in text and '123456789' not in text
    ledger.close()


def test_wuwa_missing_ledger_does_not_create_file_or_claim_unsupported(tmp_path):
    query = CachedQuery()
    query.add('wuthering_waves', 'kuro', 'ww', {'account': {'nickname': 'W'}})
    root = tmp_path/'private'
    query.private = SimpleNamespace(private_root=root, ledger=lambda *args: pytest.fail('missing ledger must not be created'))
    text = service(query).query(IDENTITY, 'gacha', 'wuthering_waves')['text']
    assert '未导入' in text and not root.exists()


def test_wuwa_detail_uses_owned_observed_archive_without_upstream(tmp_path):
    from game_assistant.wuwa_history import WuwaHistory
    query=CachedQuery()
    scope=query.add('wuthering_waves','kuro','ww',{'roles':[{'role_id':1101,'name':'今汐','level':80,'weapon':'长刃'}]})
    root=tmp_path/'private'
    ledger=WuwaHistory.for_scope(scope,root,role_uid='123456789',server_id='server')
    ledger.capture(scope,'role_detail',{'role_id':'123456789','server_id':'server','character_id':'1101','data':{
        'weapon_data':{'weapon':{'weapon_name':'时和岁稔'},'level':90,'reson_level':1},
        'skill_list':[{'skill':{'name':f'技能{i}'},'level':6} for i in range(8)],
        'phantom_data':{'cost':12,'equip_phantom_list':[{'phantom_prop':{'name':'角'},'level':25}]},
        'role_attribute_list':[{'attribute_name':'攻击','attribute_value':'2500'}], 'score':999,'token':'secret'}})
    query.private=SimpleNamespace(private_root=root,ledger=lambda s,k:ledger if s==scope and k=='wuwa_history' else None)
    text=service(query).query(IDENTITY,'roles','wuthering_waves',role_name='今汐')['text']
    assert '时和岁稔' in text and '观测时间' in text and 'secret' not in text and '999' not in text
    second=service(query).query(IDENTITY,'roles','wuthering_waves',role_name='今汐',page=2)['text']
    assert '今汐' in second and '观测时间' in second
    ledger.close()


def test_wuwa_basic_cache_explicitly_marks_missing_detail():
    query=CachedQuery()
    query.add('wuthering_waves','kuro','ww',{'roles':[{'name':'今汐','level':80,'weapon':'长刃'}]})
    text=service(query).query(IDENTITY,'roles','wuthering_waves',role_name='今汐')['text']
    assert '详情未采集' in text and '长刃' in text


@pytest.mark.parametrize('raw,command,game,page', [('我的 2','overview',None,2), ('我的账号 2','status',None,2),
    ('鸣潮 总览 2','summary','wuthering_waves',2), ('鸣潮 帮助','help','wuthering_waves',1)])
def test_overview_and_help_page_grammar(raw,command,game,page):
    result=parse_command(raw)
    assert (result.command,result.game,result.page)==(command,game,page)


def test_long_overview_keeps_every_section_in_one_bounded_document():
    query=CachedQuery()
    for game,provider,account in [('wuthering_waves','kuro','ww'),('nte','tajiduo','nte'),('endfield','hypergryph','hg'),('endfield','skland','sk')]:
        base={'nickname': '昵称'+account+'很长'*40,'level':80,'server_name':'服务器'*24,'world_level':6}
        payload={'base':{**base,'name':base['nickname']}} if provider=='skland' else base
        query.add(game,provider,account,{'account':payload})
    context={}
    api=service(query)
    first=api.query(IDENTITY,'overview',image_context=context)['text']
    card=context['card']
    combined=str(card)
    assert all('昵称'+account in combined for account in ('ww','nte','hg','sk'))
    assert len(first)<=1800 and 'page' not in card


async def test_unlink_and_relink_same_user_still_invalidates_inflight_private_card(tmp_path):
    from game_assistant.identity.store import IdentityStore
    from game_assistant.qq.bindings import QqBindingService
    store=IdentityStore(str(tmp_path/'identities.db'))
    with store.connect(write=True) as db:db.execute("INSERT INTO users(user_id,username,password_hash) VALUES('u','u','fixture')")
    bindings=QqBindingService(store,app_id='app')
    principal=Principal('u',False)
    def link():
        code=bindings.create_link_code(principal)['code']
        return bindings.redeem_link_code(IDENTITY,code,'link-'+code)
    old=link()
    query=CachedQuery();query.add('nte','tajiduo','nte',{'account':{'nickname':'PRIVATE'}})
    class Queue:
        renderer=SimpleNamespace(invalidate_account=lambda *args:None)
        async def render(self,scope,result,**kwargs):
            bindings.unlink(principal,old['link_id']);link()
            return None
    api=QqQueryService(bindings,query,None,render_queue=Queue())
    reply=await api.query_reply(IDENTITY,'overview',image_requested=True,budget_seconds=5)
    assert 'PRIVATE' not in reply['text'] and '变更' in reply['text']


@pytest.mark.parametrize('game,command,payload,expected',[
    ('wuthering_waves','resources',{'current':None,'periods':{}},'未知'),
    ('nte','realestate',{'entries':[]},'缓存'),
    ('nte','vehicles',{'entries':[]},'缓存'),
    ('nte','teams',{'entries':[]},'缓存'),
])
def test_extras_cache_capabilities_are_reachable_via_query_and_parser(game,command,payload,expected):
    query=CachedQuery()
    query.add(game,'kuro' if game=='wuthering_waves' else 'tajiduo','a',{command:payload})
    assert parse_command(game+' '+command).command==command
    assert expected in service(query).query(IDENTITY,command,game)['text']


def test_status_legacy_page_and_cold_role_cache_remain_actionable():
    query=CachedQuery()
    for index in range(9):query.add('nte','tajiduo',str(index),{'account':{'nickname':'n'}},default=index==0)
    text=service(query).query(IDENTITY,'status',page=2)['text']
    assert '长图' in text and '已授权' in text
    query.data[('0','roles')]=QueryResult(None,None,'never',None)
    assert '暂无' in service(query).query(IDENTITY,'roles','nte')['text']


def test_detail_does_not_project_scoring_credentials_or_untrusted_urls_from_source_fields():
    query=CachedQuery()
    query.add('nte','tajiduo','n',{'roles':{'entries':[{'name':'角色','level':None,'properties':[
        {'name':'token','value':'NEVER'},{'name':'评分','value':'999'},{'name':'攻击','value':0}],
        'weapon':{'name':'https://untrusted.example/private','level':0},'extra':{'uid':'123456789'}}]}})
    text=service(query).query(IDENTITY,'roles','nte',role_name='角色')['text']
    assert 'NEVER' not in text and '999' not in text and 'untrusted.example' not in text
    assert '攻击：0' in text and '等级：未知' in text


def test_nte_team_image_carries_the_bound_roster_and_unbound_users_keep_the_public_list():
    from game_assistant.qq.bindings import QqBindingError
    query=CachedQuery()
    query.add('nte','tajiduo','n',{'roles':{'entries':[{'name':'娜娜莉'},{'name':'安魂曲'},{'name':''}]}})
    teams=QueryResult({'entries':[{'id':1,'name':'娜娜莉队'}]},'2026-10-14T00:00:00Z','ok',None)
    public=SimpleNamespace(read=lambda game,cap:teams)
    def payload(api):
        context={}
        api.query(IDENTITY,'teams','nte',image_context=context)
        [panel]=context['render_snapshot']['display_data']['panels']
        return panel['snapshot']['payload'],context
    bound=QqQueryService(SimpleNamespace(resolve_qq_identity=lambda i:Principal('u',False)),query,public)
    data,context=payload(bound)
    # The roster is private: it is read through a captured scope, so the image is cached per user
    # and the binding is re-checked after rendering.
    assert data['owned_role_names']==sorted(['娜娜莉','安魂曲'])
    assert context['user_id']=='u' and [scope.account_id for scope,_ in context['grants']]==['n']
    def unbound(identity):raise QqBindingError('qq_binding_required',403)
    data,context=payload(QqQueryService(SimpleNamespace(resolve_qq_identity=unbound),query,public))
    assert 'owned_role_names' not in data and context['user_id'] is None and not context['grants']
