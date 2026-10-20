"""终末地看板载荷（带 schema_version，前端据此拒绝旧格式快照）。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict

from game_assistant.models import GameEvent


class EndfieldEvent(GameEvent):
    """Keep the source and imprecise-date annotations used by the calendar UI."""
    model_config = ConfigDict(extra='allow')


class EndfieldPayload(BaseModel):
    schema_version: Literal[1] = 1


class EndfieldRole(BaseModel):
    uid: str
    role_id: str
    server_id: str
    nickname: str | None = None
    level: int | None = None
    server_name: str | None = None
    channel: str | None = None
    channel_id: Literal["official", "bilibili", "unknown"] = "unknown"


class EndfieldAccount(EndfieldPayload):
    nickname: str | None = None
    level: int | None = None
    role_id: str = ""
    uid: str = ""
    server_name: str | None = None
    channel: str | None = None
    channel_id: Literal["official", "bilibili", "unknown"] = "unknown"


class EndfieldPity(BaseModel):
    # exact：连续记录中找到上一次 6★；lower_bound：至少 count 抽；unknown：没有记录
    count: int | None = None
    status: Literal["exact", "lower_bound", "unknown"] = "unknown"


class EndfieldSixStar(BaseModel):
    name: str | None = None
    pool_id: str | None = None  # 具体某一期卡池；同类卡池的抽数可能跨期累计
    pool_name: str | None = None
    obtained_at: int | None = None  # 毫秒时间戳
    pulls: int | None = None
    status: Literal["exact", "lower_bound"] = "lower_bound"


class EndfieldGachaBanner(BaseModel):
    # 同一卡池类型下的某一期（官方 poolId），只统计这一期内的记录
    pool_id: str | None = None
    name: str | None = None
    total: int = 0
    six_star: int = 0
    five_star: int = 0
    four_star: int = 0
    unknown_rarity: int = 0
    free: int = 0
    newest_at: int | None = None
    oldest_at: int | None = None


class EndfieldGachaPool(BaseModel):
    key: str
    label: str
    kind: Literal["character", "weapon"]
    total: int = 0
    six_star: int = 0
    five_star: int = 0
    four_star: int | None = None
    unknown_rarity: int | None = None
    free: int = 0
    gifts: int = 0  # 额外奖励保留在明细中，不计抽数、星级出货或保底
    unverified_records: int = 0  # 武器记录缺少可识别类型，补读核验前不混入确定统计
    since_last_six: EndfieldPity = EndfieldPity()
    history: list[EndfieldSixStar] = []
    history_total: int | None = None
    history_available: int | None = None
    history_limit: int | None = None
    history_truncated: bool | None = None
    newest_at: int | None = None
    oldest_at: int | None = None
    gaps: int = 0
    pending: bool | None = None
    last_sync_at: str | None = None
    banners: list[EndfieldGachaBanner] = []  # 由新到旧


class EndfieldGachaError(BaseModel):
    # 本轮同步里读取失败的卡池（或武器池列表），下次同步时重试
    key: str
    label: str
    message: str


class EndfieldGacha(EndfieldPayload):
    role_id: str
    total: int = 0
    complete: bool | None = None  # 未采集或旧账本缺少覆盖证据时保持未知
    pools: list[EndfieldGachaPool] = []
    errors: list[EndfieldGachaError] = []
    report: dict | None = None
