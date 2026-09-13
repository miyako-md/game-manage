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
    EXPLORATION = "exploration"
    CALABASH = "calabash"
    ROLES = "roles"


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


class DetectionSummary(BaseModel):
    # roleBox exploreIndex detectionInfoList 汇总：残象探寻已收录条目按级计数
    # （by_level 如 {"轻波级": n, "巨浪级": n, "怒涛级": n, "海啸级": n}）
    total: int = 0
    by_level: dict = {}


class AreaSummary(BaseModel):
    # 国家分组下的地区（areaInfoList 单条）：名称 + 探索度百分比；
    # itemList 明细不进模型（M4 再说）
    name: str
    progress: float | None = None


class CountryGroup(BaseModel):
    # roleBox exploreIndex exploreList 单组：country.countryName + countryProgress
    # （数字或百分比字符串，统一转 float）+ 组内地区列表
    name: str
    progress: float | None = None
    areas: list[AreaSummary] = []


class ExplorationData(BaseModel):
    # roleBox exploreIndex（2026-09-13 实测结构）：data.detectionInfoList（199 项）
    # + data.exploreList（4 组：瑝珑/黑海岸/黎那汐塔/罗伊冰原）+ data.open
    detections: DetectionSummary = DetectionSummary()
    country_groups: list[CountryGroup] = []


class RoleEntry(BaseModel):
    # roleBox roleData roleList 单项（角色练度墙）：等级/命链/突破/属性/武器等
    role_id: int | None = None
    name: str = ""
    level: int | None = None
    attribute: str | None = None
    breach: int | None = None
    chain: int | None = None
    star_level: int | None = None
    weapon: str | None = None
    icon_url: str | None = None
    is_main: bool = False


class CalabashData(BaseModel):
    # roleBox calabashData（数据坞）
    level: int | None = None
    base_catch: str | None = None  # 如 "20%"
    catch_quality: int | None = None
    cur_exp: int | None = None
    max_count: int | None = None


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
