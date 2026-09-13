from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class Capability(str, Enum):
    ACCOUNT = "account"
    STAMINA = "stamina"
    ACTIVITY = "activity"
    PROGRESS = "progress"
    ANNOUNCEMENT = "announcement"
    NEWS = "news"
    MATCH = "match"


class StaminaInfo(BaseModel):
    current: int
    maximum: int
    expected_full_at: datetime | None = None
    updated_at: datetime


class AccountInfo(BaseModel):
    nickname: str | None = None
    level: int | None = None
    extra: dict = {}


class CoreReward(BaseModel):
    name: str
    cur: int = 0
    total: int = 0
    status: int = 0


class VersionActivity(BaseModel):
    # 版本活动（widget activityData）：当前主推活动的名称/截止/核心奖励进度
    title: str
    end_at: datetime | None = None
    enabled: bool = True
    core_rewards: list[CoreReward] = []


class ProgressItem(BaseModel):
    # 周期进度（深塔/海墟/周本/千道门扉/终焉矩阵/周度游历/活跃度/结晶单质/电台等）
    name: str
    cur: int = 0
    total: int = 0
    refresh_at: datetime | None = None
    status: int = 0


class AnnouncementItem(BaseModel):
    title: str
    published_at: datetime | None = None
    url: str | None = None
    summary: str = ""


class MatchSummary(BaseModel):
    match_id: str
    queue_id: int | None = None
    mode: str = ""
    start_at: datetime | None = None
    duration_seconds: int | None = None
    win: bool | None = None
    champion_id: int | None = None
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None


class FetchResult(BaseModel):
    ok: bool
    payload: Any = None
    error: str | None = None
