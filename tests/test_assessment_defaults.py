"""Built-in WuWa defaults. Upstream fixtures: XutheringWavesUID-Resources@93c75d6 (weights by Loping151)."""
import json
import shutil
import sys
from fractions import Fraction
from pathlib import Path
import pytest
from game_assistant.assessment import Configuration, assess, echo_max
from game_assistant.assessment_defaults import PATH, default_model, defaults, resolve_model
from game_assistant.assessment_store import AssessmentStore
from game_assistant.accounts.models import AccountScope

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = Path(__file__).parent / 'fixtures' / 'wuwa-xwuid-calc'
sys.path.insert(0, str(ROOT / 'scripts'))
import build_wuwa_default_weights as builder  # noqa: E402

IDS = ['1102', '1103', '1104', '1105', '1106', '1107', '1108', '1109', '1110', '1202', '1203', '1204', '1205', '1206',
       '1207', '1208', '1209', '1210', '1211', '1212', '1301', '1302', '1303', '1304', '1305', '1306', '1307', '1308',
       '1309', '1310', '1311', '1312', '1402', '1403', '1404', '1405', '1406', '1407', '1408', '1409', '1410', '1411',
       '1412', '1413', '1501', '1502', '1503', '1504', '1505', '1506', '1507', '1508', '1509', '1510', '1511', '1601',
       '1602', '1603', '1604', '1605', '1606', '1607', '1608', '1610']


def test_bundled_file_validates_and_marks_every_origin():
    data = defaults()
    assert sorted(data.characters) == IDS and {e.origin for e in data.characters.values()} == {'xwuid_snapshot'}
    assert all(entry.upstream == cid for cid, entry in data.characters.items())
    provenance = data.provenance
    assert (provenance.source, provenance.commit, provenance.plugin_commit) == ('XutheringWavesUID', builder.SHA, builder.PLUGIN_SHA)
    assert (provenance.author, provenance.license, provenance.payload_sha256) == ('Loping151', 'unstated', builder.PAYLOAD_SHA256)
    assert 'Modified' in provenance.changes and 'tyql688' in provenance.changes
    raw = json.loads(PATH.read_text(encoding='utf-8'))
    assert 'default' not in raw['characters'] and all('score_max' not in e for e in raw['characters'].values())
    # Element damage only for the character's own element; skill damage expanded by skill_weight.
    for entry in data.characters.values():
        own = builder.ELEMENTS[entry.element]
        assert {s for s in entry.main['3'] if s.endswith('_damage')} <= {own}
    changli = data.characters['1205'].sub
    assert (changli['skill_damage'], changli['liberation_damage']) == (Fraction('0.66'), Fraction('0.44'))
    assert 'basic_damage' not in changli


@pytest.mark.parametrize('character_id', ['1205', '1410', '1413', '1505'])
def test_snapshot_entries_equal_the_upstream_calc_after_mapping(character_id):
    calc = json.loads((UPSTREAM / 'character' / character_id / 'calc.json').read_text(encoding='utf-8'))
    name = json.loads((UPSTREAM / 'CharId2Data.json').read_text(encoding='utf-8'))[character_id]['name']
    stored = json.loads(PATH.read_text(encoding='utf-8'))['characters'][character_id]
    assert stored == dict(name=name, origin='xwuid_snapshot', upstream=character_id, element=builder.ELEMENT[character_id],
                          **builder.expand(calc, builder.ELEMENT[character_id]))
    # Inverse: every nonzero upstream weight is present with the same value.
    entry = defaults().characters[character_id]
    for cost in ('1', '3', '4'):
        for key, weight in calc['main_props'][cost].items():
            canonical = builder.ELEMENTS[entry.element] if key == '属性伤害加成' else builder.STATS[key]
            assert Fraction(entry.main[cost].get(canonical, 0)) == Fraction(str(weight))
    for key, weight in calc['sub_props'].items():
        if key in builder.STATS:
            assert Fraction(entry.sub.get(builder.STATS[key], 0)) == Fraction(str(weight))
    skill = Fraction(str(calc['sub_props']['技能伤害加成']))
    for canonical, factor in zip(builder.SKILL_IDS, calc['skill_weight']):
        assert Fraction(entry.sub.get(canonical, 0)) == skill * Fraction(str(factor))


