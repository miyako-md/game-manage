"""Versioned Wuwa payloads; source objects preserve nulls and evolving fields."""
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class CollectionItem(BaseModel):
    model_config = ConfigDict(extra='allow', strict=True)
    id: int | None = None
    name: str | None = None
    box_name: str | None = None
    num: int | None = None


class BaseProfile(BaseModel):
    model_config = ConfigDict(extra='allow', strict=True)
    creat_time: int | None = None
    world_level: int | None = None
    active_days: int | None = None
    achievement_count: int | None = None
    achievement_star: int | None = None
    big_count: int | None = None
    small_count: int | None = None
    box_list: list[CollectionItem | None] | None = None
    treasure_box_list: list[CollectionItem | None] | None = None
    phantom_box_list: list[CollectionItem | None] | None = None


class SourceResult(BaseModel):
    state: str = 'ok'
    data: dict[str, Any] | None = None
    fetched_at: str | None = None
    source: str
    error: str | None = None


class WuwaPayload(BaseModel):
    schema_version: int = 1
    role_id: str
    server_id: str
    provenance: dict[str, Any] = Field(default_factory=dict)


class CombatPayload(WuwaPayload):
    tower: SourceResult
    hologram: SourceResult
    slash: SourceResult


class ActivitiesPayload(WuwaPayload):
    sections: dict[str, Any]


class ResourcesPayload(WuwaPayload):
    periods: dict[str, list[dict]]
    current: dict | None = None
    error: str | None = None
