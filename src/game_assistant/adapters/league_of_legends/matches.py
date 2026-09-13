from datetime import datetime, timezone

from game_assistant.models import (
    MatchDetail, MatchParticipant, MatchSummary, MatchTeam,
)
from game_assistant.adapters.league_of_legends.champions import ChampionCatalog


def _win_from(stats: dict, team_id: int | None, team_win: dict[int, bool]) -> bool | None:
    # 复用现有口径：stats.win(bool) 优先，否则 teams[].win=="Win" 兜底
    if isinstance(stats.get("win"), bool):
        return stats["win"]
    return team_win.get(team_id)


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
        win = _win_from(stats, team, _team_win(game))
        break
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


def _team_win(game: dict) -> dict[int, bool]:
    # teams[].win 为 "Win"/"Fail" 字符串（2026-09-13 国服实测）
    return {t.get("teamId"): t.get("win") == "Win"
            for t in game.get("teams") or [] if t.get("teamId") is not None}


def parse_match_detail(raw: dict, own_puuid: str,
                       catalog: dict[int, dict] | None = None) -> MatchDetail:
    """对局详情（detail 即 game 本体，games 不在 raw 顶层）。"""
    raw = raw or {}
    creation = raw.get("gameCreation")
    start_at = (datetime.fromtimestamp(creation / 1000, tz=timezone.utc)
                if creation else None)
    team_win = _team_win(raw)
    pid_player: dict[int, dict] = {}
    for ident in raw.get("participantIdentities") or []:
        player = ident.get("player") or {}
        if ident.get("participantId") is not None:
            pid_player[ident["participantId"]] = player

    by_team: dict[int, list[tuple[int, MatchParticipant]]] = {}
    own_team = None
    for p in raw.get("participants") or []:
        stats = p.get("stats") or {}
        pid = p.get("participantId")
        player = pid_player.get(pid) or {}
        team_id = p.get("teamId")
        is_own = bool(own_puuid) and player.get("puuid") == own_puuid
        if is_own:
            own_team = team_id
        items = [stats.get(f"item{i}") for i in range(7)]
        champion_id = p.get("championId")
        member = MatchParticipant(
            champion_id=champion_id,
            champion_name=ChampionCatalog.name_for(catalog, champion_id)
            if catalog else None,
            role_name=player.get("gameName") or player.get("name"),
            level=stats.get("champLevel"),
            kills=stats.get("kills") or 0, deaths=stats.get("deaths") or 0,
            assists=stats.get("assists") or 0,
            items=[it for it in items if it],
            damage=stats.get("totalDamageDealtToChampions"),
            gold=stats.get("goldEarned"),
            win=_win_from(stats, team_id, team_win),
            team_id=team_id, is_own=is_own,
        )
        by_team.setdefault(team_id, []).append((pid if pid is not None else 0, member))

    # 我方队伍在前，其余按 teamId 升序；队内按 participantId 稳定排序
    teams = []
    for tid in sorted(by_team, key=lambda t: (t != own_team, t if t is not None else 0)):
        members = [m for _, m in sorted(by_team[tid], key=lambda pm: pm[0])]
        teams.append(MatchTeam(team_id=tid, win=team_win.get(tid),
                               participants=members))
    return MatchDetail(
        match_id=str(raw.get("gameId")), mode=raw.get("gameMode") or "",
        start_at=start_at, duration_seconds=raw.get("gameDuration"),
        teams=teams,
    )
