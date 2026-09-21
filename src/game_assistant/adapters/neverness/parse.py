"""Normalize the documented NTE endpoint schemas without recursive key guessing."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import math
import re
from typing import Any
from urllib.parse import urlsplit

from game_assistant.event_calendar import BEIJING_TZ as _BEIJING

from .data_models import (
    NteAccount, NteArea, NteCountEntry, NteExploration, NteGacha,
    NteGachaDetail, NteGachaPool, NteProgress, NteProperty, NteRecord,
    NteRecordCard, NteRole, NteRoles, NteSkill, NteStamina, NteWeapon,
)

_ERROR = "异环数据格式无效，请刷新重试"
_QUALITY = dict(zip(
    ("ITEM_QUALITY_ORANGE", "ITEM_QUALITY_PURPLE", "ITEM_QUALITY_BLUE", "ITEM_QUALITY_GREEN", "ITEM_QUALITY_WHITE"),
    ("S", "A", "B", "C", "N"),
))
_ELEMENT = {f"CHARACTER_ELEMENT_TYPE_{key}": label for key, label in (
    ("PSYCHE", "魂"), ("COSMOS", "光"), ("NATURE", "灵"),
    ("INCANTATION", "咒"), ("CHAOS", "暗"), ("LAKSHANA", "相"),
)}


def _unwrap(raw: Any) -> Any:
    # The client can return serialized `data` at successive transport layers.
    # Only that explicit wrapper is followed; arbitrary nested keys never are.
    for _ in range(16):
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (ValueError, TypeError):
                raise ValueError(_ERROR) from None
        elif isinstance(raw, dict) and "data" in raw:
            if "code" in raw and raw["code"] not in (0, "0", 200, "200"):
                raise ValueError(_ERROR)
            raw = raw["data"]
        else:
            return raw
    raise ValueError(_ERROR)


def _object(value: Any) -> dict:
    if not isinstance(value, dict):
        raise ValueError(_ERROR)
    return value


def _rows(value: Any) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(_ERROR)
    return value


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _id(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(_ERROR)
    result = str(value).strip()
    if not result:
        raise ValueError(_ERROR)
    return result


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = Decimal(str(value))
        if number.is_finite() and number >= 0 and number == number.to_integral_value():
            return int(number)
    except (InvalidOperation, ValueError, OverflowError):
        pass
    return None


def _identity(data: dict, expected_role_id: str) -> str:
    role_id = _id(data["roleid"]) if data.get("roleid") not in (None, "") else ""
    if role_id and expected_role_id and role_id != str(expected_role_id):
        raise ValueError("异环返回角色与当前账号不一致，请重新登录")
    return role_id


def _home(raw: Any, expected_role_id: str) -> tuple[dict, str]:
    data = _object(_unwrap(raw))
    if not any(key in data for key in ("roleid", "rolename", "lev", "staminaValue", "staminaMaxValue")):
        raise ValueError(_ERROR)
    return data, _identity(data, expected_role_id)


def _optional_object(data: dict, key: str) -> dict:
    return {} if data.get(key) is None else _object(data[key])


def parse_account(raw: Any, expected_role_id: str = "") -> NteAccount:
    data, role_id = _home(raw, expected_role_id)
    achievement = _optional_object(data, "achieveProgress")
    house = _optional_object(data, "realestate")
    vehicle = _optional_object(data, "vehicle")
    return NteAccount(
        role_id=role_id, nickname=_text(data.get("rolename")), level=_count(data.get("lev")),
        server_name=_text(data.get("servername")), world_level=_count(data.get("worldlevel")),
        tycoon_level=_count(data.get("tycoonLevel")), active_days=_count(data.get("roleloginDays")),
        character_count=_count(data.get("charidCnt")), achievement_count=_count(achievement.get("achievementCnt")),
        achievement_total=_count(achievement.get("total")), house_count=_count(house.get("ownCnt")),
        house_total=_count(house.get("total")), vehicle_count=_count(vehicle.get("ownCnt")),
        vehicle_total=_count(vehicle.get("total")),
    )


def parse_stamina(raw: Any, now: datetime, expected_role_id: str = "") -> NteStamina:
    data, _ = _home(raw, expected_role_id)
    current, maximum = _count(data.get("staminaValue")), _count(data.get("staminaMaxValue"))
    if current is None or maximum is None or maximum <= 0:
        raise ValueError("异环体力数据缺失或无效，请刷新重试")
    return NteStamina(
        current=current, maximum=maximum, updated_at=now, expected_full_at=None,
        city_current=_count(data.get("citystaminaValue")), city_maximum=_count(data.get("citystaminaMaxValue")),
        daily_activity=_count(data.get("dayvalue")), weekly_remaining=_count(data.get("weekcopiesremainCnt")),
    )


def _label(value: Any, labels: dict[str, str]) -> str | None:
    value = _text(value)
    return labels.get(value, value)


def _skills(value: Any) -> list[NteSkill]:
    return [NteSkill(name=_text(row.get("name")), level=_count(row.get("level"))) for row in _rows(value)]


def parse_roles(raw: Any) -> NteRoles:
    entries = []
    for row in _rows(_unwrap(raw)):
        role_id = _id(row.get("id"))
        fork = _optional_object(row, "fork")
        weapon = NteWeapon(
            name=_text(fork.get("name")), level=_count(fork.get("alev")),
            quality=_label(fork.get("quality"), _QUALITY), mix_level=_count(fork.get("slev")),
        ) if fork.get("id") else None
        properties = []
        for prop in _rows(row.get("properties", [])):
            name, value = _text(prop.get("name")), _text(prop.get("value"))
            if name is not None and value is not None:
                properties.append(NteProperty(name=name, value=value))
        icon = ("https://webstatic.tajiduo.com/bbs/yh-game-records-web-source/character/detail/"
                f"{role_id}.png") if re.fullmatch(r"[A-Za-z0-9_-]+", role_id) else None
        entries.append(NteRole(
            id=role_id, name=_text(row.get("name")), level=_count(row.get("alev")),
            quality=_label(row.get("quality"), _QUALITY), element=_label(row.get("elementType"), _ELEMENT),
            awaken_level=_count(row.get("awakenLev")), mix_level=_count(row.get("slev")),
            affinity_exp=_count(row.get("likeabilitylev")), icon_url=icon, weapon=weapon,
            properties=properties, skills=_skills(row.get("skills", [])), city_skills=_skills(row.get("citySkills", [])),
        ))
    return NteRoles(entries=entries)


def _count_entry(row: dict) -> NteCountEntry:
    return NteCountEntry(id=_id(row.get("id")), name=_text(row.get("name")),
                         current=_count(row.get("progress")), total=_count(row.get("total")))


def parse_progress(raw: Any) -> NteProgress:
    data = _object(_unwrap(raw))
    if not any(key in data for key in ("achievementCnt", "total", "bronzeUmdCnt", "silverUmdCnt", "goldUmdCnt", "detail")):
        raise ValueError(_ERROR)
    return NteProgress(
        completed=_count(data.get("achievementCnt")), total=_count(data.get("total")),
        bronze=_count(data.get("bronzeUmdCnt")), silver=_count(data.get("silverUmdCnt")), gold=_count(data.get("goldUmdCnt")),
        categories=[_count_entry(row) for row in _rows(data.get("detail", []))],
    )


def parse_exploration(raw: Any) -> NteExploration:
    return NteExploration(areas=[NteArea(
        **_count_entry(row).model_dump(), details=[_count_entry(detail) for detail in _rows(row.get("detail", []))],
    ) for row in _rows(_unwrap(raw))])


def _obtained_at(row: dict) -> datetime | None:
    timestamp = _number(row.get("timeStamp"))
    if timestamp is not None:
        try:
            return datetime.fromtimestamp(timestamp / 1000, tz=_BEIJING)
        except (OverflowError, ValueError, OSError):
            pass
    date_text = _text(row.get("time"))
    if date_text:
        try:
            date = datetime.fromisoformat(date_text)
            return date.replace(tzinfo=_BEIJING) if date.tzinfo is None else date.astimezone(_BEIJING)
        except ValueError:
            pass
    return None


def _known_sum(values: list[int | None]) -> int | None:
    # No pools or partially absent pool counts cannot support an aggregate.
    return sum(values) if values and all(value is not None for value in values) else None


def parse_gacha(raw: Any, names: dict[str, str] | None = None, expected_role_id: str = "") -> NteGacha:
    data = _object(_unwrap(raw))
    role_id = _identity(data, expected_role_id)
    pools = []
    for row in _rows(data.get("gachaDetails")):
        if _text(row.get("tab")) is None:
            raise ValueError(_ERROR)
        details = []
        for detail in _rows(row.get("details", [])):
            item_id = _id(detail.get("charid"))
            details.append(NteGachaDetail(
                item_id=item_id, name=_text((names or {}).get(item_id)) or f"角色/弧盘 {item_id}",
                pity=_count(detail.get("rareCount")), obtained_at=_obtained_at(detail),
                lucky_type=_count(detail.get("luckyType")),
            ))
        percentile_raw = row.get("playerOver")
        if isinstance(percentile_raw, str):
            percentile_raw = percentile_raw.strip().removesuffix("%")
        percentile = _number(percentile_raw)
        pools.append(NteGachaPool(
            name=_text(row.get("tab")), total_draws=_count(row.get("drawCount")), s_count=_count(row.get("rareCount")),
            average=_number(row.get("average")), percentile=percentile if percentile is not None and percentile <= 100 else None,
            guarantee=_count(row.get("m")), details=details,
        ))
    return NteGacha(role_id=role_id, nickname=_text(data.get("rolename")),
                    luck_title=_text(data.get("luckTitle")), luck_type=_count(data.get("luckType")),
                    total_draws=_known_sum([pool.total_draws for pool in pools]),
                    total_s=_known_sum([pool.s_count for pool in pools]), pools=pools)


def _http_url(value: Any) -> str | None:
    if not isinstance(value, str) or any(char.isspace() or ord(char) < 32 for char in value) or "\\" in value:
        return None
    try:
        url = urlsplit(value)
        if (url.scheme in ("http", "https") and url.hostname
                and not url.username and not url.password):
            _ = url.port
            return value
    except ValueError:
        pass
    return None


def parse_record(raw: Any, expected_role_id: str = "") -> NteRecord:
    cards = []
    for row in _rows(_unwrap(raw)):
        game_id = _count(row.get("gameId"))
        if game_id is None:
            raise ValueError(_ERROR)
        if game_id != 1289:
            continue
        if row.get("bindRoleInfo") is None:
            continue  # An unbound community card has no character to display.
        role = _object(row["bindRoleInfo"])
        role_id = _id(role.get("roleId"))
        if "gameId" in role and _count(role["gameId"]) != 1289:
            continue
        if expected_role_id and role_id != str(expected_role_id):
            continue
        cards.append(NteRecordCard(
            game_name=_text(row.get("gameName")), role_id=role_id,
            nickname=_text(role.get("roleName")), level=_count(role.get("lev")),
            server_name=_text(role.get("serverName")), url=_http_url(row.get("link")),
        ))
    return NteRecord(cards=cards)
