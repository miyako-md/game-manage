"""森空岛响应转为界面能展示的安全、固定字段。"""
from datetime import datetime, timezone


def obj(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError('expected object')
    return value


def rows(value):
    if value is None:
        return []
    if not isinstance(value, list) or any(item is not None and not isinstance(item, dict) for item in value):
        raise ValueError('expected object list')
    return [item for item in value if item is not None]


def number(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError('expected number')
    parsed = int(value)
    if isinstance(value, float) and value != parsed:
        raise ValueError('expected integer')
    return parsed


def flag(value):
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError('expected boolean')
    return value


def value(value):
    if isinstance(value, dict):
        return value.get("value") or value.get("key")
    return value


def _utc_ts(value):
    val = number(value)
    if val is None or val <= 0:
        return None
    try:
        return datetime.fromtimestamp(val / (1000 if val > 10**11 else 1), timezone.utc).isoformat()
    except (OverflowError, ValueError, OSError):
        return None


def parse_roles(data: dict) -> list[dict]:
    found = []
    for app in rows(data.get("list")):
        if app.get("appCode") != "endfield":
            continue
        for binding in rows(app.get("bindingList")):
            if binding.get("isDelete"):
                continue
            roles = rows(binding.get("roles"))
            for role in roles:
                if role.get("isBanned"):
                    continue
                role_id, server_id = role.get("roleId"), role.get("serverId")
                if role_id is None or server_id is None:
                    continue
                found.append({"role_id": str(role_id), "server_id": str(server_id),
                              "nickname": str(role.get("nickname") or binding.get("nickName") or "终末地角色")})
    return found


def parse_user_id(data: dict) -> str:
    user_id = obj(data.get("user")).get("id")
    return str(user_id) if user_id is not None and str(user_id) else ""


def _equipment(char: dict) -> list[dict]:
    out = []
    for slot in ("bodyEquip", "armEquip", "firstAccessory", "secondAccessory"):
        equipped = obj(char.get(slot))
        if not equipped:
            continue
        item = obj(equipped.get("equipData"))
        out.append({"slot": slot, "id": str(equipped.get("equipId") or item.get("id") or ""),
                    "name": item.get("name"), "rarity": value(item.get("rarity")),
                    "level": value(item.get("level")), "icon_url": item.get("iconUrl")})
    return out


def parse_operator(char: dict) -> dict:
    char = obj(char)
    info = obj(char.get("charData"))
    weapon = obj(char.get("weapon"))
    weapon_data = obj(weapon.get("weaponData"))
    gem = obj(weapon.get('gem'))
    gem_data = obj(gem.get('gemData'))
    user_skills = obj(char.get("userSkills"))
    skills = []
    for skill in rows(info.get("skills")):
        skill_id = str(skill.get("id") or "")
        skills.append({"id": skill_id, "name": skill.get("name"),
                       "level": number(obj(user_skills.get(skill_id)).get("level")),
                       "icon_url": skill.get("iconUrl")})
    return {"id": str(char.get("id") or info.get("id") or ""), "name": info.get("name"),
            "level": number(char.get("level")), "rarity": value(info.get("rarity")),
            "potential": number(char.get("potentialLevel")), "evolve_phase": number(char.get("evolvePhase")),
            "profession": value(info.get("profession")), "property": value(info.get("property")),
            "avatar_url": info.get("avatarSqUrl") or info.get("avatarRtUrl"),
            "weapon": {"id": weapon_data.get("id"), "name": weapon_data.get("name"),
                       "level": number(weapon.get("level")), "refine_level": number(weapon.get("refineLevel")),
                       "breakthrough_level": number(weapon.get('breakthroughLevel')),
                       "rarity": value(weapon_data.get("rarity")), "icon_url": weapon_data.get("iconUrl"),
                       "gem": {'name': gem_data.get('name'), 'icon_url': gem_data.get('icon'),
                               'terms': [{'name': term.get('name'), 'cost': number(term.get('cost'))}
                                         for term in rows(gem.get('terms'))]} if gem else None}
                      if weapon_data else None,
            "equipment": _equipment(char), "skills": skills}


def parse_card(detail: dict, *, fetched_at: str) -> dict:
    base = obj(detail.get("base"))
    dungeon = obj(detail.get("dungeon"))
    daily = obj(detail.get("dailyMission"))
    weekly = obj(detail.get("weeklyMission"))
    bp = obj(detail.get("bpSystem"))
    stamina = {"current": number(dungeon.get("curStamina")), "maximum": number(dungeon.get("maxStamina")),
               "expected_full_at": _utc_ts(dungeon.get("maxTs")), "updated_at": _utc_ts(detail.get("currentTs")) or fetched_at}
    progress = [
        {"name": "每日活跃", "cur": number(daily.get("dailyActivation")), "total": number(daily.get("maxDailyActivation"))},
        {"name": "每周任务", "cur": number(weekly.get("score")), "total": number(weekly.get("total"))},
        {"name": "通行证", "cur": number(bp.get("curLevel")), "total": number(bp.get("maxLevel"))},
    ]
    regions = []
    for domain in rows(detail.get("domain")):
        collections = [{"level_id": entry.get("levelId"),
                        "puzzle_count": number(entry.get("puzzleCount")),
                        "chest_count": number(entry.get("trchestCount")),
                        "piece_count": number(entry.get("pieceCount")),
                        "blackbox_count": number(entry.get("blackboxCount"))}
                       for entry in rows(domain.get("collections"))]
        levels = []
        for level in rows(domain.get("levels")):
            levels.append({"id": level.get("levelId"), "name": level.get("name"),
                           "puzzles": obj(level.get("puzzleCount")),
                           "chests": obj(level.get("trchestCount")),
                           "equipment_chests": obj(level.get("equipTrchestCount")),
                           "pieces": obj(level.get("pieceCount")),
                           "blackboxes": obj(level.get("blackboxCount"))})
        settlements = [{"id": item.get("id"), "name": item.get("name"),
                        "level": number(item.get("level")), "money": number(item.get("remainMoney")),
                        "money_max": number(item.get("moneyMax"))}
                       for item in rows(domain.get("settlements"))]
        regions.append({"id": domain.get("domainId"), "name": domain.get("name"),
                        "level": number(domain.get("level")), "collections": collections,
                        "levels": levels, "settlements": settlements,
                        "money": obj(domain.get("moneyMgr"))})
    room_types = {0: '总控中枢', 1: '制造', 2: '种植', 4: '指挥', 5: '接待', 999997: '未解锁'}
    ship = [{"id": room.get("id"), "type": room.get("type"),
             'name': room.get('name') or room_types.get(room.get('type'), '舱室'), "level": number(room.get("level")),
             "operators": room.get("chars") if isinstance(room.get("chars"), list) else []}
            for room in rows(obj(detail.get("spaceShip")).get("rooms"))]
    achieve = obj(detail.get("achieve"))
    return {"base": {"role_id": str(base.get("roleId") or ""), "name": base.get("name"),
                     "server_name": base.get("serverName"), "level": number(base.get("level")),
                     "world_level": number(base.get("worldLevel")), "avatar_url": base.get("avatarUrl"),
                     "main_mission": obj(base.get("mainMission")).get("description"),
                     "char_count": number(base.get("charNum")), "weapon_count": number(base.get("weaponNum"))},
            "stamina": stamina, "progress": progress,
            "operators": [parse_operator(char) for char in rows(detail.get("chars"))],
            "regions": regions, "ship": ship,
            "achievements": {"count": number(achieve.get("count")),
                             "medals": rows(achieve.get("achieveMedals"))}}


def parse_attendance(data: dict) -> dict:
    awards = []
    for item in rows(data.get("awards")):
        res = obj(item.get("resource"))
        awards.append({"id": res.get("id"), "name": res.get("name"), "count": number(item.get("count")),
                       "icon_url": res.get("icon")})
    resource_map = obj(data.get("resourceInfoMap"))
    for award in rows(data.get("awardIds")):
        res = obj(resource_map.get(str(award.get("id"))))
        awards.append({"id": award.get("id"), "name": res.get("name"), "count": number(res.get("count")),
                       "icon_url": res.get("icon")})
    return {"supported": True, "status": "signed", "awards": awards,
            "signed_at": _utc_ts(data.get("ts")), "error": None}


def _attendance_award(item: dict, resources: dict, *, day: int | None = None) -> dict:
    award_id = str(item.get("awardId") or item.get("id") or "")
    info = obj(resources.get(award_id))
    result = {"id": award_id, "name": info.get("name"), "count": number(info.get("count")),
              "icon_url": info.get("icon"), "done": flag(item.get("done")),
              "available": flag(item.get("available"))}
    if day is not None:
        result["day"] = day
    if "ts" in item:
        result["signed_at"] = _utc_ts(item.get("ts"))
    return result


def parse_attendance_calendar(calendar_data: dict, record_data: dict) -> dict:
    calendar_data, record_data = obj(calendar_data), obj(record_data)
    resources = obj(calendar_data.get("resourceInfoMap"))
    record_resources = obj(record_data.get("resourceInfoMap"))
    calendar = [_attendance_award(item, resources, day=index)
                for index, item in enumerate(rows(calendar_data.get("calendar")), 1)]
    records = [_attendance_award(item, record_resources)
               for item in rows(record_data.get("records"))]
    activity = obj(calendar_data.get("activity"))
    activity_data = {"name": activity.get("name"), "description": activity.get("desc"),
                     "start_at": _utc_ts(activity.get("startTs")), "end_at": _utc_ts(activity.get("endTs")),
                     "calendar": [_attendance_award(item, resources)
                                  for item in rows(activity.get("calendar"))]} if activity else None
    signed = flag(calendar_data.get("hasToday"))
    done_count = sum(bool(item["done"]) for item in calendar)
    today_award = calendar[done_count - 1] if signed and done_count else (
        calendar[done_count] if done_count < len(calendar) else None)
    return {"supported": True, "status": "unknown" if signed is None else "signed" if signed else "unsigned",
            "awards": [item for item in calendar if item["done"]], "signed_at": None,
            "calendar": calendar, "today_award": today_award, "records": records, "first": [_attendance_award(item, resources)
            for item in rows(calendar_data.get("first"))], "activity": activity_data,
            "updated_at": _utc_ts(calendar_data.get("currentTs")), "error": None}


def parse_challenge(kind: str, data: dict) -> dict:
    data = obj(data)
    if kind == "war":
        seasons = rows(data.get("seasons"))
        records = [{"id": s.get("id"), "name": s.get("name"), "stars": number(s.get("stars")),
                    "start_at": _utc_ts(s.get("startTs")), "end_at": _utc_ts(s.get("endTs")),
                    "weeks": [{"id": w.get("id"), "name": w.get("name"), "stars": number(w.get("stars")),
                               "groups": rows(w.get("dungeonGroups"))} for w in rows(s.get("weeks"))]}
                   for s in seasons]
        summary = {"honors": [{"name": a.get("name"), "star": number(a.get("star")),
                                "first_pass_at": _utc_ts(a.get("firstPassTs"))} for a in rows(data.get("achieves"))]}
    elif kind == "monument":
        records = [{"id": g.get("id"), "name": g.get("name"),
                    "start_at": _utc_ts(g.get("activityStartTs")), "end_at": _utc_ts(g.get("activityEndTs")),
                    "groups": rows(g.get("dungeonGroups")), "medal": obj(g.get("achieve"))}
                   for g in rows(data.get("indieHardGroups"))]
        summary = {"count": len(records)}
    else:
        status = obj(data.get("status"))
        history = obj(data.get("history"))
        records = rows(history.get("records"))
        if not records and "id" in data and "chars" in data:
            records = [data]  # explicit recordDetail payload
        summary = {"id": status.get("id"), "name": status.get("name"),
                   "highest": number(status.get("highest")), "challenge_count": number(status.get("challengeCount")),
                   "best_record": obj(history.get("bestRecord")),
                   "weekly_mission": obj(status.get("weeklyMission")),
                   "indicator_mission": obj(status.get("indicatorMission")),
                   "stage_mission": obj(status.get("stageMission")),
                   "indicators": rows(data.get("indicators")), "dungeon": obj(data.get("dungeon"))}
    return {"supported": True, "kind": kind, "records": records, "summary": summary, "error": None}
