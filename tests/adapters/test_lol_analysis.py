"""Personal analysis contract: synthetic LCU records, never private match data."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from game_assistant.adapters.league_of_legends.analysis import analyze_matches


NOW = datetime(2026, 9, 26, 8, tzinfo=timezone.utc)


def game(mid=1, *, at="2026-09-26T01:00:00+00:00", queue=2400):
    return {
        "gameId": mid, "queueId": queue, "gameMode": "ARAM",
        "gameCreation": int(datetime.fromisoformat(at).timestamp() * 1000),
        "gameDuration": 1200,
        "teams": [{"teamId": 100, "win": "Win"}, {"teamId": 200, "win": "Fail"}],
        "participantIdentities": [
            {"participantId": i, "player": {"puuid": "OWN" if i == 1 else f"P{i}"}}
            for i in range(1, 11)
        ],
        "participants": [
            {"participantId": i, "teamId": 100 if i <= 5 else 200,
             "championId": 1 if i == 1 else i,
             "stats": {"kills": 4, "deaths": 2, "assists": 8,
                       "totalDamageDealtToChampions": 20000, "goldEarned": 10000,
                       "totalDamageTaken": 15000, "timeCCingOthers": 20,
                       "win": False, "playerAugment1": 100, "playerAugment2": 200}}
            for i in range(1, 11)
        ],
    }


def analyze(records, **kwargs):
    return analyze_matches(records, "OWN", {1: {"name": "黑暗之女"}}, now=NOW, **kwargs)


def test_empty_unknown_averages_and_json_contract():
    result = analyze([])
    assert result["schema_version"] == 1
    assert result["overview"]["games"] == 0
    assert result["overview"]["winrate"] is None
    assert result["overview"]["avg_kills"] is None
    assert result["hextech"]["rating_status"] == "unavailable"
    json.dumps(result, allow_nan=False)


def test_objective_result_and_verified_v3_formula():
    result = analyze([game()])
    row = result["matches"][0]
    assert row["win"] is True  # participant stats.win deliberately conflicts
    assert row["score"] == 10.4  # upstream raw 56.628572205379534 -> display, no win bonus
    assert row["kp"] == 60.0 and row["damage_share"] == 20.0
    assert row["champion_name"] == "黑暗之女"
    assert row["start_at"] == "2026-09-26T01:00:00+00:00"
    assert result["coverage"]["score_games"] == 1


@pytest.mark.parametrize("field", ["kills", "deaths", "assists", "totalDamageDealtToChampions",
                                    "goldEarned", "totalDamageTaken", "timeCCingOthers"])
def test_missing_teammate_metrics_block_score(field):
    record = game()
    del record["participants"][3]["stats"][field]
    assert analyze([record])["matches"][0]["score"] is None


@pytest.mark.parametrize("change", ["four", "duplicate", "missing_identity", "duplicate_puuid"])
def test_incomplete_or_ambiguous_teammate_roster_blocks_score(change):
    record = game()
    if change == "four":
        record["participants"].pop(4)
    elif change == "duplicate":
        record["participants"][4]["participantId"] = 4
    elif change == "missing_identity":
        record["participantIdentities"].pop(4)
    else:
        record["participantIdentities"][4]["player"]["puuid"] = "P4"
    assert analyze([record])["matches"][0]["score"] is None


def test_missing_and_zero_are_distinct_and_nonfinite_is_nullable():
    record = game()
    stats = record["participants"][0]["stats"]
    stats.update(kills=0, deaths=None, assists=float("nan"), totalDamageDealtToChampions=float("inf"))
    row = analyze([record])["matches"][0]
    assert row["kills"] == 0
    assert row["deaths"] is row["assists"] is row["damage"] is row["score"] is None
    json.dumps(analyze([record]), allow_nan=False)


def test_unowned_records_and_empty_owner_are_not_counted():
    foreign = game(2)
    foreign["participantIdentities"][0]["player"]["puuid"] = "OTHER"
    assert analyze([foreign, game()])["overview"]["games"] == 1
    assert analyze_matches([game()], "", now=NOW)["overview"]["games"] == 0


def test_conflicting_teams_unknown_not_loss_and_known_outcome_denominator():
    unknown = game(2)
    unknown["teams"][1]["win"] = "Win"
    result = analyze([game(), unknown])
    assert result["overview"]["wins"] == 1
    assert result["overview"]["losses"] == 0
    assert result["overview"]["unknown_results"] == 1
    assert result["overview"]["winrate"] == 100.0
    assert result["champions"][0]["winrate"] == 100.0


def test_no_team_results_never_fall_back_to_personal_win():
    record = game()
    record.pop("teams")
    assert analyze([record])["matches"][0]["win"] is None


def test_queue_filter_archive_coverage_and_beijing_calendar_boundary():
    before = game(1, at="2026-09-19T15:59:59+00:00")
    start = game(2, at="2026-09-19T16:00:00+00:00")
    other = game(3, queue=450)
    result = analyze([before, start, other], days=7, queue_id=2400)
    assert [r["match_id"] for r in result["matches"]] == ["2"]
    assert result["trend"][0]["date"] == "2026-09-20"
    assert result["heatmap"][0] == {"date": "2026-09-20", "games": 1, "wins": 1}
    assert result["coverage"]["archived_games"] == 3
    assert result["coverage"]["filtered_games"] == 1
    assert result["coverage"]["first_at"] == "2026-09-19T15:59:59+00:00"


@pytest.mark.parametrize("bad_timestamp", [None, "not-a-date", float("inf"), -1, 1e40])
def test_invalid_timestamps_preserved_only_in_all_time(bad_timestamp):
    record = game()
    record["gameCreation"] = bad_timestamp
    assert analyze([record])["overview"]["games"] == 0
    result = analyze([record], days=0)
    assert result["matches"][0]["start_at"] is None
    assert result["trend"] == []
    assert result["coverage"]["archived_games"] == 1


def test_dedup_prefers_complete_record_independent_of_order():
    complete = game()
    summary = deepcopy(complete)
    summary["participants"] = summary["participants"][:1]
    for records in ([complete, summary], [summary, complete]):
        result = analyze(records)
        assert result["overview"]["games"] == 1
        assert result["coverage"]["detail_games"] == result["coverage"]["score_games"] == 1


def test_hextech_samples_combinations_unknown_and_missing_augment_fields():
    unknown = game(2)
    unknown.pop("teams")
    missing = game(3)
    missing["participants"][0]["stats"].pop("playerAugment1")
    missing["participants"][0]["stats"].pop("playerAugment2")
    other_queue = game(4, queue=450)
    result = analyze([game(), unknown, missing, other_queue])["hextech"]
    assert result["games"] == 3 and result["recorded_games"] == 2
    assert result["augments"][0] == {"id": 100, "name": "强化 #100", "games": 2, "wins": 1, "winrate": 100.0}
    assert result["combinations"][0]["ids"] == [100, 200]
    assert result["combinations"][0]["games"] == 2
    assert result["rating_status"] == "unavailable"


def test_unknown_latest_result_breaks_current_streak_and_highlights_are_personal():
    earlier = game(1, at="2026-09-25T01:00:00+00:00")
    latest = game(2)
    latest["teams"] = []
    latest["participants"][0]["stats"]["pentaKills"] = 1
    result = analyze([earlier, latest])
    assert result["overview"]["current_streak"] == {"kind": "unknown", "count": 0}
    assert "五杀" in result["matches"][0]["highlights"]
    assert any(h["match_id"] == "2" and h["label"] == "五杀" for h in result["highlights"])


def test_now_supports_epoch_seconds_and_milliseconds():
    for now in (NOW.timestamp(), int(NOW.timestamp() * 1000), NOW.replace(tzinfo=None)):
        assert analyze_matches([game()], "OWN", now=now)["overview"]["games"] == 1


def test_known_zero_team_metrics_get_minimum_score_without_fake_ratio():
    record = game()
    for participant in record["participants"]:
        participant["stats"] = {key: 0 for key in (
            "kills", "deaths", "assists", "totalDamageDealtToChampions",
            "goldEarned", "totalDamageTaken", "timeCCingOthers")}
    row = analyze([record])["matches"][0]
    assert row["score"] == 3.0
    assert row["kp"] is row["damage_share"] is None


def test_highlights_preserve_actual_multiple_pentakill_count():
    record = game()
    record["participants"][0]["stats"]["pentaKills"] = 2
    highlights = analyze([record])["highlights"]
    assert next(h for h in highlights if h["label"] == "五杀")["value"] == 2


def test_win_and_loss_dont_change_score_and_other_queue_is_reference():
    win, loss = game(1), game(2, queue=450)
    loss["teams"][0]["win"], loss["teams"][1]["win"] = "Fail", "Win"
    result = analyze([win, loss])
    rows = {r["match_id"]: r for r in result["matches"]}
    assert rows["1"]["score"] == rows["2"]["score"]
    assert rows["2"]["score_kind"] == "reference"
    assert result["overview"]["winrate"] == 50
    assert result["overview"]["current_streak"] == {"kind": "loss", "count": 1}


def test_augments_are_unique_per_match_and_zero_slots_do_not_count():
    record = game()
    record["participants"][0]["stats"].update(playerAugment2=100, playerAugment3=0)
    result = analyze([record])["hextech"]
    assert len(result["augments"]) == 1
    assert result["augments"][0]["games"] == 1
    assert result["combinations"] == []


def test_dates_can_fall_back_to_lcu_iso_creation_date_and_unknown_champion():
    record = game()
    record.pop("gameCreation")
    record["gameCreationDate"] = "2026-09-26T09:00:00+08:00"
    record["participants"][0]["championId"] = 9999
    row = analyze([record])["matches"][0]
    assert row["start_at"] == "2026-09-26T01:00:00+00:00"
    assert row["champion_name"] == "英雄 #9999"


def test_extreme_or_malformed_records_cannot_emit_nonfinite_json():
    record = game()
    for participant in record["participants"]:
        participant["stats"]["kills"] = 1e308
    result = analyze([None, {}, {"gameId": "invalid"}, record])
    assert result["matches"][0]["score"] is None
    json.dumps(result, allow_nan=False)


def test_analysis_does_not_mutate_source_records():
    record = game()
    before = deepcopy(record)
    analyze([record])
    assert record == before
