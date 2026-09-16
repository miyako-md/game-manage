"""Versioned, source-faithful Neverness to Everness dashboard payloads."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from game_assistant.models import StaminaInfo


class NtePayload(BaseModel):
    schema_version: Literal[1] = 1


class NteAccount(NtePayload):
    nickname: str | None = None
    level: int | None = None
    role_id: str = ""
    server_name: str | None = None
    world_level: int | None = None
    tycoon_level: int | None = None
    active_days: int | None = None
    character_count: int | None = None
    achievement_count: int | None = None
    achievement_total: int | None = None
    house_count: int | None = None
    house_total: int | None = None
    vehicle_count: int | None = None
    vehicle_total: int | None = None


class NteStamina(StaminaInfo):
    schema_version: Literal[1] = 1
    city_current: int | None = None
    city_maximum: int | None = None
    daily_activity: int | None = None
    weekly_remaining: int | None = None


class NteWeapon(BaseModel):
    name: str | None = None
    level: int | None = None
    quality: str | None = None
    mix_level: int | None = None


class NteProperty(BaseModel):
    name: str
    value: str


class NteSkill(BaseModel):
    name: str | None = None
    level: int | None = None


class NteRole(BaseModel):
    id: str
    name: str | None = None
    level: int | None = None
    quality: str | None = None
    element: str | None = None
    awaken_level: int | None = None
    mix_level: int | None = None
    affinity_exp: int | None = None
    icon_url: str | None = None
    weapon: NteWeapon | None = None
    properties: list[NteProperty] = Field(default_factory=list)
    skills: list[NteSkill] = Field(default_factory=list)
    city_skills: list[NteSkill] = Field(default_factory=list)


class NteRoles(NtePayload):
    entries: list[NteRole] = Field(default_factory=list)


class NteCountEntry(BaseModel):
    id: str
    name: str | None = None
    current: int | None = None
    total: int | None = None


class NteProgress(NtePayload):
    completed: int | None = None
    total: int | None = None
    bronze: int | None = None
    silver: int | None = None
    gold: int | None = None
    categories: list[NteCountEntry] = Field(default_factory=list)


class NteArea(NteCountEntry):
    details: list[NteCountEntry] = Field(default_factory=list)


class NteExploration(NtePayload):
    areas: list[NteArea] = Field(default_factory=list)


class NteGachaDetail(BaseModel):
    item_id: str
    name: str
    pity: int | None = None
    obtained_at: datetime | None = None
    lucky_type: int | None = None


class NteGachaPool(BaseModel):
    name: str | None = None
    total_draws: int | None = None
    s_count: int | None = None
    average: float | None = None
    percentile: float | None = None
    guarantee: int | None = None
    details: list[NteGachaDetail] = Field(default_factory=list)


class NteGacha(NtePayload):
    role_id: str = ""
    nickname: str | None = None
    luck_title: str | None = None
    luck_type: int | None = None
    total_draws: int | None = None
    total_s: int | None = None
    pools: list[NteGachaPool] = Field(default_factory=list)


class NteRecordCard(BaseModel):
    game_name: str | None = None
    role_id: str
    nickname: str | None = None
    level: int | None = None
    server_name: str | None = None
    url: str | None = None


class NteRecord(NtePayload):
    cards: list[NteRecordCard] = Field(default_factory=list)
