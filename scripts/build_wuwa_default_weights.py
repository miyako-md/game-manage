"""Build src/game_assistant/assessment-defaults-wuwa.json from a pinned upstream snapshot.

Development-machine tool; the application never runs it and never goes online.
Input: a directory holding the files of XutheringWavesUID-Resources@93c75d6
(``XutheringWavesUID/resource/map``; weights by Loping151, no licence stated) laid
out as ``<dir>/character/<ID>/calc.json`` plus ``<dir>/CharId2Data.json``.

    uv run python scripts/build_wuwa_default_weights.py --snapshot DIR          # write
    uv run python scripts/build_wuwa_default_weights.py --snapshot DIR --check  # compare

Writing needs the complete pinned snapshot (PAYLOAD_SHA256). ``--check`` regenerates
every entry whose upstream file is present and fails on any difference, so a partial
snapshot (e.g. the test fixtures) checks a subset.
"""
import argparse
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'src' / 'game_assistant' / 'assessment-defaults-wuwa.json'
SHA = '93c75d6539cd6c1b3dbe151c02237cabb6af6a95'
PLUGIN_SHA = 'b29863c0284028bc289464e9353ceebfe1311ce1'
FETCHED_AT = '2026-10-31T09:44:01Z'
# sha256 over CharId2Data.json and every character/<ID>/calc.json it lists (see payload_sha256).
PAYLOAD_SHA256 = '66a86f3355bd098a782a53a2eac94cbcca86eddeeae5745b8fe2d0af3f6d1067'
DATA_VERSION = '2026-10-31'

ELEMENTS = {'冷凝': 'glacio_damage', '热熔': 'fusion_damage', '导电': 'electro_damage',
            '气动': 'aero_damage', '衍射': 'spectro_damage', '湮灭': 'havoc_damage'}
# Character element by game ID. Cross-checked against character-search-catalog.json
# where that catalog lists the character; the rest per the official character pages.
# 1212/1309/1310/1312/1412/1510: game data (api.encore.moe ElementName) and the upstream
# grade lists (own element damage) agree.
ELEMENT = {
    '1102': '冷凝', '1103': '冷凝', '1104': '冷凝', '1105': '冷凝', '1106': '冷凝', '1107': '冷凝',
    '1108': '冷凝', '1109': '冷凝', '1110': '冷凝',
    '1202': '热熔', '1203': '热熔', '1204': '热熔', '1205': '热熔', '1206': '热熔', '1207': '热熔',
    '1208': '热熔', '1209': '热熔', '1210': '热熔', '1211': '热熔', '1212': '热熔',
    '1301': '导电', '1302': '导电', '1303': '导电', '1304': '衍射', '1305': '导电', '1306': '导电',
    '1307': '导电', '1308': '导电', '1309': '导电', '1310': '导电', '1311': '导电', '1312': '导电',
    '1402': '气动', '1403': '气动', '1404': '气动', '1405': '气动', '1406': '气动', '1407': '气动',
    '1408': '气动', '1409': '气动', '1410': '气动', '1411': '气动', '1412': '气动', '1413': '气动',
    '1501': '衍射', '1502': '衍射', '1503': '衍射', '1504': '导电', '1505': '衍射', '1506': '衍射',
    '1507': '衍射', '1508': '湮灭', '1509': '衍射', '1510': '衍射', '1511': '衍射',
    '1601': '湮灭', '1602': '湮灭', '1603': '湮灭', '1604': '湮灭', '1605': '湮灭', '1606': '湮灭',
    '1607': '湮灭', '1608': '湮灭', '1610': '湮灭',
}
STATS = {'攻击': 'attack_flat', '攻击%': 'attack_ratio', '生命': 'health_flat', '生命%': 'health_ratio',
         '防御': 'defense_flat', '防御%': 'defense_ratio', '暴击': 'crit_rate', '暴击伤害': 'crit_damage',
         '共鸣效率': 'energy_regen', '治疗效果加成': 'healing_bonus'}
