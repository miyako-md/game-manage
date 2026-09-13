from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class Capability(str, Enum):
    ACCOUNT = "account"
    STAMINA = "stamina"
    ACTIVITY = "activity"
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


class ActivityItem(BaseModel):
    title: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    url: str | None = None


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
