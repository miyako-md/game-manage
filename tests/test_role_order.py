"""Overview role order: parity with frontend/src/role-order.js and the Endfield report."""
import json
from pathlib import Path

import pytest

from game_assistant import role_order
from game_assistant.endfield_reports import build_endfield_report

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('case', json.loads((ROOT/'tests/fixtures/role_order.json').read_text(encoding='utf-8'))['cases'])
def test_shared_sample_matches_the_frontend_newest_first_order(case):
    assert [role['name'] for role in role_order.overview_roles(case['game'], case['roles'])] == case['expected']


def test_backend_wuwa_order_is_the_generated_frontend_list():
    frontend = json.loads((ROOT/'frontend/src/wuwa-role-order.json').read_text(encoding='utf-8'))
    assert list(role_order.WUWA_ORDER) == frontend['names'] and len(set(role_order.WUWA_ORDER)) == len(role_order.WUWA_ORDER)


def test_endfield_uses_the_report_level_order_and_unplaced_roles_go_last():
    operators = [{'id': 'a', 'name': '甲', 'level': 40, 'rarity': 5}, {'id': 'b', 'name': '乙', 'level': None, 'rarity': 6},
                 {'id': 'c', 'name': '丙', 'level': 60, 'rarity': 4}, {'id': 'd', 'name': '丁', 'level': 40, 'rarity': 6}, 'bad']
    ordered = role_order.overview_roles('endfield', operators)
    report = build_endfield_report({'operators': [item for item in operators if isinstance(item, dict)]})
    assert [item['id'] for item in ordered[:-1]] == [item['id'] for item in report['training']['items']] == ['c', 'd', 'a', 'b']
    assert ordered[-1] == 'bad'


def test_malformed_ids_and_names_are_unplaced_never_invented():
    assert role_order.recency('nte', {'id': True}) is None and role_order.recency('nte', {'id': '-3'}) is None
    assert role_order.recency('nte', {'id': '0012'}) == 12 and role_order.recency('wuthering_waves', {'name': ['今汐']}) is None
    assert role_order.recency('endfield', {'id': '1'}) is None and role_order.recency('nte', None) is None
    roles = [{'name': '无编号'}, {'id': '7', 'name': '有编号'}]
    assert [role['name'] for role in role_order.overview_roles('nte', roles)] == ['有编号', '无编号']
