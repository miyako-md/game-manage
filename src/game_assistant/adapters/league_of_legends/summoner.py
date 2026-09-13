from game_assistant.models import AccountInfo


def parse_summoner(raw: dict, ranked_raw: dict | None) -> AccountInfo:
    ranked = None
    qm = (ranked_raw or {}).get("queueMap") or {}
    solo = qm.get("RANKED_SOLO_5x5") or {}
    if solo:
        ranked = {
            "tier": solo.get("tier"), "division": solo.get("division"),
            "league_points": solo.get("leaguePoints"),
            "wins": solo.get("wins"), "losses": solo.get("losses"),
        }
    return AccountInfo(
        nickname=raw.get("gameName") or raw.get("name"),
        level=raw.get("summonerLevel"),
        extra={"puuid": raw.get("puuid"), "profile_icon_id": raw.get("profileIconId"),
               "ranked_solo": ranked},
    )
