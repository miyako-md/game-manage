from datetime import datetime, timezone

from game_assistant.adapters.league_of_legends.matches import (
    compute_stats, parse_match_detail, parse_match_history,
)
from game_assistant.models import MatchSummary

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


def test_damage_extracted():
    game = {**GAME, "participants": [
        {**GAME["participants"][0],
         "stats": {"kills": 1, "deaths": 2, "assists": 3, "win": True,
                   "totalDamageDealtToChampions": 21450}}]}
    m = parse_match_history({"games": {"games": [game]}}, "ME")[0]
    assert m.damage == 21450


CATALOG = {157: {"name": "疾风剑豪", "icon": None},
           160: {"name": "无双剑姬", "icon": None},
           22: {"name": "寒冰射手", "icon": None}}


def _detail_game():
    """10 人双队真实形状：participants + participantIdentities + teams。"""
    participants, identities = [], []
    for i in range(1, 11):
        team = 100 if i <= 5 else 200
        participants.append({
            "participantId": i, "championId": 160 if i <= 5 else 22,
            "teamId": team,
            "stats": {
                "kills": i, "deaths": 11 - i, "assists": i * 2,
                "item0": 1001 if i <= 5 else 0, "item1": 0, "item2": 3003,
                "item3": 0, "item4": 0, "item5": 0, "item6": 3340,
                "goldEarned": 10000 + i * 100, "champLevel": 17 + (i % 2),
                "totalDamageDealtToChampions": 20000 + i * 10,
                "win": team == 100,
            },
        })
        identities.append({"participantId": i,
                           "player": {"puuid": "ME" if i == 3 else f"P{i}",
                                      "gameName": f"玩家{i}"}})
    return {
        "gameId": 987654321, "gameMode": "CLASSIC", "queueId": 420,
        "gameCreation": 1788525600000, "gameDuration": 2135,
        "teams": [{"teamId": 100, "win": "Win"}, {"teamId": 200, "win": "Fail"}],
        "participantIdentities": identities, "participants": participants,
    }


def test_parse_match_detail_basic():
    d = parse_match_detail(_detail_game(), "ME", CATALOG)
    assert d.match_id == "987654321" and d.mode == "CLASSIC"
    assert d.duration_seconds == 2135
    assert d.start_at == datetime.fromtimestamp(1788525600, tz=timezone.utc)
    assert len(d.teams) == 2
    own = [p for t in d.teams for p in t.participants if p.is_own]
    assert len(own) == 1
    me = own[0]
    assert me.champion_id == 160 and me.champion_name == "无双剑姬"  # catalog 命名
    assert me.role_name == "玩家3" and me.team_id == 100 and me.win is True
    assert (me.kills, me.deaths, me.assists) == (3, 8, 6)
    assert me.level == 18 and me.gold == 10300 and me.damage == 20030


def test_parse_match_detail_items_filtered():
    d = parse_match_detail(_detail_game(), "ME", CATALOG)
    me = next(p for t in d.teams for p in t.participants if p.is_own)
    assert me.items == [1001, 3003, 3340]  # item0..item6 过滤 0（含第 7 格饰品）
    other = d.teams[1].participants[0]
    assert other.items == [3003, 3340]  # item0=0 被过滤


def test_parse_match_detail_teams_own_first():
    d = parse_match_detail(_detail_game(), "ME", CATALOG)
    assert [t.team_id for t in d.teams] == [100, 200]  # 我方在前
    assert all(len(t.participants) == 5 for t in d.teams)
    assert d.teams[0].win is True and d.teams[1].win is False
    # 队内按 participantId 升序
    assert [p.role_name for p in d.teams[0].participants] == \
        [f"玩家{i}" for i in range(1, 6)]


def test_parse_match_detail_win_fallback_from_teams():
    game = _detail_game()
    for p in game["participants"]:
        p["stats"] = {**p["stats"], "win": "Win" if p["teamId"] == 100 else "Fail"}
    d = parse_match_detail(game, "ME", None)
    me = next(p for t in d.teams for p in t.participants if p.is_own)
    assert me.win is True  # stats.win 非 bool → teams 兜底
    # catalog 缺失 → champion_name 为 None，前端回退"英雄 #id"
    assert me.champion_name is None


