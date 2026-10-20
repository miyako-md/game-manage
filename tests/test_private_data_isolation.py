import json
import sqlite3
import pytest
from game_assistant.accounts.models import AccountScope
from game_assistant.snapshots import SnapshotStore
from game_assistant.nte_gacha import GachaStore as NteStore
from game_assistant.wuwa_gacha import GachaStore as WuwaStore
from game_assistant.wuwa_history import WuwaHistory
from game_assistant.endfield_gacha import EndfieldGachaStore
from game_assistant.endfield_blueprints import BlueprintStore, BlueprintInput

A = AccountScope('user-a','account-a','role-a')
B = AccountScope('user-b','account-b','role-b')

def nte_doc():
    return dict(format='nte-history-export',format_version=1,user_uid='77',
                banner={'id':'Lottery_LimitedCharacter'},scan={'warnings':[]},
                records=[dict(uid='same',pool_group_id='Lottery_LimitedCharacter',
                    timestamp='2026-09-16 12:00:00',timestamp_group_ordinal=0,reward_id='item',
                    reward_rank='B',reward_type='item',result_type='dice',quantity=1)])

@pytest.mark.parametrize('factory',[NteStore,WuwaStore,WuwaHistory,EndfieldGachaStore,BlueprintStore])
def test_scoped_stores_refuse_other_scope_and_missing_scope(factory,tmp_path):
    a = factory.for_scope(A,tmp_path,role_uid='77',server_id='cn')
    b = factory.for_scope(B,tmp_path,role_uid='77',server_id='cn')
    method = 'items' if factory is BlueprintStore else 'summary' if factory in (NteStore,EndfieldGachaStore) else 'read'
    args = ('roles',) if factory is WuwaHistory else ()
    with pytest.raises(PermissionError):
        getattr(a,method)(B,*args)
    with pytest.raises((ValueError,TypeError)):
        getattr(a,method)(None,*args)
    assert a.path != b.path

def test_snapshot_native_scope_keys_and_clear(tmp_path):
    store = SnapshotStore(str(tmp_path/'s.db'))
    store.save_scoped(A,'account',json.dumps({'uid':'77','level':None}),1)
    store.save_scoped(B,'account',json.dumps({'uid':'77','level':2}),1)
    assert json.loads(store.get_scoped(A,'account')['payload'])['level'] is None
    store.clear_scoped(A)
    assert store.get_scoped(A,'account') is None
    assert json.loads(store.get_scoped(B,'account')['payload'])['level']==2
    assert store.get('nte','account') is None
    with pytest.raises(ValueError): store.get_scoped(None,'account')

@pytest.mark.parametrize('factory',[NteStore,WuwaStore,WuwaHistory,EndfieldGachaStore,BlueprintStore])
def test_scoped_writes_dedupe_export_and_delete_are_isolated(factory,tmp_path):
    a,b = (factory.for_scope(s,tmp_path,role_uid='77',server_id='cn') for s in (A,B))
    if factory is NteStore:
        doc=nte_doc(); preview=a.preview(A,doc)
        with pytest.raises(ValueError): b.import_document(B,doc,preview_id=preview['preview_id'])
        for store,scope in ((a,A),(b,B)):
            preview=store.preview(scope,doc)
            assert store.import_document(scope,doc,preview_id=preview['preview_id'])['imported']==1
        assert a.export(A)['user_uid']==b.export(B)['user_uid']=='77'
    elif factory is WuwaStore:
        doc={'role_id':'77','server_id':'cn','list':[{'draw_id':'same','pool':'1','resource_id':'item','name':'item','time':'2026-09-16 12:00:00','rarity':'3'}]}
        assert a.import_records(A,doc)['inserted']==b.import_records(B,doc)['inserted']==1
        assert a.read(A)['total']==b.read(B)['total']==1
    elif factory is WuwaHistory:
        assert a.append(A,'roles',{'level':1})==b.append(B,'roles',{'level':2})==1
        assert a.read(A,'roles')['items'][0]['payload']['level']==1
        assert b.read(B,'roles')['items'][0]['payload']['level']==2
    elif factory is EndfieldGachaStore:
        row={'seq_id':1,'timestamp':1,'name':'same','rarity':3}
        a.add_records(A,'pool',[row]); b.add_records(B,'pool',[row])
        assert len(a.export(A)['records'])==len(b.export(B)['records'])==1
    else:
        item=a.save(A,BlueprintInput(name='a',code='code'))
        with pytest.raises(KeyError): b.save(B,BlueprintInput(name='b',code='code'),item['id'])
        assert not b.delete(B,item['id'])
        assert a.items(A)[0]['name']=='a'
        assert a.delete(A,item['id'])

