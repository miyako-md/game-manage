"""Built-in NTE defaults and the equipped-piece conversion. Values are synthetic in the role API's shape;
weights in the sample fixture are 异环工坊's (credited as its endpoint asks)."""
import json
import sys
from pathlib import Path
import pytest
from game_assistant.assessment import AssessmentModel, assess
from game_assistant.assessment_defaults import NTE_PATH, default_model, nte_defaults, resolve_model
from game_assistant.assessment_equipped import equipped_configuration
from game_assistant.assessment_store import AssessmentStore
from game_assistant.accounts.models import AccountScope

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = Path(__file__).parent / 'fixtures' / 'nte-workshop-weights-sample.json'
sys.path.insert(0, str(ROOT / 'scripts'))
import build_nte_default_weights as builder  # noqa: E402


def stat(key, name, value):
    return {'id': key, 'name': name, 'value': value}


SUBS = [stat('critbase', '暴击率', '5.4%'), stat('critdamagebase', '暴击伤害', '10.8%'),
        stat('atkup', '攻击力百分比', '4.5%'), stat('defadd', '防御力', '20')]


def core(main=('critdamagebase', '暴击伤害', '60%'), source='nature_orange', subs=SUBS):
    return {'id': source, 'name': '空幕', 'level': 20, 'main_properties': [stat(*main)], 'properties': subs}


def pie(source, name, subs=SUBS):
    return {'id': source, 'name': name, 'level': 20, 'main_properties': [stat('atkadd', '攻击力', '63'), stat('hpmaxadd', '生命值', '840')], 'properties': subs}


def role(*, cores=None, pies=None):
    return {'entries': [{'id': '1003', 'suit': {'core': [core()] if cores is None else cores,
                                                'pie': [pie('cell3_style1_2_orange', 'Ⅲ型驱动'), pie('cell2_style1_1_purple', 'Ⅱ型驱动')] if pies is None else pies}}]}


def score(payload):
    return assess(equipped_configuration('nte', '1003', payload), default_model('nte', '1003'))


def test_bundled_file_validates_credits_the_workshop_and_keeps_weights_inside_the_spec():
    data = nte_defaults()
    assert data.provenance.notice == '权重配置来自：异环工坊' and data.provenance.license == 'unstated'
    assert len(data.characters) == 25 and set(data.spec.quality_factors) == {'orange', 'purple', 'blue'}
    assert len(data.spec.eligible_substats) == 11
    raw = json.loads(NTE_PATH.read_text(encoding='utf-8'))
    # Zero weights are not stored, and the workshop's spelling of the psyche key is mapped.
    assert all(w != '0' for entry in raw['characters'].values() for table in ('substat_weights', 'mainstat_weights') for w in entry[table].values())
    assert not any('damageupsychebase' in entry['mainstat_weights'] for entry in raw['characters'].values())


def test_build_check_passes_on_the_sample_and_catches_changes(tmp_path, capsys):
    assert builder.main(['--snapshot', str(SAMPLE), '--check']) == 0
    assert 'partial snapshot' in capsys.readouterr().out
    changed = json.loads(NTE_PATH.read_text(encoding='utf-8'))
    changed['characters']['1003']['substat_weights']['critbase'] = '0.5'
    output = tmp_path / 'defaults.json'
    output.write_text(json.dumps(changed, ensure_ascii=False), encoding='utf-8')
    assert builder.main(['--snapshot', str(SAMPLE), '--check', '--output', str(output)]) == 1
    assert '1003' in capsys.readouterr().err
    changed = json.loads(NTE_PATH.read_text(encoding='utf-8'))
    changed['spec']['quality_factors']['blue'] = '0.5'
    output.write_text(json.dumps(changed, ensure_ascii=False), encoding='utf-8')
    assert builder.main(['--snapshot', str(SAMPLE), '--check', '--output', str(output)]) == 1


def test_build_refuses_a_changed_attribution_notice(tmp_path):
    payload = json.loads(SAMPLE.read_text(encoding='utf-8'))
    payload['notice'] = '禁止转载'
    changed = tmp_path / 'snapshot.json'
    changed.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(SystemExit):
        builder.main(['--snapshot', str(changed), '--check'])


def test_kind_quality_area_and_substats_come_from_the_pieces_own_fields():
    items = equipped_configuration('nte', '1003', role()).items
    cartridge, gold, purple = items
    assert (cartridge.kind, cartridge.nte.quality, cartridge.nte.area) == ('cartridge', 'orange', None)
    assert cartridge.nte.mainstat.canonical_id == 'critdamagebase' and cartridge.nte.mainstat.unit == 'percent_points'
    assert cartridge.nte.mainstat.context == {'kind': 'cartridge'}
    assert (gold.kind, gold.nte.quality, gold.nte.area, gold.nte.mainstat) == ('drive', 'orange', '3', None)
    assert (purple.nte.quality, purple.nte.area) == ('purple', '2')
    assert all(i.nte.substats_complete is True for i in items)
    assert [s.unit for s in gold.nte.substats] == ['percent_points'] * 3 + ['flat']
    assert [i.id for i in items] == ['core:0:nature_orange', 'pie:0:cell3_style1_2_orange', 'pie:1:cell2_style1_1_purple']


