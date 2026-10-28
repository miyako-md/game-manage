"""Build src/game_assistant/assessment-defaults-nte.json from a saved 异环工坊 weight snapshot.

Development-machine tool; the application never runs it and never goes online.
Input: the JSON body of GET https://yh.zzzmap.com/api/open/game-character/weight-configs
saved to a file. The endpoint asks users to credit it ("请在页面注明 - 权重配置来自：异环工坊");
it states no licence.

    uv run python scripts/build_nte_default_weights.py --snapshot FILE --fetched-at 2026-10-28T00:44:35Z  # write
    uv run python scripts/build_nte_default_weights.py --snapshot FILE --check                            # compare

The scoring spec below (stat catalog, quality factors, cartridge main references) is
not workshop data: it was measured on equipped items from the NTE role API (see
docs/personal-assessment.md). ``--check`` regenerates every character in the snapshot
and the spec and fails on any difference, so a partial snapshot (e.g. the test
fixture) checks a subset.
"""
import argparse
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'src' / 'game_assistant' / 'assessment-defaults-nte.json'
DATA_VERSION = '2026-10-28.1'
ENDPOINT = 'https://yh.zzzmap.com/api/open/game-character/weight-configs'
NOTICE = '权重配置来自：异环工坊'

# Canonical IDs are the role API's lower-case stat IDs. unit: values shown with '%' are ratios.
SUBSTATS = {'atkadd': ('攻击力', 'flat'), 'atkup': ('攻击力百分比', 'ratio'), 'critbase': ('暴击率', 'ratio'),
            'critdamagebase': ('暴击伤害', 'ratio'), 'damageupgeneralbase': ('通用伤害增强', 'ratio'),
            'defadd': ('防御力', 'flat'), 'defup': ('防御力百分比', 'ratio'), 'hpmaxadd': ('生命值', 'flat'),
            'hpmaxup': ('生命值百分比', 'ratio'), 'magbase': ('环合强度', 'flat'), 'unbalintensitybase': ('倾陷强度', 'flat')}
# Cartridge (core) main stats; drive (pie) main stats are the fixed flat ATK/HP pair and are not scored.
CARTRIDGE_MAINS = {'critbase', 'critdamagebase', 'atkup', 'hpmaxup', 'defup', 'magbase', 'unbalintensitybase'}
MAIN_ONLY = {'chargegetefficiency': ('充能效率', 'ratio'), 'healup': ('治疗加成', 'ratio'),
             'damageupchaosbase': ('暗属性异能伤害增强', 'ratio'), 'damageupcosmosbase': ('光属性异能伤害增强', 'ratio'),
             'damageupincantationbase': ('咒属性异能伤害增强', 'ratio'), 'damageuplakshanabase': ('相属性异能伤害增强', 'ratio'),
             'damageupnaturebase': ('灵属性异能伤害增强', 'ratio'), 'damageuppsychebase': ('魂属性异能伤害增强', 'ratio'),
             'damageuppsychicallybase': ('心灵伤害增强', 'ratio')}
# Item ID colour suffix -> quality factor; the pie main values scale by the same 1 / 0.8 / 0.6.
QUALITY_FACTORS = {'orange': '1', 'purple': '0.8', 'blue': '0.6'}
# S-rank cartridge main values at level 20 (GameWith "Effect Value (Max Enhancement)", checked
# 2026-10-28). Six of them were also measured on real equipped items (crit, crit damage, 暗/咒/灵
# damage, magbase from purple 144 / 0.8) and agree. Charge efficiency is not a cartridge main stat;
# a main stat without a value here stays unscorable (UNKNOWN_MAIN_REFERENCE).
REFERENCES = {'atkup': '0.375', 'hpmaxup': '0.375', 'defup': '0.525', 'critbase': '0.3', 'critdamagebase': '0.6',
              'magbase': '180', 'unbalintensitybase': '180', 'healup': '0.345',
              **{key: '0.375' for key in ('damageupchaosbase', 'damageupcosmosbase', 'damageupincantationbase', 'damageuplakshanabase',
                                          'damageupnaturebase', 'damageuppsychebase', 'damageuppsychicallybase')}}
