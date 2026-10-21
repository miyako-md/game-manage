import json
from fastapi import HTTPException
from game_assistant.assessment_routes import install_assessment_routes
from game_assistant.accounts.models import AccountScope
from tests.test_identity import identity, register, write
from tests.test_personal_assessment import config,wuwa_model


class Accounts:
    revoked=False
    def require_scope(self,principal,account,role):
        if self.revoked or account!='owned' or role!='role': raise HTTPException(404,'account_not_found')
        return AccountScope(principal.user_id,account,role)
    def describe(self,scope):
        if self.revoked: raise HTTPException(404,'account_not_found')
        return dict(game='wuthering_waves',version=1)


class NteAccounts(Accounts):
    def describe(self,scope): return dict(game='nte',version=1)


def test_authorized_model_save_configuration_compare_csrf_and_revocation(identity,tmp_path):
    client=identity[3]; accounts=Accounts()
    store=install_assessment_routes(client.app,accounts,tmp_path/'private')
    path='/api/accounts/owned/roles/role/assessment/wuthering_waves/c1'
    assert client.get(path).status_code==401
    register(identity)
    assert client.put(path+'/model',json=wuwa_model().model_dump(mode='json')).status_code==403
    assert write(client,path+'/model',wuwa_model().model_dump(mode='json'),method='put').status_code==200
    a=write(client,path+'/configurations',config().model_dump(mode='json')).json()['id']
    b=write(client,path+'/configurations',config().model_dump(mode='json')).json()['id']
    assert write(client,path+'/compare',dict(a=a,b=b)).json()['percent_delta']=='0.00'
    assert write(client,path+'/score',dict(id=a)).json()['value']=='20.00'
    assert client.get(path.replace('owned','other')).status_code==404
    assert client.get(path.replace('c1','other')).json()['configurations']==[]
    register(identity,username='bob')
    assert client.get(path).json()['configurations']==[]
    assert write(client,path+'/score',dict(id=a)).status_code==404
    accounts.revoked=True
    assert client.get(path).status_code==404
    assert write(client,path+'/model',wuwa_model().model_dump(mode='json'),method='put').status_code==404
    store.close()


def test_scoped_persistence_reopens_and_refuses_body_identity_and_source(identity,tmp_path):
    client=identity[3]; accounts=Accounts(); store=install_assessment_routes(client.app,accounts,tmp_path/'private')
    register(identity)
    path='/api/accounts/owned/roles/role/assessment/wuthering_waves/c1'
    bad=config().model_dump(mode='json');bad['character_id']='other'
    assert write(client,path+'/configurations',bad).status_code==422
    bad=config().model_dump(mode='json');bad['source']='equipped_snapshot'
    assert write(client,path+'/configurations',bad).status_code==422
    row=write(client,path+'/configurations',config().model_dump(mode='json')).json()
    assert write(client,path+'/score',dict(id=row['id'])).json()['status']=='unconfigured'
    assert write(client,path+'/configurations',{'user_id':'forged',**config().model_dump(mode='json')}).status_code==422
    assert write(client,path+'/configurations/'+row['id'],method='delete').status_code==200
    assert client.get(path).json()['configurations']==[]
    csrf=client.get('/api/identity/csrf').json()['csrf_token']
    assert client.post(path+'/configurations',content=b'{"padding":"'+b'x'*(128*1024)+b'"}',headers={'X-CSRF-Token':csrf}).status_code==413
    store.close()


def test_equipped_normalization_keeps_unknown_and_percentage_units():
    from game_assistant.assessment_equipped import equipped_configuration
    n=equipped_configuration('nte','c1',{'entries':[{'id':'c1','suit':{'core':[{'id':'i','properties':[{'id':'p','value':'3'}]}]}}]})
    assert n.items[0].kind is None and n.items[0].nte is None
    assert n.items[0].source_group=='core' and n.items[0].stats[0].unit is None
    w=equipped_configuration('wuthering_waves','c1',{'role':{'role_id':'c1'},'phantom_data':{'equip_phantom_list':[{'main_props':[{'attribute_name':'攻击','attribute_value':'10%'}],'sub_props':[{'attribute_name':'暴击','attribute_value':'0%'}]}]}})
    assert w.items[0].stats[0].canonical_id=='attack_ratio' and w.items[0].stats[0].value=='10'
    assert w.items[0].stats[1].value=='0' and w.items[0].stats[1].unit=='percent_points'
    repeated=equipped_configuration('nte','c1',{'entries':[{'id':'c1','suit':{'core':[{'id':'same'},{'id':'same'}]}}]})
    assert len({i.id for i in repeated.items})==2 and all(i.source_id=='same' for i in repeated.items)