def test_scope_metadata_mismatch_is_not_adopted(tmp_path):
    store=BlueprintStore.for_scope(A,tmp_path,role_uid='77',server_id='cn')
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE private_scope SET user_id='other'")
    with pytest.raises(PermissionError): store.items(A)


def test_scope_inventory_and_restart(tmp_path):
    from game_assistant.private_data import list_scope_files
    store=BlueprintStore.for_scope(A,tmp_path,role_uid='77',server_id='cn')
    store.save(A,BlueprintInput(name='persist',code='code'))
    reopened=BlueprintStore.for_scope(A,tmp_path,role_uid='77',server_id='cn')
    assert reopened.items(A)[0]['name']=='persist'
    files=list_scope_files(tmp_path)
    assert files[0]['scope']==A and files[0]['path']==store.path


def test_backup_inventory_refuses_a_shard_placed_under_another_owner(tmp_path):
    # Backup and restore list shards through list_scope_files; A's data cannot pass as B's.
    import shutil
    from game_assistant.private_data import list_scope_files, scope_directory
    store=BlueprintStore.for_scope(A,tmp_path,role_uid='77',server_id='cn')
    moved=scope_directory(tmp_path,B)/'blueprints'
    moved.mkdir(parents=True)
    shutil.copy(store.path,moved/store.path.name)
    with pytest.raises(PermissionError,match='disagree'):
        list_scope_files(tmp_path)


def test_snapshot_grant_versions_poll_failure_and_provider_boundaries(tmp_path):
    from game_assistant.models import FetchResult
    store=SnapshotStore(str(tmp_path/'s.db'))
    skland=AccountScope('user-a','skland-account','skland-role')
    hyper=AccountScope('user-a','hyper-account','hyper-role')
    store.save_scoped(skland,'account',json.dumps({'level':None}),2)
    store.save_scoped(hyper,'account',json.dumps({'level':50}),2)
    assert store.get_scoped(skland,'account',grant_version=1) is None
    store.record_poll_scoped(skland,'account',FetchResult(ok=True,payload={}),2)
    status=store.record_poll_scoped(skland,'account',FetchResult(ok=False,error='failure',error_kind='source_error'),2)
    assert status['last_success_at'] and status['consecutive_failures']==1
    assert json.loads(store.get_scoped(skland,'account')['payload'])['level'] is None
    assert store.get_poll_status_scoped(hyper,'account') is None


def test_skland_and_hypergryph_identity_stay_separate(tmp_path):
    import asyncio
    from game_assistant.endfield_skland import EndfieldSklandService
    from tests.test_endfield_skland import FakeClient
    client=FakeClient()
    first=EndfieldSklandService.for_scope(A,dict(cred='first',user_id='u1',role_id='r1',server_id='1'),client=client)
    second=EndfieldSklandService.for_scope(B,dict(cred='second',user_id='u1',role_id='r2',server_id='1'),client=client)
    a=asyncio.run(first.read_card(A)); b=asyncio.run(second.read_card(B))
    assert a['payload']['base']['role_id']=='r1' and b['payload']['base']['role_id']=='r2'
    assert a['payload']['base']['level']==22
    with pytest.raises(PermissionError): asyncio.run(first.read_card(B))
    with pytest.raises(AttributeError): first.sign_attendance(A)
    first.clear(A)
    client.fail_card=True
    assert asyncio.run(first.read_card(A))['payload'] is None
    assert asyncio.run(second.read_card(B))['payload']['base']['role_id']=='r2'


def cloud_fixture(tmp_path,game='endfield',provider='hypergryph'):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from game_assistant.identity.dependencies import require_user
    from game_assistant.identity.models import Principal
    from game_assistant.accounts.service import AccountService
    from game_assistant.auth.store import CredentialStore
    from game_assistant.migrations.cloud_v1 import migrate_cloud_schema
    from tests.test_cloud_schema import add_user,add_account
    from game_assistant.private_routes import install_cloud_private_routes
    connection=sqlite3.connect(':memory:',check_same_thread=False)
    migrate_cloud_schema(connection)
    add_user(connection,A.user_id); add_user(connection,B.user_id)
    add_account(connection,A.user_id,A.account_id,A.role_id,game=game,provider=provider,game_uid='77')
    add_account(connection,B.user_id,B.account_id,B.role_id,game=game,provider=provider,game_uid='77')
    connection.execute("UPDATE grants SET state='active'");connection.commit()
    service=AccountService(connection,CredentialStore(tmp_path/'credentials',connection=connection,key_path=tmp_path/'key'))
    app=FastAPI();app.state.cloud_route_policy=[]
    app.dependency_overrides[require_user]=lambda:Principal(A.user_id,False)
    bundle=install_cloud_private_routes(app,service,None,tmp_path/'private')
    return TestClient(app),app,bundle,connection


