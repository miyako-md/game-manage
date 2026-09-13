"""库街区 roleBox 数据解析（探索度 + 数据坞）。

roleBox 响应的 data 字段是 JSON 字符串（实测形状，2026-09-13），
rolebox_client.post 已二次解析为 dict；本模块再兜底兼容信封/字符串形状
（role.parse_widget_energy / widget._data 同款防御式写法）。

exploreIndex data 实测形状：
  countryProgress（百分比，可能缺失）、areaInfoList[]（areaName/areaProgress/
  itemList[]{type,name,progress}）、detectionInfoList[]（detectionName/
  levelName/level 0-3）。
calabashData data 实测形状：
  level/baseCatch("20%")/catchQuality/curExp/maxCount/phantomList[]。
"""
import json as _json
from collections import Counter

from game_assistant.models import CalabashData, ExploreArea, ExplorationData


def _data(raw) -> dict:
    """防御式取数：兼容内层 data dict / 完整信封 / JSON 字符串三种输入。"""
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except ValueError:
            return {}
    if not isinstance(raw, dict):
        return {}
    if "code" in raw and "data" in raw:  # 完整信封形状 → 取内层
        inner = raw.get("data")
        if isinstance(inner, str):
            try:
                inner = _json.loads(inner)
            except ValueError:
                return {}
        return inner if isinstance(inner, dict) else {}
    return raw


def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float_or_none(v):
    # areaProgress 是百分比（数字或 "85.5%" 字符串），统一转 float（去掉 %）
    try:
        return float(str(v).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _str_or_none(v):
    return None if v is None else str(v)


def parse_explore_index(raw) -> ExplorationData:
    """exploreIndex 响应 → ExplorationData。

    detectionInfoList 按级计数：detection_by_level = {"轻波级": n, "巨浪级": n,
    ...}（levelName 缺失时回退 "等级{level}"）；detection_count 为残象已收录数
    （列表长度）。
    """
    data = _data(raw)
    areas = []
    for a in data.get("areaInfoList") or []:
        if not isinstance(a, dict):
            continue
        items = []
        for it in a.get("itemList") or []:
            if not isinstance(it, dict) or not it.get("name"):
                continue
            progress = it.get("progress")
            items.append(f"{it['name']} {progress}" if progress is not None
                         else str(it["name"]))
        areas.append(ExploreArea(name=str(a.get("areaName") or ""),
                                 progress=_float_or_none(a.get("areaProgress")),
                                 items=items))
    by_level = Counter()
    for d in data.get("detectionInfoList") or []:
        if not isinstance(d, dict):
            continue
        key = d.get("levelName") or f"等级{d.get('level')}"
        by_level[str(key)] += 1
    return ExplorationData(
        country_progress=_str_or_none(data.get("countryProgress")),
        areas=areas,
        detection_count=sum(by_level.values()),
        detection_by_level=dict(by_level))


def parse_calabash_data(raw) -> CalabashData:
    """calabashData 响应 → 数据坞信息（phantomList 明细不展示，仅汇总字段）。"""
    data = _data(raw)
    return CalabashData(
        level=_int_or_none(data.get("level")),
        base_catch=_str_or_none(data.get("baseCatch")),
        catch_quality=_int_or_none(data.get("catchQuality")),
        cur_exp=_int_or_none(data.get("curExp")),
        max_count=_int_or_none(data.get("maxCount")))
