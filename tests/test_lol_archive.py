import sqlite3
import threading
from copy import deepcopy

from game_assistant.lol_archive import LolArchive


def game(owner='owner-a', match_id=123, full=False):
    count = 10 if full else 1
    return {'gameId': match_id, 'gameCreation': 1789000000000, 'queueId': 2400,
            'accessToken': 'must-not-store',
            'participants': [{'participantId': i, 'teamId': 100 if i <= 5 else 200,
                              'stats': {'kills': i}} for i in range(1, count + 1)],
            'participantIdentities': [{'participantId': 1, 'player': {'puuid': owner}}]}


def archive():
    return LolArchive(sqlite3.connect(':memory:', check_same_thread=False), threading.Lock())


def test_accounts_are_isolated_and_duplicate_summaries_cannot_erase_detail():
    store = archive()
    store.save({'puuid': 'owner-a', 'gameName': 'A'}, [game(full=True)], '2026-09-26T01:00:00+00:00')
    store.save({'puuid': 'owner-a', 'gameName': 'A'}, [game()], '2026-09-26T02:00:00+00:00')
    assert len(store.records('owner-a')) == 1
    assert len(store.detail('owner-a', '123')['participants']) == 10
    assert 'accessToken' not in store.detail('owner-a', '123')
    store.save({'puuid': 'owner-b', 'gameName': 'B'}, [game('owner-b', 456), game()], '2026-09-26T03:00:00+00:00')
    assert store.account()['puuid'] == 'owner-b'
    assert store.detail('owner-b', '123') is None
    assert len(store.records('owner-b')) == 1


def test_out_of_order_fetch_cannot_restore_old_active_account():
    store = archive()
    store.save({'puuid': 'new', 'gameName': 'New'}, [], '2026-09-26T03:00:00+00:00')
    store.save({'puuid': 'old', 'gameName': 'Old'}, [], '2026-09-26T02:00:00+00:00')
    assert store.account()['puuid'] == 'new'


def test_wrong_identity_invalid_ids_and_nonfinite_data_are_not_archived():
    store = archive()
    malformed = game()
    malformed['gameId'] = '../123'
    missing_participant = game()
    missing_participant['participants'] = []
    nonfinite = game()
    nonfinite['gameCreation'] = float('nan')
    assert store.save({'puuid': 'owner-a'}, [malformed, missing_participant, nonfinite], '2026-09-26T03:00:00+00:00') == 0
    assert store.records('owner-a') == []


def test_same_level_detail_can_update_but_missing_fields_do_not_erase_old_values():
    store = archive()
    first = game(full=True)
    first['participants'][0]['stats']['totalDamageDealtToChampions'] = 12345
    store.save({'puuid': 'owner-a'}, [first], '2026-09-26T01:00:00+00:00')
    summary = game(full=True)
    store.save({'puuid': 'owner-a'}, [summary], '2026-09-26T02:00:00+00:00')
    assert store.detail('owner-a','123')['participants'][0]['stats']['totalDamageDealtToChampions'] == 12345


def test_partial_same_size_payload_retains_outcomes_identities_and_augments():
    store = archive()
    full = game(full=True)
    full['teams'] = [{'teamId':100,'win':'Win'},{'teamId':200,'win':'Fail'}]
    full['participants'][0]['stats']['playerAugment1'] = 101
    full['participantIdentities'].append({'participantId':2,'player':{'puuid':'fixture-teammate'}})
    store.save({'puuid':'owner-a'}, [full], '2026-09-26T01:00:00+00:00')
    partial = game(full=True)
    partial['participants'][0]['stats'].update(playerAugment1=0,unrelatedMetric=100)
    store.save({'puuid':'owner-a'}, [partial], '2026-09-26T02:00:00+00:00')
    preserved = store.detail('owner-a','123')
    assert preserved['teams'] == full['teams']
    assert len(preserved['participantIdentities']) == 2
    assert preserved['participants'][0]['stats']['playerAugment1'] == 101


def test_account_observation_does_not_freshen_old_history():
    store = archive()
    store.save({'puuid':'owner-a'}, [game()], '2026-09-25T01:00:00+00:00')
    store.save({'puuid':'owner-a'}, [], '2026-09-26T01:00:00+00:00', history_observed=False)
    assert store.account()['collected_at'].startswith('2026-09-25')
    store.save({'puuid':'owner-b'}, [], '2026-09-26T02:00:00+00:00', history_observed=False)
    assert store.account()['puuid'] == 'owner-b'
    assert store.account()['collected_at'] is None