def test_private_routes_reject_other_owner_detail_delete_import_export(tmp_path):
    client,app,bundle,connection=cloud_fixture(tmp_path)
    a=f'/api/accounts/{A.account_id}/roles/{A.role_id}/endfield/blueprints'
    b=f'/api/accounts/{B.account_id}/roles/{B.role_id}/endfield/blueprints'
    item=client.post(a,json={'name':'private','code':'code'}).json()
    assert client.get(a).json()['items'][0]['id']==item['id']
    for path in (b,b+'/export',f'/api/accounts/{B.account_id}/roles/{B.role_id}/endfield/gacha/records'):
        assert client.get(path).status_code==404
    assert client.delete(b+'/'+item['id']).status_code==404
    assert client.put(b+'/'+item['id'],json={'name':'changed','code':'code'}).status_code==404
    assert client.post(b,json={'name':'other','code':'code'}).status_code==404
    assert client.get(a+'/export').json()['items'][0]['name']=='private'
    assert client.get(f'/api/accounts/{A.account_id}/roles/{B.role_id}/endfield/blueprints').status_code==404
    assert client.get(f'/api/accounts/{A.account_id}/roles/{A.role_id}/endfield/skland/card').status_code==404


def test_cloud_disables_game_write_actions(tmp_path):
    client,app,bundle,connection=cloud_fixture(tmp_path)
    prefix=f'/api/accounts/{A.account_id}/roles/{A.role_id}'
    assert client.post(prefix+'/endfield/skland/attendance',json={}).status_code in (404,405)
    assert client.post('/api/endfield/skland/attendance',json={}).status_code==404
    assert client.post('/api/endfield/skland/passport',json={}).status_code==404
    assert client.post('/api/lol/collect',json={}).status_code==404
    assert all('sign_attendance' not in route.endpoint.__name__ for route in bundle_route_objects(app))


def test_cloud_weapon_record_filter_stays_inside_the_authorized_role(tmp_path):
    import asyncio
    from tests.test_endfield_gacha import FakeClient,history,weapon_draws
    client,app,bundle,connection=cloud_fixture(tmp_path)
    first=bundle.ledger(A,'endfield_gacha')
    second=bundle.ledger(B,'endfield_gacha')
    fake=FakeClient(special=history(1,20),weapons={'weapon_1':('合成申领',weapon_draws(1,4))})
    asyncio.run(first.sync(A,fake,'u8',interval=0))
    asyncio.run(second.sync(B,fake,'u8',interval=0))
    path=f'/api/accounts/{A.account_id}/roles/{A.role_id}/endfield/gacha/records'
    page=client.get(path,params={'kind':'weapon','limit':2,'offset':1})
    assert page.status_code==200
    assert page.json()['total']==4 and [row['seq_id'] for row in page.json()['records']]==['3','2']
    assert all(row['kind']=='weapon' for row in page.json()['records'])
    assert client.get(path,params={'kind':'invalid'}).status_code==422
    other=f'/api/accounts/{B.account_id}/roles/{B.role_id}/endfield/gacha/records?kind=weapon'
    assert client.get(other).status_code==404


def bundle_route_objects(app):
    from game_assistant.private_routes import iter_routes
    return list(iter_routes(app.routes))


@pytest.mark.parametrize('unclassified_path',['/api/unclassified-route','/api/system/unclassified-route'])
def test_complete_local_route_inventory_rejects_unknown(tmp_path,unclassified_path):
    from game_assistant.api import create_app
    from game_assistant.config import Settings
    from game_assistant.registry import GameRegistry
    from game_assistant.private_routes import local_route_inventory
    app=create_app(settings=Settings(db_path=str(tmp_path/'local.db')),registry=GameRegistry(),start_scheduler=False)
    inventory=local_route_inventory(app)
    assert len(inventory)>60
    assert {item['category'] for item in inventory}<={'private_query','private_modify','public_read_only','admin_sources','admin_system','internal_qq','disabled'}
    assert [item for item in inventory if item['category']=='admin_system'] == [
        {'method':'GET','path':'/api/system/update','category':'admin_system','cloud_policy':'admin_required'},
        {'method':'POST','path':'/api/system/update/apply','category':'admin_system','cloud_policy':'admin_required'},
        {'method':'POST','path':'/api/system/update/check','category':'admin_system','cloud_policy':'admin_required'},
    ]
    assert next(item for item in inventory if item['path']=='/api/endfield/skland/attendance' and item['method']=='POST')['cloud_policy']=='disabled'
    passport = next(item for item in inventory if item['path']=='/api/endfield/skland/passport' and item['method']=='POST')
    assert passport['category']=='private_modify' and passport['cloud_policy']=='disabled_legacy'
    assert next(item for item in inventory if item['path']=='/api/sources/bilibili/{game}/refresh')['category']=='admin_sources'
    assert next(item for item in inventory if item['path']=='/api/auth/bilibili-source/login/status')['category']=='admin_sources'
    @app.get(unclassified_path)
    def unclassified(): return {}
    with pytest.raises(ValueError,match='Unclassified'):
        local_route_inventory(app)