def test_recomputed_maximum_matches_every_upstream_score_max():
    table = json.loads((UPSTREAM / 'score_max.json').read_text(encoding='utf-8'))['score_max']
    assert sorted(table) == IDS
    for character_id, maxima in table.items():
        model = default_model('wuthering_waves', character_id)
        for cost, upstream in zip(('1', '3', '4'), maxima):
            # Upstream stores float results truncated to 3 places in three steps.
            assert 0 <= echo_max(model.wuwa_echo_profile, cost) - Fraction(str(upstream)) < Fraction(3, 1000)


def test_revised_upstream_weights_replace_the_old_ones():
    # 尤诺: the COST 4 crit rate main stat was lowered from the old 0.5; 爱弥斯 is liberation only.
    assert defaults().characters['1410'].main['4']['crit_rate'] == Fraction('0.33')
    emis = defaults().characters['1210'].sub
    assert 'basic_damage' not in emis and emis['liberation_damage'] == Fraction('0.77')


def test_build_check_passes_on_the_fixture_subset_and_catches_changes(tmp_path, capsys):
    assert builder.main(['--snapshot', str(UPSTREAM), '--check']) == 0
    assert 'partial snapshot' in capsys.readouterr().out
    # Writing needs the complete pinned snapshot.
    assert builder.main(['--snapshot', str(UPSTREAM), '--output', str(tmp_path / 'out.json')]) == 1
    assert not (tmp_path / 'out.json').exists()
    changed = json.loads(PATH.read_text(encoding='utf-8'))
    changed['characters']['1205']['sub']['crit_rate'] = '3'
    output = tmp_path / 'defaults.json'
    output.write_text(json.dumps(changed, ensure_ascii=False), encoding='utf-8')
    assert builder.main(['--snapshot', str(UPSTREAM), '--check', '--output', str(output)]) == 1
    assert '1205' in capsys.readouterr().err
    calc = tmp_path / 'snapshot'
    shutil.copytree(UPSTREAM, calc)
    shutil.rmtree(calc / 'character' / '1205')
    assert builder.main(['--snapshot', str(calc), '--check', '--output', str(output)]) == 0


def echo(index, cost, main, sub):
    stats = [dict(canonical_id=k, value=v, unit='flat' if k.endswith('_flat') else 'percent_points', role=role,
                  observation_id=f'{role}:{i}') for role, rows in (('main', main), ('sub', sub)) for i, (k, v) in enumerate(rows)]
    return dict(id=f'echo:{index}', kind='echo', cost=cost, stats_complete=True, stats=stats)


CHANGLI = [
    echo(0, 4, [('crit_rate', '22'), ('attack_flat', '150')],
         [('crit_rate', '8.1'), ('crit_damage', '16.2'), ('attack_ratio', '10.1'), ('skill_damage', '9.4'), ('attack_flat', '40')]),
    echo(1, 3, [('fusion_damage', '30'), ('attack_flat', '100')],
         [('crit_rate', '9.3'), ('crit_damage', '17.4'), ('attack_ratio', '8.6'), ('energy_regen', '10.8'), ('liberation_damage', '8.6')]),
    echo(2, 3, [('attack_ratio', '30'), ('attack_flat', '100')],
         [('crit_rate', '6.9'), ('crit_damage', '13.8'), ('health_flat', '470'), ('defense_ratio', '10.9'), ('attack_flat', '50')]),
    echo(3, 1, [('attack_ratio', '18'), ('health_flat', '2280')],
         [('crit_rate', '10.5'), ('crit_damage', '21'), ('attack_ratio', '11.6'), ('skill_damage', '11.6'), ('attack_flat', '60')]),
    echo(4, 1, [('health_ratio', '22.8'), ('health_flat', '2280')],
         [('crit_damage', '12.6'), ('energy_regen', '6.8'), ('basic_damage', '6.4'), ('heavy_damage', '7.1'), ('defense_flat', '50')]),
]


