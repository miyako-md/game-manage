import json
from copy import deepcopy
from pathlib import Path

import pytest

from game_assistant.adapters.league_of_legends.esports_parse import (
    decode_public_payload, parse_catalog, parse_matches, parse_team,
)

FIXTURES = Path(__file__).parents[1] / 'fixtures' / 'lol_esports'


def sample(name):
    return json.loads((FIXTURES / f'{name}.json').read_text(encoding='utf-8'))


def tournament():
    return next(t for t in parse_catalog(sample('catalog'), 2026).tournaments if t.family == 'lpl')


def test_catalog_current_year_and_scope():
    result = parse_catalog(sample('catalog'), 2026)
    assert {t.family for t in result.tournaments} == {'lpl', 'first_stand', 'msi', 'ewc'}
    assert set(result.missing_families) == {'worlds', 'asian_games'}
    assert all(t.season_year == 2026 for t in result.tournaments)
    assert result.meta.coverage == 'partial'


def test_worlds_missing_and_lpl_date_conflict():
    result = parse_matches(sample('lpl'), tournament())
    assert any(m.start_at.month == 9 for m in result.matches)
    assert all(m.tournament_id == tournament().id for m in result.matches)
    assert result.meta.coverage == 'unknown'


def test_ids_remain_strings_and_duplicates_conflict():
    raw = sample('lpl')
    row = deepcopy(raw['msg'][0])
    row['bMatchId'] = '11906577704952350992'
    raw['msg'] = [row, {**row, 'ScoreA': '9'}]
    parsed = parse_matches(raw, tournament())
    assert not parsed.matches
    assert parsed.meta.coverage == 'partial'
    raw['msg'] = [row]
    assert parse_matches(raw, tournament()).matches[0].source_id == '11906577704952350992'


@pytest.mark.parametrize('status,expected', [('1', 'scheduled'), ('2', 'live'), ('3', 'completed'), ('999', 'unknown')])
def test_unknown_status_and_zero_scores(status, expected):
    raw = sample('lpl')
    raw['msg'] = [{**raw['msg'][0], 'MatchStatus': status, 'ScoreA': '0', 'ScoreB': '0'}]
    row = parse_matches(raw, tournament()).matches[0]
    assert row.status == ('unknown' if status == '3' else expected)
    if status == '1':
        assert row.score_a is None and row.winner_team_id is None


def test_team_roster_roles_and_missing_match_lineup():
    parsed = parse_team(sample('edg'), [tournament().id])
    assert parsed.team.id == 'tencent:team:1'
    assert len(parsed.players) == 6
    assert {m.scope for m in parsed.roster_memberships} == {'source_current'}
    assert all(m.match_id is None and m.tournament_id is None for m in parsed.roster_memberships)
    assert next(m for m in parsed.roster_memberships if m.player_id.endswith(':2770')).position == '打野'
    raw = sample('edg')
    raw['msg']['activePlayers'][0]['GamePlace'] = '999,'
    assert parse_team(raw, []).roster_memberships[0].position is None


def test_roster_source_time_is_not_fetch_time():
    parsed = parse_team(sample('g2'), [])
    assert parsed.meta.source_updated_at.isoformat().startswith('2026-07-02T23:50:08')
    raw = sample('g2')
    raw.pop('lastUpdateTime')
    assert parse_team(raw, []).meta.source_updated_at is None


def test_js_wrapper_never_executes():
    assert decode_public_payload('var TeamList={"status":"0","msg":{}};')['status'] == '0'
    assert decode_public_payload('{"msg": []}') == {'msg': []}
    for value in ('var A={};alert(1)', 'var A=evil()', 'cb({});', '[]'):
        with pytest.raises(ValueError):
            decode_public_payload(value)


def test_wrong_season_invalid_time_and_roster_conflict_are_partial():
    raw = sample('lpl')
    raw['msg'] = [{**raw['msg'][0], 'GameId': '2025'}, {**raw['msg'][-1], 'MatchDate': '0000-00-00'}]
    result = parse_matches(raw, tournament())
    assert len(result.matches) == 1 and result.matches[0].start_at is None
    assert result.meta.coverage == 'partial'


def test_oversize_roster_is_partial_instead_of_silently_complete():
    raw = sample('edg')
    raw['msg']['activePlayers'] = [{**raw['msg']['activePlayers'][0], 'MemberId': str(i + 1)} for i in range(201)]
    result = parse_team(raw, [])
    assert result.meta.issues and result.meta.coverage == 'partial'
    raw = sample('edg')
    raw['msg']['activePlayers'].append({**raw['msg']['activePlayers'][0], 'NickName': 'changed'})
    result = parse_team(raw, [])
    assert not any(p.source_id == '2347' for p in result.players)
    assert result.meta.coverage == 'partial'
