"""Build src/game_assistant/assessment-defaults-wuwa.json from a pinned upstream snapshot.

Development-machine tool; the application never runs it and never goes online.
Input: a directory holding the upstream files of WutheringWavesUID@1d693a2
(GPL-3.0, weights by tyql688) laid out as ``<dir>/<name>/calc.json`` (or the
flattened ``<dir>/<name>__calc.json``) plus ``<dir>/CharId2Data.json``.

    uv run python scripts/build_wuwa_default_weights.py --snapshot DIR          # write
    uv run python scripts/build_wuwa_default_weights.py --snapshot DIR --check  # compare

``--check`` regenerates every entry whose upstream file is present and fails on
any difference, so a partial snapshot (e.g. the test fixtures) checks a subset.
"""
import argparse
import copy
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'src' / 'game_assistant' / 'assessment-defaults-wuwa.json'
SHA = '1d693a2df0f940824cb34e102cec1cf3b381e70f'
DATA_VERSION = '2026-10-22'

ELEMENTS = {'冷凝': 'glacio_damage', '热熔': 'fusion_damage', '导电': 'electro_damage',
            '气动': 'aero_damage', '衍射': 'spectro_damage', '湮灭': 'havoc_damage'}
# Character element by game ID. Cross-checked against character-search-catalog.json
# where that catalog lists the character; the rest per the official character pages.
ELEMENT = {
    '1102': '冷凝', '1103': '冷凝', '1104': '冷凝', '1105': '冷凝', '1106': '冷凝', '1107': '冷凝',
    '1108': '冷凝', '1109': '冷凝', '1110': '冷凝',
    '1202': '热熔', '1203': '热熔', '1204': '热熔', '1205': '热熔', '1206': '热熔', '1207': '热熔',
    '1208': '热熔', '1209': '热熔', '1210': '热熔', '1211': '热熔',
    '1301': '导电', '1302': '导电', '1303': '导电', '1304': '衍射', '1305': '导电', '1306': '导电',
    '1307': '导电', '1308': '导电', '1311': '导电',
    '1402': '气动', '1403': '气动', '1404': '气动', '1405': '气动', '1406': '气动', '1407': '气动',
    '1408': '气动', '1409': '气动', '1410': '气动', '1411': '气动', '1413': '气动',
    '1501': '衍射', '1502': '衍射', '1503': '衍射', '1504': '导电', '1505': '衍射', '1506': '衍射',
    '1507': '衍射', '1508': '湮灭', '1509': '衍射', '1511': '衍射',
    '1601': '湮灭', '1602': '湮灭', '1603': '湮灭', '1604': '湮灭', '1605': '湮灭', '1606': '湮灭',
    '1607': '湮灭', '1608': '湮灭', '1610': '湮灭',
}
STATS = {'攻击': 'attack_flat', '攻击%': 'attack_ratio', '生命': 'health_flat', '生命%': 'health_ratio',
         '防御': 'defense_flat', '防御%': 'defense_ratio', '暴击': 'crit_rate', '暴击伤害': 'crit_damage',
         '共鸣效率': 'energy_regen', '治疗效果加成': 'healing_bonus'}
SKILLS = ['普攻伤害加成', '重击伤害加成', '共鸣技能伤害加成', '共鸣解放伤害加成']
SKILL_IDS = ['basic_damage', 'heavy_damage', 'skill_damage', 'liberation_damage']

# Self-made entries: the upstream ``default`` template with these overrides (upstream
# stat names; values follow comparable upstream characters). Not upstream data: the
# reasoning per character (official kit: damage types, scaling stat, energy need) is
# kept in the owner's review table outside the repository.
_DPS = {'技能伤害加成': 1.1}
_NO_ATTACK = {'main': {'4': {'攻击': 0, '攻击%': 0, '暴击': 0, '暴击伤害': 0}, '3': {'攻击': 0, '攻击%': 0, '属性伤害加成': 0},
                       '1': {'攻击%': 0}},
              'sub': {'攻击': 0, '攻击%': 0, '暴击': 0, '暴击伤害': 0}}


def _support(main, sub, skill_weight=(0, 0, 0, 0)):
    out = copy.deepcopy(_NO_ATTACK)
    for cost, table in main.items():
        out['main'][cost].update(table)
    out['sub'].update(sub)
    return dict(out, skill_weight=list(skill_weight))


