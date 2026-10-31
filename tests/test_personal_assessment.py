import pytest
from game_assistant.assessment import AssessmentModel, Configuration, assess, compare


def wuwa_model(weights=None, version='v1'):
    return AssessmentModel.model_validate(dict(game='wuthering_waves',character_id='c1',version=version,
        source='user_configured',wuwa_weights=weights if weights is not None else {'attack_flat':'0.1','crit_rate':'100'}))


def config(stats=None, character='c1'):
    return Configuration.model_validate(dict(game='wuthering_waves',character_id=character,name='A',source='user_configured',
        items=[dict(id='echo1',stats_complete=True,stats=stats if stats is not None else [dict(canonical_id='attack_flat',value='100',unit='flat'),dict(canonical_id='crit_rate',value='10',unit='percent_points')])]))


def test_wuwa_independent_units_contributions_and_three_states():
    result = assess(config(),wuwa_model())
    assert result['value']=='20.00' and [p['value'] for p in result['contributions']]==['10','10']
    assert assess(config(),wuwa_model({}))['status']=='unconfigured'
    assert assess(config([dict(canonical_id='attack_flat',value='100',unit='ratio')]),wuwa_model())['status']=='unscorable'
    assert assess(config([dict(canonical_id='attack_flat',value='0',unit='flat'),dict(canonical_id='crit_rate',value='0',unit='ratio')]),wuwa_model())['value']=='0.00'
    incomplete=config([dict(canonical_id='attack_flat',value='100',unit='flat')]).model_dump(mode='json')
    incomplete['items'][0]['stats_complete']=None
    assert assess(Configuration.model_validate(incomplete),wuwa_model())['status']=='unscorable'
    assert assess(config([dict(canonical_id='attack_flat',value='100',unit='flat')]),wuwa_model())['value']=='10.00'


def test_same_character_compare_rescores_model_and_zero_baseline():
    a=config(); b=config([dict(canonical_id='attack_flat',value='200',unit='flat'),dict(canonical_id='crit_rate',value='20',unit='percent_points')])
    result=compare(a,b,wuwa_model(version='v2'))
    assert result['percent_delta']=='100.00' and result['model_version']=='v2'
    with pytest.raises(ValueError): compare(a,config(character='other'),wuwa_model())
    zero=config([dict(canonical_id='attack_flat',value='0',unit='flat'),dict(canonical_id='crit_rate',value='0',unit='ratio')])
    assert compare(zero,b,wuwa_model())['percent_delta'] is None


def test_nte_configured_single_item_keeps_exact_math_and_unknown_quality():
    model=AssessmentModel.model_validate(dict(game='nte',character_id='c1',version='personal-v1',source='user_configured',
        nte_profile=dict(character_id='c1',version='weights-v1',source='user_configured',substat_weights={'attack':'1','crit':'3'},mainstat_weights={}),
        nte_spec=dict(version='spec-v1',quality_factors={'custom':'0.8'},eligible_substats=['attack','crit'],
            catalog=[dict(canonical_id=x,label=x,kinds=['drive'],main=False,sub=True,unit='flat') for x in ('attack','crit')],mainstat_reference_values=[])))
    c=Configuration.model_validate(dict(game='nte',character_id='c1',name='custom',source='user_configured',items=[dict(id='i1',nte=dict(kind='drive',quality='custom',area='4',substats_complete=True,substats=[dict(canonical_id='attack',observation_id='a',value='999',unit='flat')]))]))
    # 10*4*0.8*1/(1+3)=8; observed value 999 doesn't affect presence weighting.
    result=assess(c,model)
    assert result['value']=='8.00' and result['contributions'][0]['exact_fraction']=={'numerator':'8','denominator':'1'}
    broken=c.model_dump(mode='json');broken['items'][0]['nte']['quality']=None
    assert assess(Configuration.model_validate(broken),model)['reason']=='UNKNOWN_QUALITY'


def test_changed_selected_model_recalculates_both_configurations():
    a=config();b=config([dict(canonical_id='attack_flat',value='200',unit='flat'),dict(canonical_id='crit_rate',value='10',unit='percent_points')])
    first=compare(a,b,wuwa_model())
    second=compare(a,b,wuwa_model({'attack_flat':'1','crit_rate':'0'},version='v2'))
    assert first['percent_delta']=='50.00' and second['percent_delta']=='100.00'
    assert first['a']['model_fingerprint']!=second['a']['model_fingerprint']
    assert second['a']['model_fingerprint']==second['b']['model_fingerprint']


def test_explicit_zero_weights_and_invalid_fixed_point_are_distinct():
    assert assess(config(),wuwa_model({'attack_flat':'0','crit_rate':'0'}))['value']=='0.00'
    assert assess(config([dict(canonical_id='attack_flat',value='1e999999999',unit='flat'),dict(canonical_id='crit_rate',value='0',unit='ratio')]),wuwa_model())['status']=='unscorable'


