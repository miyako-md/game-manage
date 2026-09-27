"""Pure, account-owned LCU archive analysis; no network, credentials or persistence.

Score constants and formula adapted from user-owned miyako-md/LOLhelper,
pigeon/stats.py at c2dc013368086c318f35bbd1db32891f171e0f3a (v3).
Single scores use its 3–16 display conversion, without a win bonus. Aggregate
scores are arithmetic means of available single display scores, without the
upstream squad-size confidence shrinkage. Require five identified teammates
and all seven metrics instead of upstream's missing-as-zero fallback.

Dates deliberately use Beijing calendar midnight, not upstream clock.py's
04:00 logical day. Win rates exclude unknown outcomes. Augment pair counts
describe local co-occurrence only; no external strength/causality is inferred.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations
import math

from .champions import ChampionCatalog


BEIJING = timezone(timedelta(hours=8))
SCORE_W_COMBAT = 0.40
SCORE_W_DAMAGE = 0.30
SCORE_W_TANK = 0.12
SCORE_W_CC = 0.08
SCORE_W_ECONOMY = 0.10
KDA_FULL = 6.2
KP_FULL = 0.83
DS_FULL = 0.29
TS_FULL = 0.31
CC_FULL = 0.38
GS_FULL = 0.22
SCORE_CALIB = 0.74
METRICS = ("kills", "deaths", "assists", "totalDamageDealtToChampions",
           "goldEarned", "totalDamageTaken", "timeCCingOthers")


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def _id(value):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
        return number if number > 0 and str(number) == str(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _dict(value):
    return value if isinstance(value, dict) else {}


def _rows(value):
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _timestamp(value, *, milliseconds=False):
    try:
        if isinstance(value, datetime):
            # An injected naive clock is interpreted as UTC, independently of host TZ.
            return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)
        number = _number(value)
        if number is not None:
            if number <= 0:
                return None
            return datetime.fromtimestamp(number / (1000 if milliseconds or number >= 1e11 else 1), timezone.utc)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return None  # LCU timestamps must identify their timezone.
            return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    return None


def _start(record):
    return _timestamp(record.get("gameCreation"), milliseconds=True) or _timestamp(record.get("gameCreationDate"))


def _iso(value):
    return value.isoformat() if value is not None else None


def _identities(record):
    """Map participant IDs to a single unambiguous PUUID; ambiguous IDs are unusable."""
    values = defaultdict(set)
    for identity in _rows(record.get("participantIdentities")):
        pid = _id(identity.get("participantId"))
        puuid = _dict(identity.get("player")).get("puuid")
        if pid and isinstance(puuid, str) and puuid.strip():
            values[pid].add(puuid)
    for participant in _rows(record.get("participants")):
        pid = _id(participant.get("participantId"))
        puuid = participant.get("puuid")
        if pid and isinstance(puuid, str) and puuid.strip():
            values[pid].add(puuid)
    return {pid: next(iter(puuids)) for pid, puuids in values.items() if len(puuids) == 1}


def _owner(record, own_puuid):
    if not isinstance(own_puuid, str) or not own_puuid.strip():
        return None
    identities = _identities(record)
    found = [p for p in _rows(record.get("participants"))
             if identities.get(_id(p.get("participantId"))) == own_puuid]
    return found[0] if len(found) == 1 else None


def _win_value(value):
    if value is True or value == "Win":
        return True
    if value is False or value in ("Fail", "Loss"):
        return False
    return None


def participant_outcome(record, participant):
    team_id = _id(participant.get("teamId"))
    if team_id not in (100, 200):
        return None
    results = defaultdict(set)
    for team in _rows(record.get("teams")):
        tid, result = _id(team.get("teamId")), _win_value(team.get("win"))
        if tid in (100, 200) and result is not None:
            results[tid].add(result)
    if any(len(values) != 1 for values in results.values()):
        return None
    if len(results) == 2 and results[100] == results[200]:
        return None
    if team_id in results:
        return next(iter(results[team_id]))
    # A unique opponent's objective result determines the two-team outcome.
    other = 200 if team_id == 100 else 100
    return not next(iter(results[other])) if other in results else None


def _team(record, own):
    tid = _id(own.get("teamId"))
    if tid not in (100, 200):
        return []
    team = [p for p in _rows(record.get("participants")) if _id(p.get("teamId")) == tid]
    identities = _identities(record)
    ids = [_id(p.get("participantId")) for p in team]
    if len(team) != 5 or any(pid is None or not 1 <= pid <= 10 for pid in ids) or len(set(ids)) != 5:
        return []
    # IDs duplicated across teams also make the identity join ambiguous.
    all_ids = [_id(p.get("participantId")) for p in _rows(record.get("participants"))]
    if any(all_ids.count(pid) != 1 for pid in ids):
        return []
    puuids = [identities.get(pid) for pid in ids]
    if None in puuids or len(set(puuids)) != 5:
        return []
    return team


def _score_metrics(record, own):
    team = _team(record, own)
    if not team:
        return None, None, None
    stats = _dict(own.get("stats"))
    values = {field: [_number(_dict(p.get("stats")).get(field)) for p in team] for field in METRICS}
    totals = {field: sum(numbers) if None not in numbers else None for field, numbers in values.items()}
    totals = {field: _number(value) for field, value in totals.items()}
    k, d, a = (_number(stats.get(field)) for field in METRICS[:3])
    damage = _number(stats.get("totalDamageDealtToChampions"))
    kp = (k + a) / totals["kills"] if k is not None and a is not None and totals["kills"] else None
    ds = damage / totals["totalDamageDealtToChampions"] if damage is not None and totals["totalDamageDealtToChampions"] else None
    display_kp = round(kp * 100, 1) if kp is not None and math.isfinite(kp * 100) else None
    display_ds = round(ds * 100, 1) if ds is not None and math.isfinite(ds * 100) else None
    if any(value is None for value in totals.values()):
        return None, display_kp, display_ds
    kda = (k + a) / max(d, 1)
    gs = stats["goldEarned"] / totals["goldEarned"] if totals["goldEarned"] else 0
    taken = stats["totalDamageTaken"] / totals["totalDamageTaken"] if totals["totalDamageTaken"] else 0
    cc = stats["timeCCingOthers"] / totals["timeCCingOthers"] if totals["timeCCingOthers"] else 0
    combat = 0.6 * min(kda / KDA_FULL, 1.0) + 0.4 * min((kp or 0) / KP_FULL, 1.0)
    raw = (SCORE_W_COMBAT * combat + SCORE_W_DAMAGE * min((ds or 0) / DS_FULL, 1.0)
           + SCORE_W_TANK * min(taken / TS_FULL, 1.0) + SCORE_W_CC * min(cc / CC_FULL, 1.0)
           + SCORE_W_ECONOMY * min(gs / GS_FULL, 1.0)) * 100 * SCORE_CALIB
    return round(3.0 + raw / 100.0 * 13.0, 1), display_kp, display_ds


def _augments(own):
    stats = _dict(own.get("stats"))
    candidates = [stats.get(f"playerAugment{i}") for i in range(1, 7)]
    for source in (own, stats):
        if isinstance(source.get("augments"), list):
            candidates.extend(source["augments"])
    ids = {_id(value.get("id") if isinstance(value, dict) else value) for value in candidates}
    return [{"id": aid, "name": f"强化 #{aid}"} for aid in sorted(ids - {None})]


def _champion_name(catalog, champion_id):
    return ChampionCatalog.name_for(catalog or {}, champion_id) or (f"英雄 #{champion_id}" if champion_id else "未知英雄")


def _match(record, own, catalog):
    stats = _dict(own.get("stats"))
    score, kp, damage_share = _score_metrics(record, own)
    cid = _id(own.get("championId"))
    labels = [label for field, label in (("pentaKills", "五杀"), ("quadraKills", "四杀"))
              if (_number(stats.get(field)) or 0) > 0]
    return {
        "match_id": str(record["gameId"]), "queue_id": _id(record.get("queueId")),
        "mode": record.get("gameMode") if isinstance(record.get("gameMode"), str) else None,
        "start_at": _iso(_start(record)), "duration_seconds": _number(record.get("gameDuration")),
        "win": participant_outcome(record, own), "champion_id": cid,
        "champion_name": _champion_name(catalog, cid),
        "kills": _number(stats.get("kills")), "deaths": _number(stats.get("deaths")),
        "assists": _number(stats.get("assists")), "damage": _number(stats.get("totalDamageDealtToChampions")),
        "score": score, "kp": kp, "damage_share": damage_share,
        "score_kind": "lolhelper_v3" if _id(record.get("queueId")) == 2400 else "reference",
        "augments": _augments(own) if _id(record.get("queueId")) == 2400 else [],
        "highlights": labels,
    }


def _average(rows, field):
    values = [r[field] for r in rows if r[field] is not None]
    # Divide before summing to avoid overflowing otherwise finite source metrics.
    return round(sum(v / len(values) for v in values), 1) if values else None


def _summary(rows):
    wins = sum(r["win"] is True for r in rows)
    known = sum(r["win"] is not None for r in rows)
    return {"games": len(rows), "wins": wins,
            "winrate": round(wins / known * 100, 1) if known else None,
            "average_score": _average(rows, "score")}


def _hextech(matches):
    rows = [m for m in matches if m["queue_id"] == 2400]
    augments, pairs = defaultdict(list), defaultdict(list)
    for row in rows:
        ids = [a["id"] for a in row["augments"]]
        for aid in ids:
            augments[aid].append(row)
        for pair in combinations(ids, 2):
            pairs[pair].append(row)
    def counts(samples):
        return {k: v for k, v in _summary(samples).items() if k != "average_score"}
    return {
        "games": len(rows), "recorded_games": sum(bool(r["augments"]) for r in rows),
        "augments": [{"id": aid, "name": f"强化 #{aid}", **counts(samples)}
                     for aid, samples in sorted(augments.items(), key=lambda p: (-len(p[1]), p[0]))],
        "combinations": [{"ids": list(pair), "names": [f"强化 #{aid}" for aid in pair], **counts(samples)}
                         for pair, samples in sorted(pairs.items(), key=lambda p: (-len(p[1]), p[0]))],
        "rating_status": "unavailable",
        "rating_note": "未接入同版本英雄强化外部样本，无法生成胡烂评级。胜率仅为个人已记录样本，组合为两两共现，不代表强度或因果。",
    }


def _quality(record, own):
    parts = _rows(record.get("participants"))
    return (_score_metrics(record, own)[0] is not None, len(parts),
            sum(_number(_dict(p.get("stats")).get(field)) is not None for p in parts for field in METRICS),
            participant_outcome(record, own) is not None, _start(record) is not None, len(_augments(own)))


def analyze_matches(records, own_puuid, catalog=None, *, days=90, queue_id=None, now=None):
    """Return schema v1 for unique, owned LCU game dicts, newest first.

    days counts Beijing calendar dates including today; zero includes undated
    archive records. now accepts aware/naive-UTC datetime or epoch seconds/ms.
    Coverage first/last spans the owned archive before date/queue filtering.
    Missing timestamps never enter dated charts. Unknown newest results break
    streaks. detail_games means ten unique participants with both teams present.
    """
    if days not in (0, 7, 30, 90, 365):
        raise ValueError("days must be 0, 7, 30, 90 or 365")
    clock = datetime.now(timezone.utc) if now is None else _timestamp(now)
    if clock is None:
        raise ValueError("now must be a valid datetime or epoch timestamp")
    today = clock.astimezone(BEIJING).date()
    cutoff = today - timedelta(days=days - 1) if days else None
    unique = {}
    for record in records:
        if not isinstance(record, dict) or _id(record.get("gameId")) is None:
            continue
        own = _owner(record, own_puuid)
        if own is None:
            continue
        key = str(record["gameId"])
        quality = _quality(record, own)
        if key not in unique or quality > unique[key][2]:
            unique[key] = record, own, quality
    archive_dates = [_start(r) for r, _, _ in unique.values() if _start(r) is not None]
    selected = []
    detail_count = 0
    for record, own, _ in unique.values():
        start = _start(record)
        if queue_id is not None and _id(record.get("queueId")) != _id(queue_id):
            continue
        if days and (start is None or not cutoff <= start.astimezone(BEIJING).date() <= today):
            continue
        selected.append(_match(record, own, catalog))
        parts = _rows(record.get("participants"))
        ids = {_id(p.get("participantId")) for p in parts}
        detail_count += (len(parts) == 10 and ids == set(range(1, 11))
                         and all(sum(_id(p.get("teamId")) == tid for p in parts) == 5 for tid in (100, 200)))
    selected.sort(key=lambda r: (r["start_at"] or "", int(r["match_id"])), reverse=True)
    overview = _summary(selected)
    overview.update(losses=sum(m["win"] is False for m in selected),
                    unknown_results=sum(m["win"] is None for m in selected),
                    avg_kills=_average(selected, "kills"), avg_deaths=_average(selected, "deaths"),
                    avg_assists=_average(selected, "assists"))
    durations = [m["duration_seconds"] for m in selected if m["duration_seconds"] is not None]
    minutes = sum(value / 60 for value in durations)
    overview["play_minutes"] = round(minutes, 1) if durations and math.isfinite(minutes) else None
    streak = {"kind": "unknown", "count": 0}
    if selected and selected[0]["win"] is not None and selected[0]["start_at"] is not None:
        outcome = selected[0]["win"]
        streak["kind"] = "win" if outcome else "loss"
        for row in selected:
            if row["win"] is not outcome or row["start_at"] is None:
                break
            streak["count"] += 1
    overview["current_streak"] = streak
    by_date, by_champion = defaultdict(list), defaultdict(list)
    for row in selected:
        if row["start_at"]:
            by_date[_timestamp(row["start_at"]).astimezone(BEIJING).date().isoformat()].append(row)
        if row["champion_id"] is not None:
            by_champion[row["champion_id"]].append(row)
    trend = [{"date": date, **_summary(rows)} for date, rows in sorted(by_date.items())]
    champions = [{"champion_id": cid, "name": _champion_name(catalog, cid), **_summary(rows)}
                 for cid, rows in sorted(by_champion.items(), key=lambda p: (-len(p[1]), p[0]))]
    highlights = []
    for row in selected:
        stats = _dict(unique[row["match_id"]][1].get("stats"))
        for label in row["highlights"]:
            highlights.append({"match_id": row["match_id"], "label": label, "start_at": row["start_at"],
                               "champion_name": row["champion_name"],
                               "value": _number(stats.get("pentaKills" if label == "五杀" else "quadraKills"))})
    for field, label in (("score", "最高评分"), ("kills", "最多击杀"), ("assists", "最多助攻"), ("damage", "最高伤害")):
        candidates = [m for m in selected if m[field] is not None]
        if candidates:
            best = max(candidates, key=lambda m: m[field])
            highlights.append({"match_id": best["match_id"], "label": label, "start_at": best["start_at"],
                               "champion_name": best["champion_name"], "value": best[field]})
    return {
        "schema_version": 1, "overview": overview, "trend": trend,
        "heatmap": [{k: r[k] for k in ("date", "games", "wins")} for r in trend],
        "champions": champions, "matches": selected, "highlights": highlights, "hextech": _hextech(selected),
        "coverage": {"archived_games": len(unique), "filtered_games": len(selected), "detail_games": detail_count,
                     "score_games": sum(r["score"] is not None for r in selected),
                     "first_at": _iso(min(archive_dates)) if archive_dates else None,
                     "last_at": _iso(max(archive_dates)) if archive_dates else None,
                     "scope_note": "仅统计本账号确实参与的本机已归档记录；客户端最近窗口不等于完整历史。日期按北京时间零点划分。评分为 LOLhelper v3 展示分，其他模式仅供参考，非官方评分；缺少完整队伍指标不评分。"},
    }
