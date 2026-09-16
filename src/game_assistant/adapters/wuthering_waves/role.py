import json as _j
from datetime import datetime, timedelta, timezone

from game_assistant.models import AccountInfo, StaminaInfo

REGEN_MINUTES_PER_POINT = 6
# 北京时间（UTC+8）：库街区服务器按中国时区运营，后续展示换算可用
BEIJING_TZ = timezone(timedelta(hours=8))


def _int_or_none(v):
    # 实测 gameLevel 等字段是字符串（如 "80"），统一安全转 int
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_role_list(raw: dict) -> AccountInfo:
    """POST /gamer/role/list 响应 → 账号信息。

    data 是数组，取第一个（默认角色，isDefault=true）。实测字段（2026-09-13）：
    roleId/serverId/roleName/gameLevel（字符串）/serverName/activeDay/
    achievementCount/roleNum。roleId/serverId 存入 extra 供体力查询复用。
    """
    rows = (raw or {}).get("data") or []
    r = rows[0] if rows else {}
    return AccountInfo(
        nickname=r.get("roleName"), level=_int_or_none(r.get("gameLevel")),
        extra={"role_id": r.get("roleId"), "server_id": r.get("serverId"),
               "server_name": r.get("serverName"), "active_day": r.get("activeDay"),
               "achievement_count": r.get("achievementCount"),
               "role_num": r.get("roleNum")})


def parse_widget_energy(raw: dict, now: datetime) -> StaminaInfo:
    """POST /gamer/widget/game3/getData 响应 → 体力（结晶波片）。

    data 可能是 dict 或 JSON 字符串（实测见过字符串形状，做 json.loads 兜底）；
    data.energyData = {name/cur/total/refreshTimeStamp/expireTimeStamp/status}。
    refreshTimeStamp 语义实测不确定（样例恒为 0），满时间统一按
    6 分钟/点公式推算，不使用 refreshTimeStamp。
    """
    data = raw.get("data")
    if isinstance(data, str):
        data = _j.loads(data)
    energy = (data or {}).get("energyData") or {}
    current = _int_or_none(energy.get("cur")) or 0
    maximum = _int_or_none(energy.get("total")) or 0
    expected_full_at = None
    if maximum > current:
        expected_full_at = now + timedelta(
            minutes=REGEN_MINUTES_PER_POINT * (maximum - current))
    return StaminaInfo(current=current, maximum=maximum,
                       expected_full_at=expected_full_at, updated_at=now)


def parse_base_energy(data: dict, now: datetime) -> StaminaInfo:
    """Read refreshed roleBox energy; unavailable values must not become zero."""
    current, maximum = _int_or_none(data.get('energy')), _int_or_none(data.get('maxEnergy'))
    if current is None or maximum is None or current < 0 or maximum <= 0:
        raise ValueError('角色面板未返回有效体力')
    full = now + timedelta(minutes=REGEN_MINUTES_PER_POINT * (maximum - current)) if maximum > current else None
    return StaminaInfo(current=current, maximum=maximum, expected_full_at=full, updated_at=now)