def test_cloud_nte_import_ticket_and_export_owner_boundary(tmp_path):
    client,app,bundle,connection=cloud_fixture(tmp_path,'nte','tajiduo')
    a=f'/api/accounts/{A.account_id}/roles/{A.role_id}/nte/gacha'
    b=f'/api/accounts/{B.account_id}/roles/{B.role_id}/nte/gacha'
    body={'document':nte_doc()}
    preview=client.post(a+'/preview',json=body)
    assert preview.status_code==200
    body['preview_id']=preview.json()['preview_id']
    assert client.post(b+'/import',json=body).status_code==404
    assert client.post(a+'/import',json=body).json()['imported']==1
    assert client.get(b+'/export').status_code==404
    assert client.get(a+'/export').json()['user_uid']=='77'
    assert client.get(a+'/records').json()['records'][0]['uid']=='same'


def test_shard_orphan_and_identity_change_rejected(tmp_path):
    from game_assistant.private_data import scope_directory
    path=scope_directory(tmp_path,A)/'nte'/'ledger.sqlite3'
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE records(role TEXT)')
    with pytest.raises(PermissionError): NteStore.for_scope(A,tmp_path,role_uid='77',server_id='cn')
    blueprint=BlueprintStore.for_scope(A,tmp_path,role_uid='77',server_id='cn')
    with pytest.raises(PermissionError): BlueprintStore.for_scope(A,tmp_path,role_uid='different',server_id='cn')


def _installed_cloud_route_cases():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        client,app,bundle,connection=cloud_fixture(Path(directory))
        cases=[(method,path) for path,methods,category in bundle.routes for method in methods]
        bundle.close();connection.close()
        return cases


@pytest.mark.parametrize('method,path',_installed_cloud_route_cases())
def test_every_installed_private_route_resolves_owner(method,path,tmp_path):
    client,app,bundle,connection=cloud_fixture(tmp_path)
    path=path.replace('{account_id}',B.account_id).replace('{role_id}',B.role_id)
    path=path.replace('{identity}','same').replace('{character_id}','1001').replace('{char_id}','c1')
    path=path.replace('{kind}','month').replace('{period}','202610')
    body={'name':'private','code':'code'} if '/blueprints' in path else {}
    response=client.request(method,path,json=body)
    assert response.status_code==404
    assert response.json()['error_code']=='account_not_found'


def test_history_capture_rejects_foreign_uid_and_clear_never_reassigns(tmp_path):
    a=WuwaHistory.for_scope(A,tmp_path,role_uid='77',server_id='cn')
    b=WuwaHistory.for_scope(B,tmp_path,role_uid='88',server_id='cn')
    payload={'role_id':'77','server_id':'cn','character_id':'1001','level':10}
    assert a.capture(A,'role_detail',payload)==1
    assert b.capture(B,'role_detail',payload)==0
    a.close()
    assert WuwaHistory.for_scope(A,tmp_path,role_uid='77',server_id='cn').read(A,'role_detail')['total']==1
    assert b.read(B,'role_detail')['total']==0


def test_private_cleanup_retains_ledger_and_only_clears_scope(tmp_path):
    client,app,bundle,connection=cloud_fixture(tmp_path)
    snapshots=SnapshotStore(str(tmp_path/'snapshots.db'));bundle.snapshots=snapshots
    for scope in (A,B): snapshots.save_scoped(scope,'account','{}',1)
    bundle.ledger(A,'blueprints').save(A,BlueprintInput(name='history',code='code'))
    bundle.clear_private(A)
    assert snapshots.get_scoped(A,'account') is None and snapshots.get_scoped(B,'account') is not None
    assert bundle.ledger(A,'blueprints').items(A)[0]['name']=='history'


