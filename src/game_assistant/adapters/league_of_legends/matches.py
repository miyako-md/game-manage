from datetime import datetime, timezone

from game_assistant.models import (
    ChampionStat, MatchDetail, MatchParticipant, MatchSummary, MatchTeam,
    StatsSummary,
)
from game_assistant.adapters.league_of_legends.champions import ChampionCatalog


# 召唤师峡谷最早 15 分钟才能投降，5 分钟内结束的只会是重开或中途中止。
REMAKE_SECONDS = 300


def is_remake(stats: dict, duration_seconds) -> bool:
    if stats.get("gameEndedInEarlySurrender") is True:
        return True
    return isinstance(duration_seconds, (int, float)) and 0 <= duration_seconds < REMAKE_SECONDS


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
    champion = kills = deaths = assists = damage = team = win = None
    stats: dict = {}
    for p in game.get("participants") or []:
        if p.get("participantId") != ident_pid:
            continue
        stats = p.get("stats") or {}
        champion, team = p.get("championId"), p.get("teamId")
        kills, deaths, assists = (stats.get("kills"), stats.get("deaths"),
                                  stats.get("assists"))
        damage = stats.get("totalDamageDealtToChampions")
        win = _win_from(stats, team, _team_win(game))
        break
    return MatchSummary(
        match_id=str(game.get("gameId")), queue_id=game.get("queueId"),
        mode=game.get("gameMode") or "", start_at=start_at,
        duration_seconds=game.get("gameDuration"),
        win=win, champion_id=champion,
        kills=kills, deaths=deaths, assists=assists, damage=damage,
        remake=is_remake(stats, game.get("gameDuration")),
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


def _fmt_duration(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}分{s}秒"


_RECORDS = [
    # (label, MatchSummary 字段, value 格式化)
    ("单场最高击杀", "kills", lambda v: str(v)),
    ("单场最高助攻", "assists", lambda v: str(v)),
    ("最高伤害", "damage", lambda v: f"{int(v):,}"),
    ("最长对局", "duration_seconds", _fmt_duration),
]


def compute_stats(summaries: list[MatchSummary],
                  catalog: dict[int, dict] | None = None) -> StatsSummary:
    """生涯统计+名场面（输入 = parse_match_history 输出，近 20 场口径）。"""
    total = len(summaries)
    if total == 0:
        return StatsSummary()
    # 重开不算真正的一局；结果未知的对局只是不进胜率分母，不能按负场算。
    played = [s for s in summaries if not s.remake]
    decided = [s for s in played if s.win is not None]
    wins = sum(1 for s in decided if s.win is True)

    def avg(field: str) -> float | None:
        vals = [getattr(s, field) for s in played
                if getattr(s, field) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    groups: dict[int, list[MatchSummary]] = {}
    for s in played:
        if s.champion_id is not None:
            groups.setdefault(s.champion_id, []).append(s)
    top = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:5]
    top_champions = [ChampionStat(
        champion_id=cid,
        champion_name=(ChampionCatalog.name_for(catalog, cid) if catalog else None)
        or f"英雄 #{cid}",
        games=len(games), wins=sum(1 for s in games if s.win is True),
        losses=sum(1 for s in games if s.win is False),
    ) for cid, games in top]

    records = []
    for label, field, fmt in _RECORDS:
        best = None
        for s in played:
            v = getattr(s, field, None)
            if v is None:  # damage=None 的场次跳过该纪录
                continue
            if best is None or v > best[0]:
                best = (v, s)
        if best:
            records.append({"label": label, "value": fmt(best[0]),
                            "match_id": best[1].match_id})

    return StatsSummary(
        total_games=total, wins=wins,
        winrate=round(wins / len(decided) * 100, 1) if decided else None,
        decided_games=len(decided), remakes=total - len(played),
        avg_kills=avg("kills"), avg_deaths=avg("deaths"), avg_assists=avg("assists"),
        top_champions=top_champions, records=records,
    )
