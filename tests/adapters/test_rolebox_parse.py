import json

from game_assistant.adapters.wuthering_waves.rolebox import (
    parse_calabash_data, parse_explore_index,
)
from game_assistant.models import ExplorationData

# 实测形状 fixture（2026-09-13）：exploreIndex data 为 JSON 字符串（信封）；
# areaProgress 覆盖百分比字符串与数字两种；detectionInfoList 覆盖分级计数
EXPLORE_INNER = {
    "countryProgress": "85%",
    "areaInfoList": [
        {"areaName": "今州城", "areaProgress": "100%",
         "itemList": [{"type": 1, "name": "信标", "progress": "50%"},
                      {"type": 2, "name": "宝箱", "progress": "8/10"},
                      {"type": 3}]},  # 无 name 的条目应被跳过
        {"areaName": "无光之森", "areaProgress": 72.5, "itemList": []},
        {"areaName": "怨毒之地", "areaProgress": None},  # 进度缺失
    ],
    "detectionInfoList": [
        {"detectionName": "嗷呜", "levelName": "轻波级", "level": 1},
        {"detectionName": "咔咔", "levelName": "轻波级", "level": 2},
        {"detectionName": "咕咕", "levelName": "巨浪级", "level": 3},
        {"detectionName": "呜呜", "levelName": "怒涛级", "level": 3},
    ],
}
EXPLORE_ENVELOPE = {"code": 200, "msg": "success",
                    "data": json.dumps(EXPLORE_INNER, ensure_ascii=False)}

CALABASH_INNER = {"level": 30, "baseCatch": "20%", "catchQuality": 5,
                  "curExp": 1375, "maxCount": 724,
                  "phantomList": [{"star": 5, "maxStar": 5}]}
CALABASH_ENVELOPE = {"code": 200, "msg": "success",
                     "data": json.dumps(CALABASH_INNER, ensure_ascii=False)}


def test_explore_index_from_envelope_with_string_data():
    d = parse_explore_index(EXPLORE_ENVELOPE)
    assert isinstance(d, ExplorationData)
    assert d.country_progress == "85%"
    assert [a.name for a in d.areas] == ["今州城", "无光之森", "怨毒之地"]
    assert d.areas[0].progress == 100.0                      # "100%" → 100.0
    assert d.areas[0].items == ["信标 50%", "宝箱 8/10"]       # 压缩字符串
    assert d.areas[1].progress == 72.5                       # 数字形状
    assert d.areas[2].progress is None                       # 缺失 → None
    assert d.detection_count == 4
    assert d.detection_by_level == {"轻波级": 2, "巨浪级": 1, "怒涛级": 1}


def test_explore_index_accepts_inner_dict_from_client():
    # rolebox_client.post 已把 data 字符串二次解析为 dict（直接返回内层）
    d = parse_explore_index(EXPLORE_INNER)
    assert d.country_progress == "85%"
    assert d.detection_by_level["轻波级"] == 2


def test_explore_index_missing_fields_fall_back_to_defaults():
    d = parse_explore_index({})            # 空数据
    assert d.country_progress is None
    assert d.areas == [] and d.detection_count == 0
    assert d.detection_by_level == {}

    d2 = parse_explore_index("{not-json}")  # 非法字符串 → 防御式空数据
    assert d2 == ExplorationData()

    # levelName 缺失 → 回退 "等级{level}" 计数
    d3 = parse_explore_index({"detectionInfoList": [{"detectionName": "x", "level": 2}]})
    assert d3.detection_by_level == {"等级2": 1} and d3.detection_count == 1


def test_calabash_data_from_envelope_with_string_data():
    d = parse_calabash_data(CALABASH_ENVELOPE)
    assert (d.level, d.base_catch, d.catch_quality) == (30, "20%", 5)
    assert (d.cur_exp, d.max_count) == (1375, 724)


def test_calabash_data_missing_fields_are_none():
    d = parse_calabash_data({"level": "abc"})  # 非法数值安全转 None
    assert d.level is None and d.base_catch is None
    assert d.catch_quality is None and d.cur_exp is None and d.max_count is None