def test_exact_scores_maxima_and_grades():
    # 早雾: D = 1+1+1+0.8 = 3.8 and the pieces' substat weights sum to 1+1+0.7+0 = 2.7.
    result = score(role())
    items = {i['item_id'].split(':')[0] + i['item_id'].split(':')[1]: i for i in result['item_results']}
    assert (items['core0']['value'], items['core0']['max_value'], items['core0']['grade']) == ('116.05', '150', 'SSS')  # 50×0.9 + 100×2.7/3.8
    assert (items['pie0']['value'], items['pie0']['max_value'], items['pie0']['grade']) == ('21.32', '30', 'SSS')  # 10×3×2.7/3.8
    assert (items['pie1']['value'], items['pie1']['max_value'], items['pie1']['grade']) == ('11.37', '20', 'S')  # 10×2×0.8×2.7/3.8
    assert (result['status'], result['value'], result['max_value'], result['grade']) == ('scored', '148.74', '200', 'SSS')
    assert (result['origin'], result['unofficial'], result['attribution']) == ('builtin_default', True, 'nte_workshop')


def test_unproven_inputs_stay_unknown_and_count_as_a_partial_result():
    pies = [pie('cell3_style1_2_orange', 'Ⅱ型驱动'), pie('cell2_style1_1_orange', 'Ⅱ型驱动', SUBS[:3])]
    result = score(role(cores=[core(main=('chargegetefficiency', '充能效率', '20%'))], pies=pies))
    reasons = [i['reason'] for i in result['item_results']]
    # Charge efficiency is no cartridge main stat (no reference); the name disagrees with the ID's area; three substats are not a complete list.
    assert reasons == ['UNKNOWN_MAIN_REFERENCE', 'UNKNOWN_AREA', 'UNKNOWN_SUBSTATS']
    assert result['status'] == 'unscorable' and result['max_value'] is None and result['partial'] is None


def test_a_main_stat_without_a_name_is_mapped_by_its_id():
    result = score(role(cores=[core(main=('damageupincantationbase', None, '30%'), source='incantation_purple')], pies=[]))
    item = result['item_results'][0]
    # Purple, below the gold reference: 50×1×0.3/0.375 + 100×0.8×2.7/3.8.
    assert item['status'] == 'scored' and item['value'] == '96.84'


def test_unknown_colour_or_character_leaves_no_score():
    assert score(role(cores=[core(source='nature')], pies=[]))['reason'] == 'UNKNOWN_QUALITY'
    assert default_model('nte', '9999') is None


def test_resolution_prefers_the_saved_model_and_a_saved_copy_is_the_users_own(tmp_path):
    store = AssessmentStore(tmp_path / 'a.db')
    scope = AccountScope('u', 'a', 'r')
    model, origin = resolve_model(store, scope, 'nte', '1003')
    assert origin == 'builtin_default' and model.nte_profile.source == 'builtin_default'
    with pytest.raises(ValueError):
        AssessmentModel.model_validate({**model.model_dump(mode='python'), 'attribution': 'xwuid_snapshot'})
    with pytest.raises(ValueError):
        AssessmentModel.model_validate({**model.model_dump(mode='python'), 'source': 'user_configured', 'attribution': None})
    own = model.model_dump(mode='python')
    own.update(source='user_configured', attribution=None, nte_profile={**own['nte_profile'], 'source': 'user_configured'})
    store.save(scope, AssessmentModel.model_validate(own), 'model')
    assert resolve_model(store, scope, 'nte', '1003')[1] == 'user_configured'
    store.close()


def test_every_cartridge_main_stat_has_its_s_rank_level_limit_reference():
    refs = {r.canonical_id: str(r.value) for r in nte_defaults().spec.mainstat_reference_values}
    assert refs['defup'] == '0.525' and refs['healup'] == '0.345' and refs['unbalintensitybase'] == '180'
    assert {k for k in refs if k.startswith('damageup')} == {e.canonical_id for e in nte_defaults().spec.catalog if e.canonical_id.startswith('damageup') and e.main}
    # A gold level-20 HP% cartridge reaches the full main term.
    item = score(role(cores=[core(main=('hpmaxup', '生命值百分比', '37.5%'))], pies=[]))['item_results'][0]
    assert item['status'] == 'scored'