def test_main_sub_observations_complete_absence_and_duplicate_guard():
    c=config([dict(canonical_id='attack_flat',value='100',unit='flat',role='main',observation_id='m'),
              dict(canonical_id='attack_flat',value='20',unit='flat',role='sub',observation_id='s')])
    assert assess(c,wuwa_model())['value']=='12.00'
    rows=c.model_dump(mode='json'); rows['items'][0]['stats'].append(rows['items'][0]['stats'][1].copy())
    assert assess(Configuration.model_validate(rows),wuwa_model())['value']=='12.00'
    rows['items'][0]['stats'][2]['value']='30'
    assert assess(Configuration.model_validate(rows),wuwa_model())['reason']=='CONFLICTING_OBSERVATION'


def test_compare_uses_exact_values_when_display_scores_round_to_zero():
    a=config([dict(canonical_id='attack_flat',value='0.004',unit='flat')])
    b=config([dict(canonical_id='attack_flat',value='0.006',unit='flat')])
    result=compare(a,b,wuwa_model({'attack_flat':'1'}))
    assert result['a']['value']=='0.00' and result['b']['value']=='0.01'
    assert result['percent_delta']=='50.00' and result['reason'] is None
    assert result['exact_delta']=={'numerator':'1','denominator':'500'}


def test_item_subtotals_survive_unknown_set_with_partial_flag():
    raw=config().model_dump(mode='json');raw['items'].append(dict(id='unknown',stats_complete=None,stats=[]))
    result=assess(Configuration.model_validate(raw),wuwa_model())
    assert result['value'] is None and result['status']=='unscorable'
    assert result['partial'] is True and result['partial_known_total']=='20.00'
    assert result['item_results'][0]['value']=='20.00' and result['item_results'][1]['status']=='unscorable'
    unknown=config().model_dump(mode='json');unknown['items'][0]['stats_complete']=None
    empty=assess(Configuration.model_validate(unknown),wuwa_model())
    assert empty['partial'] is None and empty['partial_known_total'] is None


def nte_model():
    return AssessmentModel.model_validate(dict(game='nte',character_id='c1',version='personal-v1',source='user_configured',
        nte_profile=dict(character_id='c1',version='weights-v1',source='user_configured',substat_weights={'attack':'1','crit':'3'},mainstat_weights={}),
        nte_spec=dict(version='spec-v1',quality_factors={'custom':'0.8'},eligible_substats=['attack','crit'],
            catalog=[dict(canonical_id=x,label=x,kinds=['drive'],main=False,sub=True,unit='flat') for x in ('attack','crit')],mainstat_reference_values=[])))


@pytest.mark.parametrize('bad',[dict(value='-1'),dict(value='12.5%'),dict(area='four')])
def test_nte_item_with_an_invalid_number_keeps_the_other_subtotals(bad):
    # A value copied as '12.5%' or mistyped must make only that item unscorable, as for Wuwa.
    def item(item_id,observation='a',value='999',area='4'):
        return dict(id=item_id,nte=dict(kind='drive',quality='custom',area=area,substats_complete=True,
            substats=[dict(canonical_id='attack',observation_id=observation,value=value,unit='flat')]))
    c=Configuration.model_validate(dict(game='nte',character_id='c1',name='custom',source='user_configured',
        items=[item('good'),item('bad','b',**bad)]))
    result=assess(c,nte_model())
    assert (result['status'],result['value'],result['partial'],result['partial_known_total'])==('unscorable',None,True,'8.00')
    assert [(i['status'],i['reason']) for i in result['item_results']]==[('scored',None),('unscorable','INVALID_VALUE')]
    assert compare(c,c,nte_model())['reason']=='BOTH_CONFIGURATIONS_REQUIRE_SCORE'


def test_duplicated_item_ids_show_no_partial_total():
    # The whole set is rejected; adding up its items would count the duplicated one twice.
    raw=config().model_dump(mode='json');raw['items'].append(dict(raw['items'][0]))
    result=assess(Configuration.model_validate(raw),wuwa_model())
    assert (result['reason'],result['partial'],result['partial_known_total'])==('DUPLICATE_ITEM',None,None)


def echo_model(source='user_configured', **profile):
    return AssessmentModel.model_validate(dict(game='wuthering_waves',character_id='c1',version='v1',source=source,
        attribution='xwuid_snapshot' if source=='builtin_default' else None,
        wuwa_echo_profile={'main':{'1':{'attack_ratio':'1'},'3':{'attack_ratio':'2','fusion_damage':'2'},'4':{'crit_rate':'1','attack_flat':'0.1'}},
                           'sub':{'crit_rate':'1','skill_damage':'0.5'},**profile}))


def echo(item_id='e1',cost=4,main=(('crit_rate','22'),('attack_flat','150')),sub=(('crit_rate','10.5'),)):
    return dict(id=item_id,kind='echo',cost=cost,stats_complete=True,stats=[dict(canonical_id=k,value=v,unit='flat' if k.endswith('_flat') else 'percent_points',
        role=role,observation_id=f'{role}:{i}') for role,rows in (('main',main),('sub',sub)) for i,(k,v) in enumerate(rows)])


