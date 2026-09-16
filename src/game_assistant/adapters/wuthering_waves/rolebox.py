"""库街区 roleBox 数据解析（探索度 + 数据坞）。

roleBox 响应的 data 字段是 JSON 字符串（实测形状，2026-09-13），
rolebox_client.post 已二次解析为 dict；本模块再兜底兼容信封/字符串形状
（role.parse_widget_energy / widget._data 同款防御式写法）。

exploreIndex data 实测结构（2026-09-13 完整响应校准）：
  detectionInfoList[]（约 199 项：detectionName/levelName/level 等，残象探寻）；
  exploreList[]（4 组：瑝珑/黑海岸/黎那汐塔/罗伊冰原）——每组含
  country{countryName,...}、countryProgress（数字，如 67.06）、
  areaInfoList[]（areaName/areaProgress/itemList[]{name,progress,type}，
  itemList 明细不进模型）。
calabashData data 实测形状：
  level/baseCatch("20%")/catchQuality/curExp/maxCount/phantomList[]。
roleData data 实测形状：
  roleList[]（约 46 项：roleId/roleName/level/attributeName/breach/
  chainUnlockNum/starLevel/weaponTypeName/roleIconUrl/isMainRole/roleSkin 等）
  + showToGuest。
"""
import json as _json
from .detail_parse import normalize
from collections import Counter

from game_assistant.models import (
    CalabashData, CountryGroup, DetectionSummary, ExplorationData, AreaSummary,
    RoleEntry,
)


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
    """exploreIndex 响应 → ExplorationData（实测结构见模块 docstring）。

    detectionInfoList 按级计数：by_level = {"轻波级": n, "巨浪级": n, ...}
    （levelName 缺失时回退 "等级{level}"），total 为残象已收录数（列表长度）。
    countryProgress / areaProgress 可能是数字或百分比字符串，统一转 float|None。
    """
    data = _data(raw)
    by_level = Counter()
    for d in data.get("detectionInfoList") or []:
        if not isinstance(d, dict):
            continue
        key = d.get("levelName") or f"等级{d.get('level')}"
        by_level[str(key)] += 1
    groups = []
    for g in data.get("exploreList") or []:
        if not isinstance(g, dict):
            continue
        country = g.get("country") or {}
        areas = [AreaSummary(name=str(a.get("areaName") or ""),
                             progress=_float_or_none(a.get("areaProgress")))
                 for a in g.get("areaInfoList") or [] if isinstance(a, dict)]
        groups.append(CountryGroup(
            name=str(country.get("countryName") or ""),
            progress=_float_or_none(g.get("countryProgress")),
            areas=areas))
    return ExplorationData(
        detections=DetectionSummary(total=sum(by_level.values()),
                                    by_level=dict(by_level)),
        country_groups=groups)


def parse_calabash_data(raw) -> CalabashData:
    """calabashData 响应 → 数据坞信息（phantomList 明细不展示，仅汇总字段）。"""
    data = _data(raw)
    return CalabashData(
        level=_int_or_none(data.get("level")),
        base_catch=_str_or_none(data.get("baseCatch")),
        catch_quality=_int_or_none(data.get("catchQuality")),
        cur_exp=_int_or_none(data.get("curExp")),
        max_count=_int_or_none(data.get("maxCount")))


def parse_role_data(raw) -> list[RoleEntry]:
    """roleData 响应 → 角色练度墙列表。

    roleList 遍历（非 dict 项跳过），按 level 降序 + chain 降序排序
    （sorted 稳定，同级同链保持接口原序）；roleSkin 等未消费字段忽略。
    """
    data = _data(raw)
    roles = [RoleEntry(
        extra=normalize(r),
        role_id=_int_or_none(r.get("roleId")),
        name=str(r.get("roleName") or ""),
        level=_int_or_none(r.get("level")),
        attribute=_str_or_none(r.get("attributeName")),
        breach=_int_or_none(r.get("breach")),
        chain=_int_or_none(r.get("chainUnlockNum")),
        star_level=_int_or_none(r.get("starLevel")),
        weapon=_str_or_none(r.get("weaponTypeName")),
        icon_url=normalize(r).get('role_icon_url'),
        is_main=bool(r.get("isMainRole", False)),
    ) for r in data.get("roleList") or [] if isinstance(r, dict)]
    roles.sort(key=lambda e: (-(e.level or 0), -(e.chain or 0)))
    return roles
