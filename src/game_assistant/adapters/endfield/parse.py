"""按参考项目记录的字段解析绑定列表与寻访记录，不做递归猜键。"""
from typing import Any

from game_assistant.adapters.endfield.channels import binding_channel
from game_assistant.adapters.endfield.data_models import EndfieldAccount, EndfieldRole
from game_assistant.adapters.endfield.endpoints import BINDING_APP_CODE, OFFICIAL_SERVER_ID

_ERROR = "终末地数据格式无效，请刷新重试"
NO_OFFICIAL_ROLE = "该账号未绑定终末地官服角色，请先在游戏内创建角色"


class RoleChangedError(ValueError):
    """登录后绑定角色变了：需要重新登录，不能把两个角色的数据混在一起。"""


def _text(value: Any) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _flag(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _rows(value: Any) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(_ERROR)
    return value


def select_role(data: Any, channel: str = "official", *, expected_uid: str = "",
                expected_role_id: str = "", expected_server_id: str = "") -> EndfieldRole:
    """只从可信渠道和国服中选角色；保存过身份时忽略上游默认角色的变化。"""
    if channel not in ("official", "bilibili"):
        raise ValueError("不支持的终末地渠道")
    if not isinstance(data, dict):
        raise ValueError(_ERROR)
    apps = [app for app in _rows(data.get("list", [])) if app.get("appCode") == BINDING_APP_CODE]
    candidates = []
    pinned = bool(expected_uid or expected_role_id or expected_server_id)
    for app in apps:
        for account in _rows(app.get("bindingList", [])):
            uid = _text(account.get("uid"))
            if (not uid or account.get("isDeleted") is True or account.get("isDelete") is True
                    or account.get("isBanned") is True or binding_channel(account) != channel):
                continue
            for role in _rows(account.get("roles", [])):
                role_id, server_id = _text(role.get("roleId")), _text(role.get("serverId"))
                if (not role_id or server_id != OFFICIAL_SERVER_ID or role.get("isBanned") is True
                        or role.get("isDeleted") is True or role.get("isDelete") is True):
                    continue
                if ((expected_uid and uid != expected_uid)
                        or (expected_role_id and role_id != expected_role_id)
                        or (expected_server_id and server_id != expected_server_id)):
                    continue
                rank = (role.get("isDefault") is not True, account.get("isDefault") is not True)
                candidates.append((rank, EndfieldRole(
                    uid=uid, role_id=role_id, server_id=server_id, nickname=_text(role.get("nickName")),
                    level=_count(role.get("level")), server_name=_text(role.get("serverName")),
                    channel=_text(account.get("channelName")), channel_id=channel)))
    if not candidates:
        if pinned:
            raise RoleChangedError("终末地绑定角色已变化，请在「社区账号」重新登录")
        if channel == "bilibili":
            raise ValueError("该鹰角通行证未绑定终末地B服角色，请先在鹰角账号中心选择bilibili服，填写游戏UID并完成游戏内邮件验证")
        raise ValueError(NO_OFFICIAL_ROLE)
    return min(candidates, key=lambda item: item[0])[1]


def select_official_role(data: Any) -> EndfieldRole:
    """兼容已有官服调用。"""
    return select_role(data)


def parse_account(data: Any, expected_role_id: str = "", *, channel: str = "official",
                  expected_uid: str = "", expected_server_id: str = "") -> EndfieldAccount:
    role = select_role(data, channel, expected_uid=expected_uid, expected_role_id=expected_role_id,
                       expected_server_id=expected_server_id)
    return EndfieldAccount(nickname=role.nickname, level=role.level, role_id=role.role_id,
                           uid=role.uid, server_name=role.server_name, channel=role.channel,
                           channel_id=role.channel_id)


def _timestamp_ms(value: Any) -> int | None:
    number = _count(value)
    if number is None:
        return None
    if number > 10**12:
        return number
    return number * 1000 if number > 10**9 else None


def normalize_record(raw: dict, kind: str) -> dict:
    """单条寻访记录 → 账本字段。seqId 必须是数字（排序与去重依赖它）。"""
    if not isinstance(raw, dict):
        raise ValueError(_ERROR)
    seq = _text(raw.get("seqId"))
    if not seq or not seq.isdigit():
        raise ValueError(_ERROR)
    prefix = "char" if kind == "character" else "weapon"
    rarity = _count(raw.get("rarity"))
    record_kind = _text(raw.get("kind"))
    reward = bool(record_kind and record_kind.startswith("gift"))
    return {
        "seq_id": int(seq), "kind": kind,
        "record_kind": record_kind, "pool_version": _count(raw.get("poolVersion")),
        "reward_label": _text(raw.get("giftRewardLabel")),
        "item_id": _text(raw.get(f"{prefix}Id")),
        "name": (_text(raw.get("nameText")) if reward else _text(raw.get(f"{prefix}Name")))
                or _text(raw.get("nameText")) or _text(raw.get(f"{prefix}Name")),
        "rarity": rarity if rarity is not None and rarity <= 6 else None,
        "pool_id": _text(raw.get("poolId")), "pool_name": _text(raw.get("poolName")),
        "is_free": _flag(raw.get("isFree")), "is_new": _flag(raw.get("isNew")),
        "weapon_type": _text(raw.get("weaponType")) if kind == "weapon" else None,
        "gacha_ts": _timestamp_ms(raw.get("gachaTs")),
    }


def record_page(data: Any, kind: str) -> tuple[list[dict], bool]:
    """record/char、record/weapon 的 data → (记录列表, 是否还有下一页)。"""
    if not isinstance(data, dict):
        raise ValueError(_ERROR)
    if "list" not in data:
        raise ValueError(_ERROR)
    rows = [normalize_record(row, kind) for row in _rows(data["list"] or [])]
    # 参考实现按真值读取 hasMore（缺省即没有后续）；只接受布尔、0/1 和缺省，其他类型仍视为格式无效。
    has_more = data.get("hasMore")
    if has_more is None or (has_more in (0, 1) and not isinstance(has_more, float)):
        return rows, bool(has_more)
    raise ValueError(_ERROR)


def weapon_pools(data: Any) -> list[tuple[str, str]]:
    """record/weapon/pool 的 data → [(pool_id, pool_name)]；参考项目见过列表与 {list} 两种包装。"""
    if isinstance(data, dict) and "list" not in data:
        raise ValueError(_ERROR)
    rows = data["list"] if isinstance(data, dict) else data
    pools, seen = [], set()
    for row in _rows(rows):
        pool_id = _text(row.get("poolId"))
        if not pool_id:
            raise ValueError(_ERROR)
        if pool_id not in seen:
            pools.append((pool_id, _text(row.get("poolName")) or pool_id))
            seen.add(pool_id)
    return pools
