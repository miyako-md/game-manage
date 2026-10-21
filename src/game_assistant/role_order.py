"""Overview role order, the backend twin of frontend/src/role-order.js.

Wuwa: official wiki catalogue order, newest first (the generated ``wuwa_order`` list).
NTE: numeric role id, larger first. Endfield: the report's level order
(endfield_reports.build_endfield_report). Roles a proxy cannot place go last,
then by name.
"""
import json
from pathlib import Path
import re

from .endfield_reports import _number

WUWA_ORDER = tuple(json.loads(Path(__file__).with_name('character-search-catalog.json').read_text(encoding='utf-8'))['wuwa_order'])
_WUWA_RANK = {name: len(WUWA_ORDER) - index for index, name in enumerate(WUWA_ORDER)}


def recency(game, role):
    if not isinstance(role, dict):return None
    if game == 'wuthering_waves':return _WUWA_RANK.get(role.get('name')) if isinstance(role.get('name'), str) else None
    if game == 'nte':
        value = role.get('id')
        return int(value) if type(value) in (int, str) and re.fullmatch(r'[0-9]+', str(value)) else None
    return None


def _endfield_key(role):
    level = _number(role.get('level'))
    return (-(level if level is not None else -1), -(_number(role.get('rarity')) or 0), str(role.get('name') or ''), str(role.get('id') or ''))


def overview_roles(game, entries):
    """A sorted copy; non-object rows keep their relative order after every role."""
    roles = [entry for entry in entries if isinstance(entry, dict)]
    others = [entry for entry in entries if not isinstance(entry, dict)]
    if game == 'endfield':return sorted(roles, key=_endfield_key) + others
    def key(role):
        rank = recency(game, role)
        return (rank is None, -(rank or 0), str(role.get('name') or ''))
    return sorted(roles, key=key) + others
