from datetime import datetime, timezone

from game_assistant.models import MatchSummary


def _own_summary(game: dict, own_puuid: str) -> MatchSummary:
    creation = game.get("gameCreation")
    start_at = (datetime.fromtimestamp(creation / 1000, tz=timezone.utc)
                if creation else None)
    ident_pid = None
    for ident in game.get("participantIdentities") or []:
        if (ident.get("player") or {}).get("puuid") == own_puuid:
            ident_pid = ident.get("participantId")
            break
    champion = kills = deaths = assists = team = win = None
    for p in game.get("participants") or []:
        if p.get("participantId") != ident_pid:
            continue
        stats = p.get("stats") or {}
        champion, team = p.get("championId"), p.get("teamId")
        kills, deaths, assists = (stats.get("kills"), stats.get("deaths"),
                                  stats.get("assists"))
        win = stats.get("win") if isinstance(stats.get("win"), bool) else None
        break
    if win is None and team is not None:
        for t in game.get("teams") or []:
            if t.get("win") == "Win" and t.get("teamId") == team:
                win = True
            elif t.get("teamId") == team:
                win = False
    return MatchSummary(
        match_id=str(game.get("gameId")), queue_id=game.get("queueId"),
        mode=game.get("gameMode") or "", start_at=start_at,
        duration_seconds=game.get("gameDuration"),
        win=win, champion_id=champion,
        kills=kills, deaths=deaths, assists=assists,
    )


def parse_match_history(raw: dict, own_puuid: str) -> list[MatchSummary]:
    games = ((raw or {}).get("games") or {}).get("games") or []
    out = []
    for game in games:
        if not game.get("gameId"):
            continue
        out.append(_own_summary(game, own_puuid))
    return out