def test_equipped_reading_skips_empty_slots_and_missing_lists():
    # Sources leave unequipped slots as null (the dashboard and QQ already drop them).
    from game_assistant.assessment_equipped import equipped_configuration
    echo={'main_props':[{'attribute_name':'攻击','attribute_value':'10%'}],'sub_props':[None]}
    w=equipped_configuration('wuthering_waves','c1',{'role':{'role_id':'c1'},'phantom_data':{'equip_phantom_list':[None,echo]}})
    assert [(i.id,len(i.stats)) for i in w.items]==[('echo:1:unknown',1)]
    assert equipped_configuration('wuthering_waves','c1',{'role':{'role_id':'c1'},'phantom_data':{'equip_phantom_list':None}}).items==[]
    n=equipped_configuration('nte','c1',{'entries':[{'id':'c1','suit':{'core':[None,{'id':'i','properties':None}],'pie':None}}]})
    assert [(i.id,i.stats) for i in n.items]==[('core:1:i',[])]


def detail_snapshot(character='1205'):
    from game_assistant.accounts.models import QueryResult
    from tests.test_assessment_defaults import CHANGLI
    def source(item):
        # Kuro role detail shape: main/sub lists of attribute_name/attribute_value, COST on the echo.
        names={'crit_rate':'暴击','crit_damage':'暴击伤害','attack_ratio':'攻击','attack_flat':'攻击','health_ratio':'生命','health_flat':'生命',
               'defense_ratio':'防御','defense_flat':'防御','energy_regen':'共鸣效率','fusion_damage':'热熔伤害加成','skill_damage':'共鸣技能伤害加成',
               'liberation_damage':'共鸣解放伤害加成','basic_damage':'普攻伤害加成','heavy_damage':'重击伤害加成'}
        prop=lambda s:dict(attribute_name=names[s['canonical_id']],attribute_value=s['value']+('' if s['unit']=='flat' else '%'))
        return dict(cost=item['cost'],phantom_prop={'phantom_id':390080005+int(item['id'][-1]),'cost':item['cost']},
                    main_props=[prop(s) for s in item['stats'] if s['role']=='main'],sub_props=[prop(s) for s in item['stats'] if s['role']=='sub'])
    return QueryResult({'role':{'role_id':character,'role_name':'synthetic'},'token':'secret',
        'phantom_data':{'equip_phantom_list':[source(i) for i in CHANGLI]}},'2026-10-14T00:00:00Z','ok',None)


def test_projection_uses_scope_model_else_builtin_default_and_strips_unrelated_private_data(tmp_path):
    from game_assistant.assessment_store import AssessmentStore
    from game_assistant.assessment_projection import with_assessment
    from game_assistant.assessment_equipped import equipped_configuration
    from game_assistant.qq.render_snapshot import role_snapshot
    from datetime import datetime,timezone
    store=AssessmentStore(tmp_path/'score.db'); scope=AccountScope('u','a','r')
    snap=detail_snapshot()
    items=equipped_configuration('wuthering_waves','1205',snap.payload).items
    assert [(i.source_id,i.cost,i.stats_complete) for i in items][:2]==[('390080005',4,True),('390080006',3,True)]
    value=with_assessment(snap,store,scope,'wuthering_waves')
    assessment=value.payload['assessment']
    assert (assessment['status'],assessment['value'],assessment['origin'],assessment['attribution'])==('scored','168.16','builtin_default','gpl_snapshot')
    projected=role_snapshot('wuthering_waves',snap,datetime.now(timezone.utc),detail=value,resolved_id='1205')
    shown=projected['display_data']['detail']['assessment']
    assert {k:shown[k] for k in ('value','grade','max_value','origin','unofficial','attribution')}=={'value':'168.16','grade':'a','max_value':250,
        'origin':'builtin_default','unofficial':True,'attribution':'gpl_snapshot'}
    assert [(i['cost'],i['grade'],i['max_value']) for i in shown['item_results']][:2]==[(4,'ss',50),(3,'ss',50)]
    echo_ids=[e['phantom_prop']['phantom_id'] for e in projected['display_data']['detail']['phantom_data']['equip_phantom_list']]
    assert [i['item_id'] for i in shown['item_results']]==[f'echo:{n}:{p}' for n,p in enumerate(echo_ids)]
    assert 'token' not in projected['display_data']['detail']
    # A saved model wholly replaces the default, only for its own scope.
    store.save(scope,wuwa_model({'attack_flat':'0.1'}).model_copy(update=dict(character_id='1205')),'model')
    mine=with_assessment(snap,store,scope,'wuthering_waves').payload['assessment']
    assert (mine['origin'],mine['grade'],mine['formula'])==('user_configured',None,'wuwa-custom-weighted-values-v1')
    assert with_assessment(snap,store,AccountScope('other','a','r'),'wuthering_waves').payload['assessment']['origin']=='builtin_default'
    # Without a default entry: unconfigured, which QQ images hide.
    none=with_assessment(detail_snapshot('c1'),store,scope,'wuthering_waves').payload['assessment']
    assert (none['status'],none['reason'],none['model_version'],none['origin'])==('unconfigured','NO_WEIGHTS','unconfigured','user_configured')
    store.close()


