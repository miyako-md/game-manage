"""Anonymous actual response SHAPE: values/identities are invented, not live data."""
from copy import deepcopy
from datetime import datetime,timezone
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_assistant.assessment_equipped import equipped_configuration
from game_assistant.assessment_projection import with_assessment
from game_assistant.assessment_routes import install_assessment_routes
from game_assistant.accounts.models import AccountScope,QueryResult
from game_assistant.qq.render_snapshot import role_snapshot
from tests.test_identity import identity,register

OBSERVED='2026-10-14T16:03:01Z'


def wrapper():
    def stat(name,value,main=False):
        row=dict(attribute_name=name,attribute_value=value,key='anonymous',valid=True)
        if main:row['icon_url']=None
        return row
    echoes=[]
    for i in range(5):
        main=[stat('攻击','10%',True),stat('暴击','10%',True)] if i<3 else [stat('攻击','100',True),stat('生命' if i==3 else '防御','100',True)]
        sub=[stat('生命','100'),stat('暴击伤害','10%'),stat('共鸣效率','10%'),stat('共鸣技能伤害加成','10%'),stat('重击伤害加成','10%')]
        echoes.append(dict(phantom_prop={'id':'resource-'+str(i)},main_props=main,sub_props=sub))
    return dict(schema_version=1,role_id='private-account-uid',server_id='private-server',character_id='c1',
        provenance={'endpoint':'getRoleDetail','fetched_at':OBSERVED},data={
            'role':{'role_id':'c1','role_name':'anonymous'},'phantom_data':{'equip_phantom_list':echoes}})


def test_actual_wrapper_shape_and_legacy_flat_have_same_five_item_contract():
    wrapped=wrapper(); result=equipped_configuration('wuthering_waves','c1',wrapped,OBSERVED)
    assert len(result.items)==5
    stats=[s for i in result.items for s in i.stats]
    assert len(stats)==35 and sum(s.unit=='percent_points' for s in stats)==26 and sum(s.unit=='flat' for s in stats)==9
    # D2: the source's main/sub lists are complete once every entry parses; this shape carries no COST.
    assert all(i.stats_complete is True and i.cost is None for i in result.items)
    assert result==equipped_configuration('wuthering_waves','c1',wrapped['data'],OBSERVED)
    assert result.observed_at==OBSERVED


def test_wrapper_account_identity_mismatch_and_unknown_wrapper_are_rejected():
    wrapped=wrapper()
    assert not equipped_configuration('wuthering_waves','private-account-uid',wrapped).items
    wrong=deepcopy(wrapped);wrong['data']['role']['role_id']='c2'
    assert not equipped_configuration('wuthering_waves','c1',wrong).items
    for unknown in ({'data':wrapped['data']},{**wrapped,'schema_version':999},{'payload':wrapped}):
        assert not equipped_configuration('wuthering_waves','c1',unknown).items


def test_wrapped_assessment_projection_and_shared_render_use_inner_character():
    raw=wrapper(); snapshot=QueryResult(raw,OBSERVED,'ok',None)
    enriched=with_assessment(snapshot,None,AccountScope('u','a','r'),'wuthering_waves')
    assert enriched.payload['data']['assessment']['status']=='unconfigured'
    assert len(enriched.payload['data']['assessment']['item_results'])==5
    projected=role_snapshot('wuthering_waves',snapshot,datetime.now(timezone.utc),detail=enriched,resolved_id='c1')
    assert len(projected['display_data']['detail']['phantom_data']['equip_phantom_list'])==5
    assert 'data' not in projected['display_data']['detail'] and 'private-account-uid' not in str(projected)
    assert role_snapshot('wuthering_waves',snapshot,datetime.now(timezone.utc),detail=enriched,resolved_id='private-account-uid') is None


def test_local_equipped_reads_wrapped_archive_without_touching_source_time(tmp_path):
    app=FastAPI();app.state.settings=SimpleNamespace(db_path=str(tmp_path/'local.db'))
    adapter=SimpleNamespace(credentials_configured=True,_settings=SimpleNamespace(wuwa_role_id='private-account-uid',wuwa_server_id='private-server'))
    app.state.registry=SimpleNamespace(get=lambda game:adapter)
    app.state.auth=SimpleNamespace(account_generation=lambda game:1)
    reads=[]
    def read(account,server,kind,limit,subject=None):
        reads.append((account,server,kind,limit,subject))
        return {'items':[dict(payload=wrapper(),observed_at=OBSERVED,source_at=OBSERVED)]}
    app.state.store=SimpleNamespace(wuwa_history=SimpleNamespace(read=read))
    store=install_assessment_routes(app)
    try:
        response=TestClient(app).get('/api/assessment/wuthering_waves/c1/equipped')
        assert response.status_code==200
        assert len(response.json()['configuration']['items'])==5
        assert response.json()['configuration']['observed_at']==OBSERVED
        assert reads[0][:2]==('private-account-uid','private-server') and reads[0][4]=='c1'
    finally:store.close()


def test_cloud_equipped_reads_only_owned_wrapped_shard_and_retained_time(identity,tmp_path):
    from fastapi import HTTPException
    from game_assistant.wuwa_history import WuwaHistory
    client=identity[3];register(identity)
    principal=client.app.state.identity.authenticate(client.cookies.get('__Host-ga_session')).principal
    scope=AccountScope(principal.user_id,'owned','r')
    class Accounts:
        def require_scope(self,who,account,role):
            if (who.user_id,account,role)!=(scope.user_id,scope.account_id,scope.role_id):raise HTTPException(404,'account_not_found')
            return scope
        def describe(self,current):
            assert current==scope
            return dict(game='wuthering_waves',version=1,game_uid='private-account-uid',server='private-server')
    root=tmp_path/'private'
    archive=WuwaHistory.for_scope(scope,root,role_uid='private-account-uid',server_id='private-server')
    archive.append(scope,'role_detail',wrapper(),subject='c1',source_at=OBSERVED,observed_at=OBSERVED)
    archive.close()
    store=install_assessment_routes(client.app,Accounts(),root)
    try:
        path='/api/accounts/owned/roles/r/assessment/wuthering_waves/c1/equipped'
        response=client.get(path)
        assert response.status_code==200 and len(response.json()['configuration']['items'])==5
        assert response.json()['configuration']['observed_at']==OBSERVED
        assert response.json()['assessment']['status']=='unconfigured' and response.json()['assessment']['value'] is None
        assert client.get(path.replace('/owned/','/other/')).status_code==404
        assert client.get(path.replace('/c1/','/private-account-uid/')).json()['configuration']['items']==[]
    finally:store.close()