SELF_MADE = {
    '1108': dict(name='绯雪', element='冷凝', sub={**_DPS, '共鸣效率': 0.3}, skill_weight=[0, 0, 0, 0.7]),
    '1109': dict(name='洛瑟菈', element='冷凝', sub={**_DPS, '共鸣效率': 0.1}, skill_weight=[0.6, 0, 0, 0]),
    '1110': dict(name='穗穗', element='冷凝', **_support(
        {'4': {'生命%': 0.3, '治疗效果加成': 0.375}, '3': {'生命%': 0.3, '共鸣效率': 0.3}, '1': {'生命': 0.003, '生命%': 0.4}},
        {'生命': 0.01, '生命%': 1.2, '共鸣效率': 1.2, '暴击伤害': 0.33})),
    '1209': dict(name='莫宁', element='热熔', **_support(
        {'4': {'防御%': 0.4, '治疗效果加成': 0.375}, '3': {'防御%': 0.255, '共鸣效率': 0.3003}, '1': {'防御%': 0.44}},
        {'防御': 0.15, '防御%': 1.2, '共鸣效率': 1.2, '技能伤害加成': 1.1}, (0, 0, 0, 0.35))),
    '1210': dict(name='爱弥斯', element='热熔', sub={**_DPS, '共鸣效率': 0.3}, skill_weight=[0.2, 0, 0, 0.6]),
    '1211': dict(name='达妮娅', element='热熔', sub={**_DPS, '共鸣效率': 0.5}, skill_weight=[0.3, 0, 0, 0.5]),
    '1308': dict(name='丽贝卡', element='导电', sub={**_DPS, '共鸣效率': 0.5}, skill_weight=[0.6, 0, 0, 0]),
    '1311': dict(name='心', element='导电', sub={**_DPS, '共鸣效率': 0.3}, skill_weight=[0.25, 0.15, 0.6, 0]),
    '1413': dict(name='清宵', element='气动', sub={**_DPS, '共鸣效率': 0.3}, skill_weight=[0.5, 0.2, 0, 0.2]),
    '1509': dict(name='琳奈', element='衍射', sub={**_DPS, '共鸣效率': 0.3}, skill_weight=[0.65, 0, 0, 0.1]),
    '1511': dict(name='露西', element='衍射', sub={**_DPS, '共鸣效率': 0.3}, skill_weight=[0.15, 0.65, 0, 0]),
    '1610': dict(name='秧秧·玄翎', element='湮灭', sub={**_DPS, '共鸣效率': 0.2}, skill_weight=[0.15, 0.65, 0, 0]),
}


def text(value):
    value = Decimal(value)
    return '0' if value == 0 else format(value.normalize(), 'f')


def expand(calc, element):
    """Upstream calc.json -> canonical weights, as utils/calculate.py applies them."""
    skill = [Decimal(str(w)) for w in calc.get('skill_weight') or [0, 0, 0, 0]]
    if len(skill) != 4:
        raise ValueError('skill_weight needs 4 values')

    def weights(table, allow_skills):
        out = {}
        for key, raw in table.items():
            weight = Decimal(str(raw))
            if key == '属性伤害加成':
                out[ELEMENTS[element]] = weight
            elif key == '技能伤害加成':
                for canonical, factor in zip(SKILL_IDS, skill):
                    out[canonical] = weight * factor
            elif key in SKILLS and allow_skills:
                # calculate.py reads 技能伤害加成 for these; a different own value would be ignored upstream.
                if weight != Decimal(str(table.get('技能伤害加成', 0))):
                    raise ValueError(f'{key} differs from 技能伤害加成')
            elif key in STATS:
                out[STATS[key]] = weight
            else:
                raise ValueError(f'unknown upstream stat {key}')
        return {k: text(v) for k, v in sorted(out.items()) if v != 0}

    main = {cost: weights(calc['main_props'][cost], False) for cost in ('1', '3', '4')}
    sub = weights(calc['sub_props'], True)
    best_skill = SKILL_IDS[skill.index(max(skill))]

    def selected(names):
        out = []
        for name in names:
            canonical = (ELEMENTS[element] if name == '属性伤害加成' else best_skill if name == '技能伤害加成'
                         else SKILL_IDS[SKILLS.index(name)] if name in SKILLS else STATS[name])
            # A zero-weight pick adds nothing to the maximum.
            if name == '技能伤害加成' and max(skill) == 0:
                continue
            out.append(canonical)
        return out

    max_main = {key.split('.')[0]: selected(names) for key, names in sorted(calc['max_main_props'].items())}
    if sorted(max_main) != ['1', '3', '4']:
        raise ValueError('max_main_props needs COST 1/3/4')
    return dict(main=main, sub=sub, max_main=max_main, max_sub=selected(calc['max_sub_props']))