def test_parse_match_detail_empty_raw():
    d = parse_match_detail({}, "ME", None)
    assert d.match_id == "None" and d.teams == []




def _summary(n, *, win=True, kills=2, deaths=1, assists=3, damage=1000,
             duration=1000, champion_id=157, match_id=None):
    return MatchSummary(
        match_id=match_id or str(n), queue_id=450, mode="ARAM",
        duration_seconds=duration, win=win, champion_id=champion_id,
        kills=kills, deaths=deaths, assists=assists, damage=damage,
    )


def test_compute_stats_empty():
    s = compute_stats([])
    assert s.total_games == 0 and s.winrate is None and s.records == []


def test_compute_stats_rates_and_averages():
    summaries = [
        _summary(1, win=True, kills=10, deaths=2, assists=5),
        _summary(2, win=False, kills=1, deaths=8, assists=1),
        _summary(3, win=True, kills=4, deaths=3, assists=12),
        _summary(4, win=True, kills=6, deaths=1, assists=6),
        _summary(5, win=False, kills=3, deaths=6, assists=6),
    ]
    s = compute_stats(summaries, CATALOG)
    assert (s.total_games, s.wins) == (5, 3)
    assert s.winrate == 60.0
    assert (s.avg_kills, s.avg_deaths, s.avg_assists) == (4.8, 4.0, 6.0)


def test_compute_stats_top_champions_order_and_names():
    summaries = [
        # 157×3 场、22×2 场、160×2 场、1×1 场 → top5 按场次降序，平局按 id 升序
        _summary(1, champion_id=157, match_id="m1"),
        _summary(2, champion_id=157, win=False, match_id="m2"),
        _summary(3, champion_id=157, match_id="m3"),
        _summary(4, champion_id=22, match_id="m4"),
        _summary(5, champion_id=22, win=False, match_id="m5"),
        _summary(6, champion_id=160, match_id="m6"),
        _summary(7, champion_id=160, win=False, match_id="m7"),
        _summary(8, champion_id=1, match_id="m8"),
        _summary(9, champion_id=None),  # 无英雄不计入常用
    ]
    s = compute_stats(summaries, CATALOG)
    assert [(c.champion_id, c.games, c.wins) for c in s.top_champions] == [
        (157, 3, 2), (22, 2, 1), (160, 2, 1), (1, 1, 1)]
    assert s.top_champions[0].champion_name == "疾风剑豪"
    assert s.top_champions[3].champion_name == "英雄 #1"  # catalog 未收录
    assert len(s.top_champions) == 4


def test_compute_stats_top_champions_capped_at_five():
    summaries = [_summary(i, champion_id=100 + i) for i in range(7)]
    s = compute_stats(summaries, None)
    assert len(s.top_champions) == 5
    assert s.top_champions[0].champion_name == "英雄 #100"  # 平局按 id 升序


def test_compute_stats_records():
    summaries = [
        _summary(1, kills=5, assists=7, damage=21450, duration=2135, match_id="m1"),
        _summary(2, kills=22, assists=3, damage=50000, duration=900, match_id="m2"),
        _summary(3, kills=1, assists=30, damage=8000, duration=2500, match_id="m3"),
    ]
    s = compute_stats(summaries, CATALOG)
    by_label = {r["label"]: r for r in s.records}
    assert by_label["单场最高击杀"] == {"label": "单场最高击杀",
                                       "value": "22", "match_id": "m2"}
    assert by_label["单场最高助攻"] == {"label": "单场最高助攻",
                                       "value": "30", "match_id": "m3"}
    assert by_label["最高伤害"] == {"label": "最高伤害",
                                    "value": "50,000", "match_id": "m2"}  # 千分位
    assert by_label["最长对局"] == {"label": "最长对局",
                                    "value": "41分40秒", "match_id": "m3"}


def test_compute_stats_damage_record_skipped_when_all_none():
    summaries = [_summary(1, damage=None), _summary(2, damage=None)]
    s = compute_stats(summaries, None)
    labels = [r["label"] for r in s.records]
    assert "最高伤害" not in labels
    assert set(labels) == {"单场最高击杀", "单场最高助攻", "最长对局"}
