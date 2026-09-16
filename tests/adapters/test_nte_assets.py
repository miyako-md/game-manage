"""Asset endpoint contracts: preserve unknowns and reject broken snapshots."""
import json

import pytest

from game_assistant.adapters.neverness.assets import (
    parse_realestate, parse_teams, parse_vehicles,
)


def test_realestate_decodes_residents_and_preserves_furniture_ownership():
    result = parse_realestate({"code": 200, "data": json.dumps({
        "ownCnt": 1, "total": 2, "detail": [
            {"id": "home1", "name": "海景公寓", "own": True,
             "chars": '[1019,"1020"]', "fdetail": [
                 {"id": "chair", "name": "木椅", "own": False},
                 {"id": "table", "name": "桌子", "own": True}]},
            {"id": "home2", "name": "别墅", "own": False, "chars": ""},
        ]})})
    assert result.schema_version == 1
    assert (result.owned_count, result.total) == (1, 2)
    assert result.entries[0].resident_ids == ["1019", "1020"]
    assert [f.owned for f in result.entries[0].furniture] == [False, True]
    assert result.entries[1].owned is False
    assert result.entries[1].resident_ids == []


def test_missing_counts_and_ownership_remain_unknown_including_furniture():
    result = parse_realestate({"detail": [{"id": 1, "fdetail": [{"id": 2}]}]})
    assert result.owned_count is None
    assert result.total is None
    assert result.entries[0].owned is None
    assert result.entries[0].furniture[0].owned is None


def test_vehicle_stats_keep_source_text_and_model_type_distinct_from_id():
    result = parse_vehicles({"code": "0", "data": {"ownCnt": 0, "total": None,
        "showId": "car1", "showName": "街道之星", "detail": [{
            "id": "car1", "name": "街道之星", "own": False,
            "base": [{"name": "最高时速", "value": "146"}, {"name": "未公开"}],
            "advanced": [{"name": "加速", "value": "0", "max": "10.0"}],
            "models": [{"id": "item-1", "type": "paint-red"}]}]}})
    assert result.owned_count == 0
    assert result.total is None
    assert result.show_id == "car1"
    assert result.show_name == "街道之星"
    car = result.entries[0]
    assert car.base[0].value == "146"
    assert car.base[1].value is None
    assert (car.advanced[0].value, car.advanced[0].maximum) == ("0", "10.0")
    assert (car.models[0].id, car.models[0].type) == ("item-1", "paint-red")


def test_team_urls_are_filtered_and_description_remains_plain_source_text():
    result = parse_teams({"code": 200, "data": json.dumps([{
        "id": "t1", "name": "队伍一", "desc": '<b>原始描述</b>',
        "icon": "javascript:alert(1)", "imgs": [
            "https://example.com/a.png", "http://example.com/b.png", "//example.com/x",
            "data:image/png,bad", "https://user:pass@example.com/x", "https://[invalid",
        ]}])})
    assert result.entries[0].icon_url is None
    assert result.entries[0].description == '<b>原始描述</b>'
    assert result.entries[0].image_urls == ["https://example.com/a.png", "http://example.com/b.png"]
    assert "owned_count" not in result.model_dump()


@pytest.mark.parametrize("parser,raw", [
    (parse_realestate, {"detail": []}), (parse_vehicles, {"detail": []}), (parse_teams, []),
])
def test_explicit_empty_collections_are_successful(parser, raw):
    assert parser(raw).entries == []


@pytest.mark.parametrize("parser,raw", [
    (parse_realestate, {}), (parse_realestate, {"detail": None}),
    (parse_realestate, {"detail": [{"id": 1, "chars": "not-json"}]}),
    (parse_realestate, {"detail": [{"id": 1, "chars": '{"id":1}'}]}),
    (parse_realestate, {"detail": [{"id": 1, "chars": '[null]'}]}),
    (parse_realestate, {"detail": [{"id": 1, "fdetail": {}}]}),
    (parse_vehicles, {"detail": [{"id": 1, "base": "secret"}]}),
    (parse_vehicles, {"detail": [{"id": 1, "advanced": [None]}]}),
    (parse_vehicles, {"detail": [{"id": 1, "models": {}}]}),
    (parse_teams, [{"id": "t", "imgs": [{}]}]),
    (parse_teams, {"detail": []}), (parse_teams, [{"name": "missing-id"}]),
    (parse_teams, {"code": 401, "data": [], "msg": "secret-value"}),
])
def test_malformed_payloads_fail_without_echoing_raw_input(parser, raw):
    with pytest.raises(ValueError, match="异环数据格式无效") as err:
        parser(raw)
    assert "secret" not in str(err.value)


@pytest.mark.parametrize("own,expected", [(True, True), (False, False), (1, True),
    (0, False), ("1", True), ("0", False), (None, None), ("unknown", None), (2, None)])
def test_ownership_does_not_treat_nonempty_false_strings_as_owned(own, expected):
    assert parse_realestate({"detail": [{"id": 1, "own": own}]}).entries[0].owned is expected