# The workshop spells one key differently from the role API.
WORKSHOP_KEYS = {'damageupsychebase': 'damageuppsychebase'}


def spec():
    catalog = [dict(canonical_id=key, label=label, kinds=['drive', 'cartridge'], main=key in CARTRIDGE_MAINS, sub=True, unit=unit)
               for key, (label, unit) in SUBSTATS.items()]
    catalog += [dict(canonical_id=key, label=label, kinds=['cartridge'], main=True, sub=False, unit=unit) for key, (label, unit) in MAIN_ONLY.items()]
    units = {entry['canonical_id']: entry['unit'] for entry in catalog}
    return dict(version=f'nte-builtin-{DATA_VERSION}', quality_factors=QUALITY_FACTORS, eligible_substats=list(SUBSTATS),
                mainstat_reference_values=[dict(canonical_id=key, value=value, unit=units[key], context={'kind': 'cartridge'})
                                           for key, value in REFERENCES.items()],
                catalog=catalog, aliases={})


def _weight(value):
    if type(value) not in (int, float) or not 0 <= value <= 1:
        raise SystemExit(f'weight outside 0..1: {value!r}')
    return format(Decimal(str(value)).normalize(), 'f')


def characters(payload):
    if payload.get('code') != 200 or not isinstance(payload.get('data'), list):
        raise SystemExit('unexpected workshop payload')
    mains = CARTRIDGE_MAINS | set(MAIN_ONLY)
    out = {}
    for row in payload['data']:
        identity = str(row['itemId'])
        if not identity.isdigit() or identity in out:
            raise SystemExit(f'bad or duplicate character id: {identity!r}')
        sub, main = {}, {}
        for entry in row['weightConfig']['weights']:
            key = WORKSHOP_KEYS.get(entry['key'], entry['key'])
            # Zero weights are dropped; keys outside the measured catalog (基础攻击力, 受治疗加成) cannot score.
            if key in SUBSTATS and entry['value']:
                sub[key] = _weight(entry['value'])
            if key in mains and entry['main_value']:
                main[key] = _weight(entry['main_value'])
        out[identity] = dict(name=row['name'], substat_weights=dict(sorted(sub.items())), mainstat_weights=dict(sorted(main.items())))
    return out


def build(raw, fetched_at):
    payload = json.loads(raw)
    if payload.get('notice') and NOTICE not in payload['notice']:
        raise SystemExit('workshop notice changed: review the attribution before rebuilding')
    return dict(schema_version=1, formula='nte-custom-weighting-v1', data_version=DATA_VERSION,
                provenance=dict(source='异环工坊', endpoint=ENDPOINT, fetched_at=fetched_at,
                                payload_sha256=hashlib.sha256(raw).hexdigest(), notice=NOTICE, license='unstated',
                                changes='Modified by game-manage: keyed by game character ID; weight keys mapped to the role API stat IDs; zero weights and keys outside the measured stat catalog dropped. The scoring spec (catalog, quality factors, cartridge main references) is not workshop data.'),
                spec=spec(), characters=dict(sorted(characters(payload).items())))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--snapshot', required=True, type=Path)
    parser.add_argument('--fetched-at', help='UTC time the snapshot was fetched (required to write)')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    raw = args.snapshot.read_bytes()
    if args.check:
        current = json.loads(args.output.read_text(encoding='utf-8'))
        fresh = build(raw, current['provenance']['fetched_at'])
        problems = [f'character {key}' for key, value in fresh['characters'].items() if current['characters'].get(key) != value]
        problems += [field for field in ('schema_version', 'formula', 'data_version', 'spec') if current.get(field) != fresh[field]]
        full = fresh['provenance']['payload_sha256'] == current['provenance']['payload_sha256']
        if full and current != fresh:
            problems.append('file differs from a rebuild of the same snapshot')
        if problems:
            print('mismatch: ' + ', '.join(problems), file=sys.stderr)
            return 1
        print(f"ok: spec and {len(fresh['characters'])} characters match" + ('' if full else ' (partial snapshot)'))
        return 0
    if not args.fetched_at:
        parser.error('--fetched-at is required to write')
    args.output.write_text(json.dumps(build(raw, args.fetched_at), ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'wrote {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