def test_poll_failure_uses_existing_scoped_snapshot_success_time(tmp_path):
    from game_assistant.models import FetchResult
    store=SnapshotStore(str(tmp_path/'s.db'))
    store.save_scoped(A,'account','{}',1)
    snapshot=store.get_scoped(A,'account')
    status=store.record_poll_scoped(A,'account',FetchResult(ok=False,error='unavailable',error_kind='source_error'),1)
    assert status['last_success_at']==snapshot['fetched_at']


def test_cloud_boundary_with_event_loop_account_connection(tmp_path):
    from contextlib import asynccontextmanager
    from fastapi.testclient import TestClient
    from game_assistant.cloud_app import create_cloud_app
    from game_assistant.config import Settings
    from game_assistant.accounts.service import AccountService
    from game_assistant.private_routes import install_cloud_private_routes
    from tests.test_cloud_schema import add_account
    from tests.test_identity import write
    settings=Settings(db_path=str(tmp_path/'local.db'),cloud_db_path=str(tmp_path/'cloud.db'),
                      cloud_allowed_origins=['https://cloud.example'])
    app=create_cloud_app(settings,start_scheduler=False)
    admin=app.state.identity.bootstrap_admin('admin','Admin-password-123')
    with sqlite3.connect(settings.cloud_db_path) as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        add_account(connection,admin.user_id,'cloud-account','cloud-role',game='endfield',provider='hypergryph')
        connection.execute("UPDATE grants SET state='active'")
    accounts=AccountService(None,None)
    bundle=install_cloud_private_routes(app,accounts,None,tmp_path/'private')
    bundle.allowlist(app)
    @asynccontextmanager
    async def lifespan(app):
        accounts.connection=sqlite3.connect(settings.cloud_db_path)
        accounts.connection.execute('PRAGMA foreign_keys=ON')
        try: yield
        finally:
            bundle.close();accounts.connection.close()
    app.router.lifespan_context=lifespan
    path='/api/accounts/cloud-account/roles/cloud-role/endfield/blueprints'
    with TestClient(app,base_url='https://cloud.example') as client:
        assert client.get(path).status_code==401
        assert write(client,'/api/identity/login',{'username':'admin','password':'Admin-password-123'}).status_code==200
        assert client.post(path,json={'name':'private','code':'code'}).status_code==403
        created=write(client,path,{'name':'private','code':'code'})
        assert created.status_code==201
        assert client.get(path).json()['items'][0]['name']=='private'
        assert client.get('/api/endfield/blueprints').status_code==404


def test_cloud_import_rechecks_grant_after_network_await(tmp_path,monkeypatch):
    from game_assistant import private_routes
    client,app,bundle,connection=cloud_fixture(tmp_path,'wuthering_waves','kuro')
    async def official(*args):
        connection.execute("UPDATE grants SET version=version+1 WHERE grant_id=?",('grant-'+A.account_id,));connection.commit()
        return dict(records={'role_id':'77','server_id':'cn','list':[]},failed_pools=[],source='official_query')
    monkeypatch.setattr(private_routes,'fetch_official',official)
    path=f'/api/accounts/{A.account_id}/roles/{A.role_id}/wuwa/gacha/preview'
    assert client.post(path,json={'url':'https://example.invalid'}).status_code==409
    assert bundle.ledger(A,'wuwa_gacha').read(A)['total']==0


def test_cloud_wuwa_preview_owner_replay_and_grant_version(tmp_path):
    client,app,bundle,connection=cloud_fixture(tmp_path,'wuthering_waves','kuro')
    base=f'/api/accounts/{A.account_id}/roles/{A.role_id}/wuwa/gacha'
    document={'info':{'uid':'77','server_id':'cn'},'list':[
        dict(id='one',pool='1',resource_id='unknown',rarity=5,time='2026-01-01')]}
    response=client.post(base+'/preview',json={'records':document})
    assert response.status_code==200
    assert client.post(base+'/import',json={'records':document}).status_code==422
    assert client.post(base+'/import',json={'url':'https://example.invalid'}).status_code==422
    assert bundle.ledger(A,'wuwa_gacha').read(A)['total']==0
    token=response.json()['preview_id']
    assert client.post(base+'/import',json={'preview_id':token}).json()['inserted']==1
    assert client.post(base+'/import',json={'preview_id':token}).status_code==409
    assert client.get(base+'/export').status_code==200
    token=client.post(base+'/preview',json={'records':document}).json()['preview_id']
    connection.execute('UPDATE grants SET version=version+1 WHERE grant_id=?',('grant-'+A.account_id,));connection.commit()
    assert client.post(base+'/import',json={'preview_id':token}).status_code==409
    other=f'/api/accounts/{B.account_id}/roles/{B.role_id}/wuwa/gacha'
    assert client.post(other+'/import',json={'preview_id':token}).status_code==404
