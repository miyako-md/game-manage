"""Synthetic NTE SDK/live response shapes; no credentials or real user data."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from game_assistant.adapters.neverness.parse import (
    parse_account, parse_exploration, parse_gacha, parse_progress,
    parse_record, parse_roles, parse_stamina,
)
from game_assistant.models import StaminaInfo

NOW = datetime(2026, 9, 14, tzinfo=timezone.utc)


def wrap(data):
    return {"code": 0, "data": data}


def home():
    return {"roleid": "123", "rolename": "测试", "lev": 40,
            "servername": "异环", "worldlevel": 5, "tycoonLevel": 7,
            "roleloginDays": 20, "charidCnt": 4,
            "staminaValue": 0, "staminaMaxValue": 180,
            "citystaminaValue": 23, "citystaminaMaxValue": 100,
            "dayvalue": 60, "weekcopiesremainCnt": 2,
            "achieveProgress": {"achievementCnt": 21, "total": 100},
            "realestate": {"ownCnt": 1, "total": 3},
            "vehicle": {"ownCnt": 0, "total": 7}}


def test_account_maps_home_counts_and_missing_counts_remain_unknown():
    result = parse_account(wrap(home()), expected_role_id="123")
    assert result.model_dump() == {
        "schema_version": 1, "nickname": "测试", "level": 40,
        "role_id": "123", "server_name": "异环", "world_level": 5,
        "tycoon_level": 7, "active_days": 20, "character_count": 4,
        "achievement_count": 21, "achievement_total": 100,
        "house_count": 1, "house_total": 3, "vehicle_count": 0, "vehicle_total": 7,
    }
    assert parse_account(wrap({"roleid": "123"})).vehicle_count is None


def test_stamina_preserves_zero_and_remaining_semantics_without_guessed_time():
    result = parse_stamina(wrap(home()), NOW, expected_role_id="123")
    assert isinstance(result, StaminaInfo)
    assert (result.current, result.maximum) == (0, 180)
    assert (result.city_current, result.city_maximum) == (23, 100)
    assert (result.daily_activity, result.weekly_remaining) == (60, 2)
    assert result.expected_full_at is None
    assert result.updated_at == NOW
    assert result.schema_version == 1


@pytest.mark.parametrize("value", [None, "NaN", float("inf"), -1, True, 1.5])
def test_invalid_main_stamina_fails_instead_of_zero(value):
    data = home()
    data["staminaValue"] = value
    with pytest.raises(ValueError):
        parse_stamina(wrap(data), NOW)


def test_missing_main_stamina_fails_and_missing_secondary_is_unknown():
    with pytest.raises(ValueError):
        parse_stamina(wrap({"roleid": "123"}), NOW)
    result = parse_stamina(wrap({"staminaValue": 1, "staminaMaxValue": 180}), NOW)
    assert result.city_current is None
    assert result.weekly_remaining is None


def test_live_home_without_weekly_field_keeps_other_stamina_values():
    data = home()
    del data["weekcopiesremainCnt"]
    result = parse_stamina(wrap(data), NOW)
    assert result.weekly_remaining is None
    assert result.daily_activity == 60
    assert result.current == 0


@pytest.mark.parametrize("parser", [parse_account, lambda raw, **kw: parse_stamina(raw, NOW, **kw), parse_gacha])
def test_mismatched_home_or_gacha_identity_is_rejected(parser):
    data = {**home(), "gachaDetails": []}
    with pytest.raises(ValueError):
        parser(wrap(data), expected_role_id="999")


def test_roles_map_distinct_levels_and_official_icon():
    result = parse_roles(wrap([{
        "id": "1019", "name": "角色", "alev": 55, "slev": 2,
        "awakenLev": 3, "likeabilitylev": 3300,
        "quality": "ITEM_QUALITY_ORANGE", "elementType": "CHARACTER_ELEMENT_TYPE_PSYCHE",
        "fork": {"id": "fork_test", "name": "弧盘", "alev": "40", "slev": "1", "quality": "ITEM_QUALITY_PURPLE"},
        "properties": [{"id": "atk", "name": "攻击", "value": "1000"}, {"id": "unknown"}],
        "skills": [{"id": "s1", "name": "战技", "level": 5}],
        "citySkills": [{"id": "c1", "name": "城区技能", "level": 2}],
    }]))
    entry = result.entries[0]
    assert (entry.level, entry.awaken_level, entry.mix_level, entry.affinity_exp) == (55, 3, 2, 3300)
    assert (entry.quality, entry.element) == ("S", "魂")
    assert entry.icon_url == "https://webstatic.tajiduo.com/bbs/yh-game-records-web-source/character/detail/1019.png"
    assert entry.weapon.model_dump() == {"name": "弧盘", "level": 40, "quality": "A", "mix_level": 1}
    assert [p.model_dump() for p in entry.properties] == [{"name": "攻击", "value": "1000"}]
    assert entry.skills[0].level == 5
    assert entry.city_skills[0].name == "城区技能"


def test_roles_keep_unknown_labels_and_missing_numbers_and_reject_bad_ids():
    role = parse_roles(wrap([{"id": "x", "quality": "FUTURE", "elementType": "新元素"}])).entries[0]
    assert (role.quality, role.element, role.level, role.weapon) == ("FUTURE", "新元素", None, None)
    with pytest.raises(ValueError):
        parse_roles(wrap([{"name": "missing ID"}]))
    role = parse_roles(wrap([{"id": "../escape"}])).entries[0]
    assert role.icon_url is None


def test_progress_uses_achievement_counts_and_categories():
    result = parse_progress(wrap({"achievementCnt": 0, "total": 100,
                                 "bronzeUmdCnt": 2, "silverUmdCnt": 1,
                                 "detail": [{"id": "1", "name": "旅途", "progress": 0, "total": 20}]}))
    assert (result.completed, result.total, result.bronze, result.silver, result.gold) == (0, 100, 2, 1, None)
    assert result.categories[0].model_dump() == {"id": "1", "name": "旅途", "current": 0, "total": 20}


def test_exploration_null_and_counts_are_not_percentages_or_zero():
    result = parse_exploration(wrap([{"id": "a", "name": "区域", "progress": 5, "total": 40,
        "detail": [{"id": "b", "name": "未解锁", "progress": None, "total": 20},
                   {"id": "c", "name": "未探索", "progress": 0, "total": 10}]}]))
    assert (result.areas[0].current, result.areas[0].total) == (5, 40)
    assert result.areas[0].details[0].current is None
    assert result.areas[0].details[1].current == 0


def test_gacha_pool_s_count_differs_from_detail_pity_and_dates_are_beijing():
    result = parse_gacha(wrap({"gachaDetails": [{"tab": "限定卡池", "m": 90,
        "drawCount": 130, "rareCount": 2, "average": "65.0", "playerOver": "45%",
        "details": [{"charid": "1019", "rareCount": 80, "timeStamp": 0},
                    {"charid": "fork_unknown", "rareCount": 50, "time": "2026-09-14"}]}]}),
        names={"1019": "角色"}, expected_role_id="123")
    assert (result.total_draws, result.total_s) == (130, 2)
    assert result.role_id == ""
    pool = result.pools[0]
    assert (pool.s_count, pool.average, pool.percentile, pool.guarantee) == (2, 65.0, 45.0, 90)
    assert (pool.details[0].name, pool.details[0].pity) == ("角色", 80)
    assert pool.details[0].obtained_at.isoformat() == "1970-01-01T08:00:00+08:00"
    assert pool.details[1].name == "角色/弧盘 fork_unknown"
    assert pool.details[1].obtained_at.utcoffset() == timedelta(hours=8)
    assert "current_pity" not in pool.model_dump()


def test_missing_gacha_pool_counts_do_not_make_fake_totals():
    result = parse_gacha(wrap({"gachaDetails": [{"tab": "弧盘池", "details": []}]}))
    assert result.total_draws is None and result.total_s is None


def test_absent_gacha_pool_stats_are_unknown_but_explicit_zero_counts_are_zero():
    empty = parse_gacha(wrap({"gachaDetails": []}))
    assert empty.total_draws is None and empty.total_s is None
    zero = parse_gacha(wrap({"gachaDetails": [{"tab": "常驻", "drawCount": 0, "rareCount": 0, "details": []}]}))
    assert zero.total_draws == 0 and zero.total_s == 0


def test_unrecognized_gacha_pool_is_rejected_instead_of_unknown_success():
    with pytest.raises(ValueError):
        parse_gacha(wrap({"gachaDetails": [{"new_pool_structure": {}}]}))


@pytest.mark.parametrize("value", ["NaN", "Infinity", float("-inf"), True, -4])
def test_nonfinite_and_invalid_optional_counts_stay_unknown(value):
    assert parse_account(wrap({"roleid": "123", "lev": value})).level is None
    result = parse_gacha(wrap({"gachaDetails": [{"tab": "常驻", "average": value, "drawCount": value, "details": []}]}))
    assert result.pools[0].average is None
    assert result.pools[0].total_draws is None


def test_record_filters_game_and_selected_role_and_omits_account():
    def card(game, role, link="https://bbs.tajiduo.com/x"):
        return {"gameId": game, "gameName": "异环", "link": link,
                "bindRoleInfo": {"gameId": game, "roleId": role, "roleName": "角色", "lev": 40,
                                 "serverName": "区服", "account": "private_account"}}
    result = parse_record(wrap([card(100, "123"), card(1289, "999"), card(1289, "123")]), expected_role_id="123")
    assert [c.model_dump() for c in result.cards] == [{"game_name": "异环", "role_id": "123", "nickname": "角色", "level": 40,
                                                     "server_name": "区服", "url": "https://bbs.tajiduo.com/x"}]
    assert "private_account" not in result.model_dump_json()
    assert parse_record(wrap([card(1289, "123", "javascript:alert(1)")])).cards[0].url is None


@pytest.mark.parametrize("parser,data,field", [(parse_roles, [], "entries"), (parse_exploration, [], "areas"),
    (parse_record, [], "cards"), (parse_gacha, {"gachaDetails": []}, "pools"),
    (parse_progress, {"detail": []}, "categories")])
def test_explicit_empty_collections_and_serialized_data_wrappers(parser, data, field):
    result = parser(wrap(json.dumps(wrap(json.dumps(data)))))
    assert getattr(result, field) == []
    assert result.model_dump()["schema_version"] == 1


@pytest.mark.parametrize("parser", [parse_account, parse_roles, parse_progress, parse_exploration, parse_gacha, parse_record])
@pytest.mark.parametrize("raw", [None, {"data": {}}, {"data": {"private": [{"id": "1"}]}}, {"data": "broken json"}, {"code": 401, "data": []}])
def test_bad_or_unknown_structure_raises_generic_parse_error(parser, raw):
    with pytest.raises(ValueError) as error:
        parser(raw)
    assert "private" not in str(error.value)


@pytest.mark.parametrize("parser,data", [(parse_roles, [None]), (parse_roles, [{"id": "1", "skills": {}}]),
    (parse_exploration, [{"id": "1", "detail": [None]}]),
    (parse_progress, {"detail": {}}), (parse_gacha, {"gachaDetails": [{"details": {}}]}),
    (parse_record, [{"gameId": 1289, "bindRoleInfo": {"roleId": ""}}])])
def test_malformed_collection_entries_do_not_become_successful_empty_payload(parser, data):
    with pytest.raises(ValueError):
        parser(wrap(data))
