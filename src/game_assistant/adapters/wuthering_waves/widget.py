"""库街区小组件数据解析（周期进度）。数据实测来源：gamer/widget/game3/getData。

widget getData 的 data 字段（2026-09-13 实测）含一批同构的 progress 对象
（name/cur/total/status/refreshTimeStamp，10 位秒级时间戳，0=无）；data 可能为
dict 或 JSON 字符串（role.parse_widget_energy 同款兜底）。原 activityData
版本活动解析已随 ACTIVITY 能力删除（活动日历 events 承担游戏内活动展示）。
"""
import json as _json
from datetime import datetime, timezone

from game_assistant.models import ProgressItem

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
