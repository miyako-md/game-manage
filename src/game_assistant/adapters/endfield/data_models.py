"""终末地看板载荷（带 schema_version，前端据此拒绝旧格式快照）。"""
from typing import Literal

from pydantic import BaseModel


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


class EndfieldAccount(EndfieldPayload):
    nickname: str | None = None
    level: int | None = None
    role_id: str = ""
    uid: str = ""
    server_name: str | None = None
    channel: str | None = None


class EndfieldPity(BaseModel):
    # exact：连续记录中找到上一次 6★；lower_bound：至少 count 抽；unknown：没有记录
    count: int | None = None
    status: Literal["exact", "lower_bound", "unknown"] = "unknown"


class EndfieldSixStar(BaseModel):
    name: str | None = None
    pool_name: str | None = None
    obtained_at: int | None = None  # 毫秒时间戳
    pulls: int | None = None
    status: Literal["exact", "lower_bound"] = "lower_bound"


class EndfieldGachaPool(BaseModel):
    key: str
    label: str
    kind: Literal["character", "weapon"]
    total: int = 0
    six_star: int = 0
    five_star: int = 0
    free: int = 0
    since_last_six: EndfieldPity = EndfieldPity()
    history: list[EndfieldSixStar] = []
    newest_at: int | None = None
    oldest_at: int | None = None
    gaps: int = 0
    pending: bool = False
    last_sync_at: str | None = None


class EndfieldGacha(EndfieldPayload):
    role_id: str
    total: int = 0
    complete: bool = True
    pools: list[EndfieldGachaPool] = []
