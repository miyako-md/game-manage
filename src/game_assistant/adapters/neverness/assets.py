"""NTE assets and official recommendations, from explicit Tajiduo schemas.

Reference: NTEUID ba7790e, utils/sdk/tajiduo_model.py (Furniture,
House, Vehicle and TeamRecommendation). Unknown ownership is not false.
"""
import json
from typing import Any

from pydantic import BaseModel, Field

from .data_models import NtePayload
from .parse import _ERROR, _count, _http_url, _id, _object, _rows, _text, _unwrap


class NteFurniture(BaseModel):
    id: str
    name: str | None = None
    owned: bool | None = None


class NteHouse(NteFurniture):
    resident_ids: list[str] = Field(default_factory=list)
    furniture: list[NteFurniture] = Field(default_factory=list)


class NteRealestate(NtePayload):
    entries: list[NteHouse] = Field(default_factory=list)
    owned_count: int | None = None
    total: int | None = None


class NteVehicleStat(BaseModel):
    name: str | None = None
    value: str | None = None


class NteVehicleAdvancedStat(NteVehicleStat):
    maximum: str | None = None


class NteVehicleModel(BaseModel):
    id: str | None = None
    type: str | None = None


class NteVehicle(NteFurniture):
    base: list[NteVehicleStat] = Field(default_factory=list)
    advanced: list[NteVehicleAdvancedStat] = Field(default_factory=list)
    models: list[NteVehicleModel] = Field(default_factory=list)


class NteVehicles(NtePayload):
    entries: list[NteVehicle] = Field(default_factory=list)
    owned_count: int | None = None
    total: int | None = None
    show_id: str | None = None
    show_name: str | None = None


class NteTeam(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    icon_url: str | None = None
    image_urls: list[str] = Field(default_factory=list)


class NteTeams(NtePayload):
    entries: list[NteTeam] = Field(default_factory=list)


def _owned(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (str, int)):
        if value in (1, "1", "true"):
            return True
        if value in (0, "0", "false"):
            return False
    return None


def _optional_id(value: Any) -> str | None:
    return None if value in (None, "") else _id(value)


def _residents(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            raise ValueError(_ERROR) from None
    if not isinstance(value, list):
        raise ValueError(_ERROR)
    return [_id(item) for item in value]


def _safe_url(value: Any) -> str | None:
    return _http_url(_text(value))


def parse_realestate(raw: Any) -> NteRealestate:
    data = _object(_unwrap(raw))
    entries = []
    for row in _rows(data.get("detail")):
        entries.append(NteHouse(
            id=_id(row.get("id")), name=_text(row.get("name")), owned=_owned(row.get("own")),
            resident_ids=_residents(row.get("chars")),
            furniture=[NteFurniture(id=_id(item.get("id")), name=_text(item.get("name")),
                                    owned=_owned(item.get("own")))
                       for item in _rows(row.get("fdetail", []))],
        ))
    return NteRealestate(entries=entries, owned_count=_count(data.get("ownCnt")), total=_count(data.get("total")))


def parse_vehicles(raw: Any) -> NteVehicles:
    data = _object(_unwrap(raw))
    entries = []
    for row in _rows(data.get("detail")):
        entries.append(NteVehicle(
            id=_id(row.get("id")), name=_text(row.get("name")), owned=_owned(row.get("own")),
            base=[NteVehicleStat(name=_text(item.get("name")), value=_text(item.get("value")))
                  for item in _rows(row.get("base", []))],
            advanced=[NteVehicleAdvancedStat(name=_text(item.get("name")), value=_text(item.get("value")),
                                             maximum=_text(item.get("max")))
                      for item in _rows(row.get("advanced", []))],
            models=[NteVehicleModel(id=_optional_id(item.get("id")), type=_text(item.get("type")))
                    for item in _rows(row.get("models", []))],
        ))
    return NteVehicles(entries=entries, owned_count=_count(data.get("ownCnt")), total=_count(data.get("total")),
                       show_id=_optional_id(data.get("showId")), show_name=_text(data.get("showName")))


def parse_teams(raw: Any) -> NteTeams:
    entries = []
    for row in _rows(_unwrap(raw)):
        images = row.get("imgs", [])
        if not isinstance(images, list) or any(not isinstance(item, str) for item in images):
            raise ValueError(_ERROR)
        entries.append(NteTeam(
            id=_id(row.get("id")), name=_text(row.get("name")), description=_text(row.get("desc")),
            icon_url=_safe_url(row.get("icon")), image_urls=[url for item in images if (url := _safe_url(item))],
        ))
    return NteTeams(entries=entries)
