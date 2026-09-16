"""库街区小组件数据解析（周期进度）。数据实测来源：gamer/widget/game3/getData。

widget getData 的 data 字段（2026-09-13 实测）含一批同构的 progress 对象
（name/cur/total/status/refreshTimeStamp，10 位秒级时间戳，0=无）；data 可能为
dict 或 JSON 字符串（role.parse_widget_energy 同款兜底）。原 activityData
版本活动解析已随 ACTIVITY 能力删除（活动日历 events 承担游戏内活动展示）。
"""
import json as _json
from datetime import datetime, timedelta, timezone

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


def parse_progress(raw: dict, *, include_tower: bool = True, overrides: dict[str, ProgressItem] | None = None) -> list[ProgressItem]:
    data = _data(raw)
    items = []
    for key in PROGRESS_KEYS:
        if key == 'towerData' and not include_tower:
            continue
        if overrides and key in overrides:
            items.append(overrides[key])
            continue
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


def parse_store_energy(data: dict) -> ProgressItem:
    current, maximum = data.get('storeEnergy'), data.get('storeEnergyLimit')
    if isinstance(current, bool) or isinstance(maximum, bool) or not isinstance(current, int) or not isinstance(maximum, int) or current < 0 or maximum <= 0:
        raise ValueError('角色面板未返回有效结晶单质')
    return ProgressItem(name=data.get('storeEnergyTitle') or '结晶单质', cur=current, total=maximum)


def parse_base_progress(data: dict) -> dict[str, ProgressItem]:
    items = {'storeEnergyData': parse_store_energy(data)}
    for key, current_key, max_key, name in [
        ('livenessData', 'liveness', 'livenessMaxCount', '活跃度'),
        ('weeklyData', 'weeklyInstCount', 'weeklyInstCountLimit', data.get('weeklyInstTitle') or '战歌重奏收取次数'),
        ('weeklyRougeData', 'rougeScore', 'rougeScoreLimit', data.get('rougeTitle') or '千道门扉的异想'),
    ]:
        current, maximum = data.get(current_key), data.get(max_key)
        if isinstance(current, bool) or isinstance(maximum, bool) or not isinstance(current, int) or not isinstance(maximum, int) or current < 0 or maximum < 0:
            raise ValueError(f'角色面板未返回有效{name}进度')
        items[key] = ProgressItem(name=name, cur=current, total=maximum)
    return items


def parse_periodic_tower(data: dict, now: datetime) -> ProgressItem:
    """difficulty=3 is 深境区; seasonEndTime is remaining milliseconds, not Unix time.

    A negative duration was observed with last season's full-star record before
    refreshData. Never relabel that stale record as current-season progress.
    """
    remaining = data.get('seasonEndTime')
    if isinstance(remaining, bool) or not isinstance(remaining, (int, float)) or not 0 < remaining <= 366 * 86400000:
        raise ValueError('深境区周期数据已过期或缺失')
    zone = next((z for z in data.get('difficultyList', []) if str(z.get('difficulty')) == '3'), None)
    if zone is None or not zone.get('towerAreaList'):
        raise ValueError('未返回深境区本期进度')
    areas = zone['towerAreaList']
    for area in areas:
        if not isinstance(area.get('star'), int) or not isinstance(area.get('maxStar'), int) or not 0 <= area['star'] <= area['maxStar'] or area['maxStar'] <= 0:
            raise ValueError('深境区星数异常')
    return ProgressItem(name='逆境深塔·深境区', cur=sum(a['star'] for a in areas),
                        total=sum(a['maxStar'] for a in areas), refresh_at=now + timedelta(milliseconds=remaining))
