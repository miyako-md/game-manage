from datetime import datetime, timezone

from game_assistant.adapters.league_of_legends.matches import parse_match_history

# fixture 形状校准来源：C:\GPT\LOLhelper pigeon/collector.py _payload_from_lcu（真实数据验证）
GAME = {
    "gameId": 1234567890, "queueId": 450, "gameMode": "ARAM",
    "gameCreation": 1788525600000, "gameDuration": 1234,
    "teams": [{"teamId": 100, "win": "Win"}, {"teamId": 200, "win": "Fail"}],
    "participantIdentities": [
        {"participantId": 1, "player": {"puuid": "ME", "summonerId": 9}},
        {"participantId": 2, "player": {"puuid": "OTHER"}},
    ],
    "participants": [
        {"participantId": 1, "championId": 157, "teamId": 100,
         "stats": {"kills": 8, "deaths": 3, "assists": 10, "win": True}},
        {"participantId": 2, "championId": 22, "teamId": 200,
         "stats": {"kills": 2, "deaths": 8, "assists": 4, "win": False}},
    ],
}


def test_parse_own_summary():
    items = parse_match_history({"games": {"games": [GAME]}}, "ME")
    assert len(items) == 1
    m = items[0]
    assert m.match_id == "1234567890" and m.queue_id == 450 and m.mode == "ARAM"
    assert m.start_at == datetime.fromtimestamp(1788525600, tz=timezone.utc)
    assert m.duration_seconds == 1234
    assert m.win is True and m.champion_id == 157
    assert (m.kills, m.deaths, m.assists) == (8, 3, 10)


def test_parse_other_puuid_skipped():
    items = parse_match_history({"games": {"games": [GAME]}}, "NOT-ME")
    assert items[0].kills is None and items[0].win is None


def test_win_fallback_from_teams():
    game = {**GAME, "participants": [
        {**GAME["participants"][0],
         "stats": {"kills": 1, "deaths": 2, "assists": 3}}]}
    items = parse_match_history({"games": {"games": [game]}}, "ME")
    assert items[0].win is True  # teams[0].win == "Win" 且自己 teamId=100


def test_empty_history():
    assert parse_match_history({}, "ME") == []