def golden():
    return Configuration.model_validate(dict(game='wuthering_waves', character_id='1205', name='golden',
                                             source='user_configured', items=CHANGLI))


def test_changli_five_echo_golden():
    # By hand with the upstream formula: Σ(value×weight) ÷ score_max[cost] × 50.
    # Echo 0: 22×.5+150×.025 + 8.1×2+16.2×1+10.1×1.1+9.4×1.1×.6+40×.1 = 68.464; ÷83.166×50 = 41.161 → 41.16 (ss)
    # Echo 1: 30×.275+100×.025 + 18.6+17.4+9.46+10.8×.3+8.6×1.1×.4 = 63.234; ÷79.166×50 = 39.9375 → 39.94 (ss; upstream floor 39.93)
    # Echo 2: 30×.275+2.5 + 13.8+13.8+0+0+5 = 43.35; ÷79.166×50 = 27.379 → 27.38 (b)
    # Echo 3: 18×.4 + 21+21+12.76+7.656+6 = 75.616 = the COST 1 maximum → 50.00 (sss)
    # Echo 4: 0 + 12.6+6.8×.3 = 14.64; ÷75.616×50 = 9.680 → 9.68 (c)
    result = assess(golden(), default_model('wuthering_waves', '1205'))
    assert [(i['value'], i['grade'], i['cost'], i['max_value']) for i in result['item_results']] == [
        ('41.16', 'ss', 4, 50), ('39.94', 'ss', 3, 50), ('27.38', 'b', 3, 50), ('50.00', 'sss', 1, 50), ('9.68', 'c', 1, 50)]
    # 168.16 ÷ 250 = 0.6726 → a (upstream, flooring each item, would show 168.14).
    assert (result['status'], result['value'], result['grade'], result['max_value']) == ('scored', '168.16', 'a', 250)
    assert (result['origin'], result['unofficial'], result['attribution']) == ('builtin_default', True, 'xwuid_snapshot')
    assert result['formula'] == 'wuwa-echo-default-v1' and result['partial'] is False


def test_resolution_prefers_the_saved_model_and_never_falls_back_to_the_template(tmp_path):
    from tests.test_personal_assessment import wuwa_model
    store = AssessmentStore(tmp_path / 'score.db'); scope = AccountScope('u', 'a', 'r')
    model, origin = resolve_model(store, scope, 'wuthering_waves', '1205')
    assert (origin, model.source, model.attribution) == ('builtin_default', 'builtin_default', 'xwuid_snapshot')
    assert resolve_model(store, scope, 'wuthering_waves', '1311')[0].attribution == 'xwuid_snapshot'
    for missing in ('1512', '9999', 'c1'):
        model, origin = resolve_model(store, scope, 'wuthering_waves', missing)
        assert origin is None and model.version == 'unconfigured' and default_model('wuthering_waves', missing) is None
        result = assess(Configuration.model_validate(dict(game='wuthering_waves', character_id=missing, name='x',
            source='user_configured', items=[CHANGLI[0]])), model)
        assert (result['status'], result['reason'], result['grade'], result['origin']) == ('unconfigured', 'NO_WEIGHTS', None, 'user_configured')
    assert resolve_model(store, scope, 'nte', '1205') == (resolve_model(None, scope, 'nte', '1205')[0], None)
    store.save(scope, wuwa_model(), 'model')
    assert resolve_model(store, scope, 'wuthering_waves', 'c1') == (wuwa_model(), 'user_configured')
    store.close()