def test_model_put_refuses_builtin_source_and_delete_restores_the_default(identity,tmp_path):
    client=identity[3]; store=install_assessment_routes(client.app,Accounts(),tmp_path/'private')
    register(identity)
    path='/api/accounts/owned/roles/role/assessment/wuthering_waves/1205'
    builtin=client.get(path).json()['model']
    assert (builtin['source'],builtin['attribution'])==('builtin_default','gpl_snapshot')
    assert write(client,path+'/model',builtin,method='put').status_code==422
    # The editor saves a copy of the default as the user's own model; it keeps the echo formula.
    saved=write(client,path+'/model',dict(builtin,source='user_configured'),method='put')
    assert saved.status_code==200 and saved.json()['data']==dict(builtin,source='user_configured',attribution=None)
    assert client.get(path).json()['model']['source']=='user_configured'
    from game_assistant.assessment import AssessmentModel, assess
    from tests.test_assessment_defaults import golden
    copy=assess(golden(),AssessmentModel.model_validate(saved.json()['data']))
    assert (copy['value'],copy['grade'],copy['origin'],copy['unofficial'],copy['attribution'])==('168.16','a','user_configured',None,None)
    assert client.delete(path+'/model').status_code==403
    assert write(client,path+'/model',method='delete').json()=={'deleted':True}
    assert client.get(path).json()['model']==builtin
    assert write(client,path+'/model',method='delete').json()=={'deleted':False}
    empty=client.get(path.replace('1205','c1')).json()['model']
    assert (empty['version'],empty['source'],empty['wuwa_echo_profile'])==('unconfigured','user_configured',None)
    store.close()


def test_nte_model_whose_weights_do_not_fit_its_catalog_is_refused(identity,tmp_path):
    # Saved, such a model would make every later NTE score unscorable (INVALID_WEIGHT).
    from tests.test_personal_assessment import nte_model
    client=identity[3]; store=install_assessment_routes(client.app,NteAccounts(),tmp_path/'private')
    register(identity)
    path='/api/accounts/owned/roles/role/assessment/nte/c1/model'
    good=nte_model().model_dump(mode='json')
    main_weight_on_a_sub_only_row=dict(good,nte_profile=dict(good['nte_profile'],mainstat_weights={'attack':'1'}))
    assert write(client,path,main_weight_on_a_sub_only_row,method='put').status_code==422
    assert write(client,path,good,method='put').status_code==200
    store.close()


def test_observation_id_bound_is_checked_on_save_and_old_rows_fail_scoring_alike(identity,tmp_path):
    # Two copies of one substat collapse into collapsed_observation_ids, which holds at most 256 characters.
    # A 257-character ID used to be saved, then made /score answer 422 and /compare crash with a 500.
    from tests.test_personal_assessment import nte_model
    client=identity[3]; store=install_assessment_routes(client.app,NteAccounts(),tmp_path/'private')
    register(identity)
    path='/api/accounts/owned/roles/role/assessment/nte/c1'
    model=nte_model().model_dump(mode='json')
    assert write(client,path+'/model',model,method='put').status_code==200
    def configuration(observation):
        stat=dict(canonical_id='attack',observation_id=observation,value='10',unit='flat')
        return dict(game='nte',character_id='c1',name='json',source='user_configured',
            items=[dict(id='i1',nte=dict(kind='drive',quality='custom',area='4',substats_complete=True,substats=[stat,dict(stat)]))])
    def failure(response): return response.status_code,response.json().get('detail')
    good=write(client,path+'/configurations',configuration('x'*256)).json()['id']
    assert write(client,path+'/compare',dict(a=good,b=good)).json()['a']['value']=='8.00'
    assert failure(write(client,path+'/configurations',configuration('x'*257)))==(422,'invalid_input')
    assert failure(write(client,path+'/score',dict(configuration=configuration('x'*257))))==(422,'invalid_input')
    # A row stored before the bound stays listed and deletable; scoring or comparing it is refused the same way.
    stale=write(client,path+'/configurations',configuration('x')).json()['id']
    with store.db: store.db.execute('UPDATE personal_assessment SET payload=? WHERE id=?',(json.dumps(configuration('x'*257)),stale))
    assert [row['id'] for row in client.get(path).json()['configurations']]==[good,stale]
    assert failure(write(client,path+'/score',dict(id=stale)))==(422,'invalid_scoring_input')
    assert failure(write(client,path+'/compare',dict(a=good,b=stale)))==(422,'invalid_scoring_input')
    assert write(client,path+'/configurations/'+stale,method='delete').status_code==200
    # A stored model that no longer validates fails /compare as it fails /score.
    with store.db: store.db.execute("UPDATE personal_assessment SET payload=? WHERE kind='model'",(json.dumps(dict(model,version='v'*257)),))
    for route,body in (('/score',dict(id=good)),('/compare',dict(a=good,b=good))):
        assert failure(write(client,path+route,body))==(422,'invalid_scoring_input')
    store.close()


