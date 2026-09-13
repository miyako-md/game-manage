from game_assistant.adapters.league_of_legends.summoner import parse_summoner

RAW = {"summonerId": 123, "puuid": "P1", "gameName": "峡谷小毕",
       "name": "旧名", "summonerLevel": 160, "profileIconId": 5553}
RANKED = {"queueMap": {"RANKED_SOLO_5x5": {
    "tier": "EMERALD", "division": "II", "leaguePoints": 33,
    "wins": 120, "losses": 110}}}


def test_parse_summoner_basic():
    acc = parse_summoner(RAW, None)
    assert acc.nickname == "峡谷小毕" and acc.level == 160
    assert acc.extra["puuid"] == "P1"
    assert acc.extra["ranked_solo"] is None


def test_parse_summoner_ranked():
    acc = parse_summoner(RAW, RANKED)
    rs = acc.extra["ranked_solo"]
    assert rs["tier"] == "EMERALD" and rs["league_points"] == 33


def test_parse_summoner_ranked_missing_queue():
    acc = parse_summoner(RAW, {"queueMap": {}})
    assert acc.extra["ranked_solo"] is None