SKILLS = ['普攻伤害加成', '重击伤害加成', '共鸣技能伤害加成', '共鸣解放伤害加成']
SKILL_IDS = ['basic_damage', 'heavy_damage', 'skill_damage', 'liberation_damage']


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


def calc_path(snapshot, character_id):
    return snapshot / 'character' / character_id / 'calc.json'


def payload_sha256(snapshot, ids):
    """Hash of the files the build reads; equal to PAYLOAD_SHA256 only for the complete pinned snapshot."""
    digest = hashlib.sha256()
    paths = [snapshot / 'CharId2Data.json'] + [calc_path(snapshot, cid) for cid in sorted(ids)]
    for path in paths:
        if path.is_file():
            digest.update(path.relative_to(snapshot).as_posix().encode('utf-8') + b'\n' + path.read_bytes() + b'\n')
    return digest.hexdigest()


def build(snapshot):
    """Returns (entries, complete); characters the upstream map lists without a calc.json get no entry."""
    ids = json.loads((snapshot / 'CharId2Data.json').read_text(encoding='utf-8'))
    characters = {}
    for character_id, row in sorted(ids.items()):
        path = calc_path(snapshot, character_id)
        if not path.is_file():
            continue
        calc = json.loads(path.read_text(encoding='utf-8'))
        characters[character_id] = dict(name=row['name'], origin='xwuid_snapshot', upstream=character_id,
                                        element=ELEMENT[character_id], **expand(calc, ELEMENT[character_id]))
    catalog = json.loads((ROOT / 'src' / 'game_assistant' / 'character-search-catalog.json').read_text(encoding='utf-8'))
    for row in catalog['characters']:
        if row['game'] == 'wuthering_waves' and row['character_id'] in characters and row['form'] in ELEMENTS:
            if row['form'] != characters[row['character_id']]['element']:
                raise ValueError(f"{row['character_id']} element differs from the search catalog")
    return dict(sorted(characters.items())), payload_sha256(snapshot, ids) == PAYLOAD_SHA256


def document(characters):
    return dict(
        schema_version=1,
        formula='wuwa-echo-default-v1',
        data_version=DATA_VERSION,
        provenance=dict(
            source='XutheringWavesUID',
            repository='https://cnb.cool/loping151/XutheringWavesUID-Resources',
            commit=SHA,
            path='XutheringWavesUID/resource/map/character/<ID>/calc.json',
            plugin_repository='https://github.com/Loping151/XutheringWavesUID',
            plugin_commit=PLUGIN_SHA,
            author='Loping151',
            license='unstated',
            fetched_at=FETCHED_AT,
            payload_sha256=PAYLOAD_SHA256,
            modified=DATA_VERSION,
            changes=('Modified by game-manage: upstream stat names mapped to canonical IDs; skill damage expanded by '
                     'skill_weight and element damage to the character element; zero weights, grades, colours, '
                     'revision notes and score_max dropped (score_max is recomputed); conditional variants '
                     '(洛瑟菈 condition.json) ignored. 45 entries are value-identical to the GPL-3.0 weights by '
                     'tyql688 in WutheringWavesUID@1d693a2.'),
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
    characters, complete = build(args.snapshot)
    if not args.check:
        if not complete:
            print('snapshot differs from the pinned payload (PAYLOAD_SHA256)', file=sys.stderr)
            return 1
        args.output.write_text(dump(document(characters)), encoding='utf-8', newline='\n')
        print(f'wrote {len(characters)} entries')
        return 0
    stored = json.loads(args.output.read_text(encoding='utf-8'))
    expected = document({})
    problems = [key for key in expected if key != 'characters' and stored.get(key) != expected[key]]
    problems += [cid for cid, entry in characters.items() if stored['characters'].get(cid) != entry]
    if complete:
        problems += [cid for cid in stored['characters'] if cid not in characters]
    if problems:
        print('differs: ' + ', '.join(problems), file=sys.stderr)
        return 1
    print(f'checked {len(characters)} entries' + ('' if complete else ' (partial snapshot)'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
