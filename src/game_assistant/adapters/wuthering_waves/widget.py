"""库街区小组件数据解析（版本活动 + 周期进度）。数据实测来源：gamer/widget/game3/getData。

widget getData 的 data 字段（2026-09-13 实测）含 activityData 与一批同构的
progress 对象（name/cur/total/status/refreshTimeStamp，10 位秒级时间戳，0=无）；
data 可能为 dict 或 JSON 字符串（role.parse_widget_energy 同款兜底）。
"""
import json as _json
from datetime import datetime, timezone

from game_assistant.models import CoreReward, ProgressItem, VersionActivity

# 周期进度固定 key（energyData 除外：体力单独走 stamina 能力，不重复展示）
PROGRESS_KEYS = ["towerData", "slashTowerData", "weeklyData", "weeklyRougeData",
                 "newTowerData", "weeklyFrameData", "livenessData", "storeEnergyData"]


def _data(raw: dict) -> dict:
    data = raw.get("data")
    if isinstance(data, str):
        data = _json.loads(data)
    return data or {}


def _seconds_ts(v) -> datetime | None:
    try:
        ts = int(v)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def parse_version_activity(raw: dict) -> VersionActivity | None:
    act = _data(raw).get("activityData")
    if not act:
        return None
    return VersionActivity(
        title=act.get("title") or "",
        end_at=_seconds_ts(act.get("endTime")),
        enabled=bool(act.get("enabled", True)),
        core_rewards=[CoreReward(name=c.get("name") or "", cur=int(c.get("cur") or 0),
                                 total=int(c.get("total") or 0),
                                 status=int(c.get("status") or 0))
                      for c in act.get("coreRewards") or []])


def parse_progress(raw: dict) -> list[ProgressItem]:
    data = _data(raw)
    items = []
    for key in PROGRESS_KEYS:
        obj = data.get(key)
        if not obj:
            continue
        items.append(ProgressItem(name=obj.get("name") or key,
                                  cur=int(obj.get("cur") or 0),
                                  total=int(obj.get("total") or 0),
                                  refresh_at=_seconds_ts(obj.get("refreshTimeStamp")),
                                  status=int(obj.get("status") or 0)))
    for bp in data.get("battlePassData") or []:
        items.append(ProgressItem(name=bp.get("name") or "",
                                  cur=int(bp.get("cur") or 0),
                                  total=int(bp.get("total") or 0),
                                  refresh_at=_seconds_ts(bp.get("refreshTimeStamp")),
                                  status=int(bp.get("status") or 0)))
    return items