def echoes(*items):
    return Configuration.model_validate(dict(game='wuthering_waves',character_id='c1',name='A',source='user_configured',items=list(items)))


def test_echo_formula_selects_main_weights_by_cost_and_expands_nothing_at_runtime():
    # COST 4 maximum without a selection: best main 22×1 (crit) + fixed 150×0.1 + best five subs 10.5×1 + 11.6×0.5 = 53.3
    result=assess(echoes(echo()),echo_model())
    assert result['item_results'][0]['contributions'][0]['weight']=='1' and result['value']=='44.56'  # (22+15+10.5)÷53.3×50
    assert result['item_results'][0]['grade']=='sss' and result['grade']=='c'  # 44.56÷250 for the set
    # The same main stats on a COST 3 echo have no COST 3 weight; an element other than the profile's counts nothing.
    three=assess(echoes(echo(cost=3,main=(('crit_rate','22'),('glacio_damage','30'),('attack_flat','100')))),echo_model())
    assert three['value']=='6.88' and [c['value'] for c in three['contributions']][:3]==['0','0','0']  # 10.5÷(60+16.3)×50
    assert three['item_results'][0]['grade']=='c' and (three['origin'],three['unofficial'],three['attribution'])==('user_configured',None,None)


def test_echo_without_usable_cost_or_role_is_unscorable_and_partial_not_zero():
    good=echo('good'); missing=echo('missing',cost=None); unknown=echo('two',cost=2)
    result=assess(echoes(good,missing,unknown),echo_model())
    assert (result['status'],result['value'],result['grade'],result['max_value'])==('unscorable',None,None,250)
    assert result['partial'] is True and result['partial_known_total']=='44.56'
    assert [(i['reason'],i['cost'],i['max_value']) for i in result['item_results']]==[(None,4,50),('UNKNOWN_COST',None,50),('UNKNOWN_COST',2,50)]
    anonymous=echo(); anonymous['stats'][0]['role']=None
    assert assess(echoes(anonymous),echo_model())['reason']=='UNKNOWN_STAT_ROLE'
    incomplete=echo(); incomplete['stats_complete']=None
    assert assess(echoes(incomplete),echo_model())['reason']=='UNKNOWN_STAT_COMPLETENESS'


def test_echo_rounding_is_half_up_and_total_adds_displayed_items():
    model=echo_model(main={'1':{'attack_ratio':'1'},'3':{'attack_ratio':'1'},'4':{'crit_rate':'1'}},sub={'crit_rate':'0.1'},
                     max_main={'1':['attack_ratio'],'3':['attack_ratio'],'4':['crit_rate']},max_sub=[])
    # COST 1 maximum = 18×1 (only attack% selected): 0.0378÷18×50 = 0.105 → 0.11 (upstream's floor gives 0.10).
    one=assess(echoes(echo('a',1,(('attack_ratio','0.0378'),),())),model)
    assert one['value']=='0.11' and one['grade']=='c'
    pair=assess(echoes(echo('a',1,(('attack_ratio','0.0378'),),()),echo('b',1,(('attack_ratio','0.0378'),),())),model)
    assert pair['value']=='0.22'  # 0.11 + 0.11, not round(0.21)
    assert pair['grade']=='c' and pair['item_results'][1]['value']=='0.11'


def test_echo_profile_validation_and_builtin_marking():
    with pytest.raises(ValueError): echo_model(main={'1':{},'3':{}})
    with pytest.raises(ValueError): echo_model(main={'1':{'crit_rate':'1'},'3':{},'4':{}})  # no crit main stat on COST 1
    with pytest.raises(ValueError): echo_model(sub={'fusion_damage':'1'})  # element damage is never a sub stat
    with pytest.raises(ValueError): echo_model(sub={'crit_rate':'101'})
    with pytest.raises(ValueError): AssessmentModel.model_validate(dict(game='wuthering_waves',character_id='c1',version='v',source='builtin_default',wuwa_weights={'crit_rate':'1'}))
    with pytest.raises(ValueError): AssessmentModel.model_validate(dict(game='wuthering_waves',character_id='c1',version='v',source='user_configured',attribution='xwuid_snapshot'))
    with pytest.raises(ValueError): AssessmentModel.model_validate(dict(game='wuthering_waves',character_id='c1',version='v',source='builtin_default',attribution='xwuid_snapshot'))
    builtin=assess(echoes(echo()),echo_model('builtin_default'))
    assert (builtin['origin'],builtin['unofficial'],builtin['attribution'],builtin['item_results'][0]['grade'])==('builtin_default',True,'xwuid_snapshot','sss')
    legacy=assess(config(),wuwa_model())
    assert (legacy['origin'],legacy['unofficial'],legacy['attribution'],legacy['grade'],legacy['max_value'])==('user_configured',None,None,None,None)
    assert legacy['item_results'][0]['cost'] is None