def test_local_equipped_finds_the_character_behind_newer_rows_of_others(tmp_path):
    # Reading only the account's newest 100 detail rows lost a character once another changed 100 times.
    import sqlite3, threading
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from game_assistant.wuwa_history import WuwaHistory
    history=WuwaHistory(sqlite3.connect(':memory:',check_same_thread=False),threading.Lock())
    def detail(character,level=90):
        echo=dict(phantom_prop={'id':'res'},main_props=[dict(attribute_name='攻击',attribute_value='10%')],sub_props=[])
        return dict(schema_version=1,role_id='uid-w',server_id='srv',character_id=character,
            provenance={'endpoint':'getRoleDetail','fetched_at':'2026-10-14T00:00:00Z'},
            data={'role':{'role_id':character,'level':level},'phantom_data':{'equip_phantom_list':[echo]}})
    history.capture('role_detail',detail('c1'),expected=('uid-w','srv'))
    for level in range(100):history.capture('role_detail',detail('c2',level),expected=('uid-w','srv'))
    app=FastAPI()
    app.state.settings=SimpleNamespace(db_path=str(tmp_path/'local.db'))
    adapter=SimpleNamespace(credentials_configured=True,_settings=SimpleNamespace(nte_role_id='uid-n',wuwa_role_id='uid-w',wuwa_server_id='srv'))
    app.state.registry=SimpleNamespace(get=lambda game:adapter)
    app.state.auth=SimpleNamespace(account_generation=lambda game:1)
    app.state.store=SimpleNamespace(wuwa_history=history)
    store=install_assessment_routes(app)
    try:
        body=TestClient(app).get('/api/assessment/wuthering_waves/c1/equipped').json()
        assert len(body['configuration']['items'])==1
    finally:store.close()


def test_cloud_equipped_survives_token_rotation_but_not_reauthorization(tmp_path):
    from fastapi.testclient import TestClient
    from game_assistant.cloud_app import create_cloud_app
    from game_assistant.auth.service import ScopedLoginService
    from game_assistant.identity.models import Principal
    from tests.test_account_queries import cloud_settings
    from tests.test_account_auth import Provider
    app = create_cloud_app(cloud_settings(tmp_path), start_scheduler=False)
    admin = app.state.identity.bootstrap_admin('admin', 'Admin-password-123')
    with TestClient(app, base_url='https://cloud.example') as client:
        write(client,'/api/identity/login',{'username':'admin','password':'Admin-password-123'})
        principal = Principal(admin.user_id,True)
        credentials = {'center_uid':'u','role_id':'77','access_token':'token','device_id':'device'}
        def seed():
            row = app.state.accounts.save_verified(principal,'tajiduo',credentials)
            scope = app.state.accounts.require_scope(principal,row['account_id'],row['role_id'])
            app.state.store.save_scoped(scope,'roles',json.dumps({'entries':[{'id':'c1',
                'suit':{'core':[{'id':'i','properties':[{'id':'p','value':'3'}]}]}}]}),row['version'])
            return row
        row = client.portal.call(seed)
        path = f"/api/accounts/{row['account_id']}/roles/{row['role_id']}/assessment/nte/c1/equipped"
        before = client.get(path)
        assert before.status_code == 200
        assert len(before.json()['configuration']['items']) == 1
        login = ScopedLoginService(app.state.accounts,providers={'tajiduo':Provider()})
        client.portal.call(login.renew,principal,row['grant_id'])
        assert client.get(path).json()['configuration'] == before.json()['configuration']
        client.portal.call(app.state.accounts.save_verified,principal,'tajiduo',credentials)
        assert client.get(path).json()['configuration']['items'] == []