def best_selection(entry):
    """Theoretical maximum picks for a self-made entry: the best possible echo."""
    from game_assistant.assessment import ECHO_MAIN_FIXED, ECHO_MAIN_MAX, ECHO_SUB_MAX
    main = {}
    for cost in ('1', '3', '4'):
        weights = entry['main'][cost]
        primary = max(ECHO_MAIN_MAX[cost], key=lambda s: Decimal(weights.get(s, '0')) * Decimal(ECHO_MAIN_MAX[cost][s]))
        main[cost] = [primary, ECHO_MAIN_FIXED[cost][0]]
    ranked = sorted(ECHO_SUB_MAX, key=lambda s: -Decimal(entry['sub'].get(s, '0')) * Decimal(ECHO_SUB_MAX[s]))
    return main, [s for s in ranked[:5] if Decimal(entry['sub'].get(s, '0')) > 0]


def calc_file(snapshot, name):
    for path in (snapshot / name / 'calc.json', snapshot / f'{name}__calc.json'):
        if path.is_file():
            return json.loads(path.read_text(encoding='utf-8'))
    return None


def build(snapshot):
    ids = json.loads((snapshot / 'CharId2Data.json').read_text(encoding='utf-8'))
    characters, missing = {}, []
    for character_id, row in sorted(ids.items()):
        calc = calc_file(snapshot, row['name'])
        if calc is None:
            missing.append(row['name'])
            continue
        characters[character_id] = dict(name=row['name'], origin='gpl_snapshot', upstream=row['name'],
                                        element=ELEMENT[character_id], **expand(calc, ELEMENT[character_id]))
    template = calc_file(snapshot, 'default')
    if template is not None:
        for character_id, spec in SELF_MADE.items():
            if character_id in ids:
                raise ValueError(f'{character_id} is covered upstream')
            calc = copy.deepcopy(template)
            for cost, table in spec.get('main', {}).items():
                calc['main_props'][cost].update(table)
            calc['sub_props'].update(spec.get('sub', {}))
            calc['skill_weight'] = spec.get('skill_weight', calc['skill_weight'])
            entry = expand(calc, spec['element'])
            entry['max_main'], entry['max_sub'] = best_selection(entry)
            if spec['element'] != ELEMENT[character_id]:
                raise ValueError(f'{character_id} element mismatch')
            characters[character_id] = dict(name=spec['name'], origin='self_made', upstream='default',
                                            element=spec['element'], **entry)
    else:
        missing.append('default')
    catalog = json.loads((ROOT / 'src' / 'game_assistant' / 'character-search-catalog.json').read_text(encoding='utf-8'))
    for row in catalog['characters']:
        if row['game'] == 'wuthering_waves' and row['character_id'] in characters and row['form'] in ELEMENTS:
            if row['form'] != characters[row['character_id']]['element']:
                raise ValueError(f"{row['character_id']} element differs from the search catalog")
    return dict(sorted(characters.items())), missing


def document(characters):
    return dict(
        schema_version=1,
        formula='wuwa-echo-default-v1',
        data_version=DATA_VERSION,
        provenance=dict(
            repository='https://github.com/Celec7/WutheringWavesUID',
            original_repository='kvcfdd/WutheringWavesUID (deleted; Celec7 is an archived mirror at the same commit)',
            commit=SHA,
            path='WutheringWavesUID/utils/map/character/<name>/calc.json',
            author='tyql688',
            license='GPL-3.0',
            modified=DATA_VERSION,
            changes=('Modified by game-manage: keyed by game character ID; upstream stat names mapped to canonical IDs; '
                     'skill damage expanded by skill_weight and element damage to the character element; zero weights, '
                     'grades, colours and score_max dropped (score_max is recomputed); conditional variants ignored; '
                     'entries with origin self_made are not upstream data but derived from the default template.'),
        ),
        grade_thresholds=['0', '0.48', '0.6', '0.7', '0.78', '0.84'],
        grades=['c', 'b', 'a', 's', 'ss', 'sss'],
        characters=characters,
    )


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=1) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    characters, missing = build(args.snapshot)
    if not args.check:
        if missing:
            print('missing upstream files: ' + ', '.join(missing), file=sys.stderr)
            return 1
        args.output.write_text(dump(document(characters)), encoding='utf-8', newline='\n')
        print(f'wrote {len(characters)} entries')
        return 0
    stored = json.loads(args.output.read_text(encoding='utf-8'))
    expected = document({})
    problems = [key for key in expected if key != 'characters' and stored.get(key) != expected[key]]
    problems += [cid for cid, entry in characters.items() if stored['characters'].get(cid) != entry]
    if not missing:
        problems += [cid for cid in stored['characters'] if cid not in characters]
    if problems:
        print('differs: ' + ', '.join(problems), file=sys.stderr)
        return 1
    print(f'checked {len(characters)} entries' + (f'; not in snapshot: {len(missing)}' if missing else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
