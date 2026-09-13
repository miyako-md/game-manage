import json

from game_assistant.adapters.wuthering_waves.rolebox import (
    parse_calabash_data, parse_explore_index, parse_role_data,
)
from game_assistant.models import ExplorationData

# 实测形状 fixture（2026-09-13 完整响应校准）：exploreIndex data 为 JSON 字符串
# （信封）；exploreList 4 组国家（瑝珑/黑海岸/黎那汐塔/罗伊冰原），每组
# country.countryName + countryProgress（数字/字符串两种）+ areaInfoList；
# detectionInfoList 约 199 项（fixture 缩样），按 levelName 分级计数
EXPLORE_INNER = {
    "detectionInfoList": [
        {"detectionName": "嗷呜", "levelName": "轻波级", "level": 1},
        {"detectionName": "咔咔", "levelName": "轻波级", "level": 2},
        {"detectionName": "咕咕", "levelName": "巨浪级", "level": 3},
        {"detectionName": "呜呜", "levelName": "怒涛级", "level": 3},
        {"detectionName": "啦啦", "levelName": "海啸级", "level": 4},
    ],
    "exploreList": [
        {"country": {"countryId": 1, "countryName": "瑝珑"},
         "countryProgress": 67.06,
         "areaInfoList": [
             {"areaId": 1, "areaName": "云陵谷", "areaProgress": 100,
              "itemList": [{"icon": "", "name": "信标", "progress": 100,
                            "type": 2}]},  # itemList 明细不进模型
             {"areaId": 2, "areaName": "怨毒之地", "areaProgress": None},
         ]},
        {"country": {"countryId": 2, "countryName": "黑海岸"},
         "countryProgress": "60.00",  # 字符串形状
         "areaInfoList": []},
        {"country": {"countryId": 3, "countryName": "黎那汐塔"},
         "countryProgress": 49.86,
         "areaInfoList": [{"areaId": 3, "areaName": "黎那汐塔城",
                           "areaProgress": "88.8%"}]},  # 带百分号的字符串
        {"country": {"countryId": 4, "countryName": "罗伊冰原"},
         "countryProgress": 57.66,
         "areaInfoList": [{"areaId": 4, "areaName": "雪原哨站"}]},  # 进度缺失
    ],
    "open": True,
}
EXPLORE_ENVELOPE = {"code": 200, "msg": "success",
                    "data": json.dumps(EXPLORE_INNER, ensure_ascii=False)}

CALABASH_INNER = {"level": 30, "baseCatch": "20%", "catchQuality": 5,
                  "curExp": 1375, "maxCount": 724,
                  "phantomList": [{"star": 5, "maxStar": 5}]}
CALABASH_ENVELOPE = {"code": 200, "msg": "success",
                     "data": json.dumps(CALABASH_INNER, ensure_ascii=False)}

# roleData 实测形状：roleList 单项含 roleId/roleName/level/attributeName/
# breach/chainUnlockNum/starLevel/weaponTypeName/roleIconUrl/isMainRole；
# fixture 打乱 level/chain 顺序以验证排序（level 降序 + chain 降序）
ROLE_INNER = {"roleList": [
    {"roleId": 1501, "roleName": "长离", "level": 90, "attributeName": "热熔",
     "breach": 6, "chainUnlockNum": 0, "starLevel": 5,
     "weaponTypeName": "迅刀", "isMainRole": False,
     "roleIconUrl": "https://web-static.kurobbs.com/c.png",
     "roleSkin": {"skinName": "裁羽行歌"}},  # roleSkin 等未消费字段忽略
    {"roleId": 1102, "roleName": "秧秧", "level": 40, "attributeName": "气动",
     "breach": 2, "chainUnlockNum": 3, "starLevel": 4,
     "weaponTypeName": "佩枪"},  # 无 roleIconUrl → icon_url None
    {"roleId": 1402, "roleName": "散华", "level": 90, "attributeName": "衍射",
     "breach": 6, "chainUnlockNum": 6, "starLevel": 5,
     "weaponTypeName": "迅刀", "isMainRole": True,
     "roleIconUrl": "https://web-static.kurobbs.com/a.png"},
    "bad", 123,  # 非 dict 项应被跳过
], "showToGuest": True}
ROLE_ENVELOPE = {"code": 200, "msg": "success",
                 "data": json.dumps(ROLE_INNER, ensure_ascii=False)}


def test_explore_index_from_envelope_with_string_data():
    d = parse_explore_index(EXPLORE_ENVELOPE)
    assert isinstance(d, ExplorationData)
    # 残象探寻：total = 列表长度，按级计数保持出现顺序
    assert d.detections.total == 5
    assert d.detections.by_level == {"轻波级": 2, "巨浪级": 1, "怒涛级": 1,
                                     "海啸级": 1}
    # 国家分组：4 组，countryProgress 数字/"60.00"字符串统一转 float
    assert [g.name for g in d.country_groups] == \
        ["瑝珑", "黑海岸", "黎那汐塔", "罗伊冰原"]
    assert [g.progress for g in d.country_groups] == \
        [67.06, 60.0, 49.86, 57.66]
    # 地区：areaProgress 数字/None/带%字符串三种形状；itemList 不进模型
    linggu = d.country_groups[0]
    assert [(a.name, a.progress) for a in linggu.areas] == \
        [("云陵谷", 100.0), ("怨毒之地", None)]
    assert d.country_groups[1].areas == []
    assert (d.country_groups[2].areas[0].name,
            d.country_groups[2].areas[0].progress) == ("黎那汐塔城", 88.8)
    assert d.country_groups[3].areas[0].progress is None


def test_explore_index_accepts_inner_dict_from_client():
    # rolebox_client.post 已把 data 字符串二次解析为 dict（直接返回内层）
    d = parse_explore_index(EXPLORE_INNER)
    assert d.detections.by_level["轻波级"] == 2
    assert d.country_groups[0].name == "瑝珑"


def test_explore_index_missing_fields_fall_back_to_defaults():
    d = parse_explore_index({})            # 空数据
    assert d.detections.total == 0 and d.detections.by_level == {}
    assert d.country_groups == []

    d2 = parse_explore_index("{not-json}")  # 非法字符串 → 防御式空数据
    assert d2 == ExplorationData()

    # levelName 缺失 → 回退 "等级{level}" 计数
    d3 = parse_explore_index({"detectionInfoList": [{"detectionName": "x", "level": 2}]})
    assert d3.detections.by_level == {"等级2": 1} and d3.detections.total == 1


def test_calabash_data_from_envelope_with_string_data():
    d = parse_calabash_data(CALABASH_ENVELOPE)
    assert (d.level, d.base_catch, d.catch_quality) == (30, "20%", 5)
    assert (d.cur_exp, d.max_count) == (1375, 724)


def test_calabash_data_missing_fields_are_none():
    d = parse_calabash_data({"level": "abc"})  # 非法数值安全转 None
    assert d.level is None and d.base_catch is None
    assert d.catch_quality is None and d.cur_exp is None and d.max_count is None


def test_role_data_sorted_by_level_then_chain():
    d = parse_role_data(ROLE_ENVELOPE)
    # level 降序 + chain 降序：散华(90/6链) > 长离(90/0链) > 秧秧(40/3链)
    assert [e.name for e in d] == ["散华", "长离", "秧秧"]
    sanhua = d[0]
    assert (sanhua.role_id, sanhua.level, sanhua.chain) == (1402, 90, 6)
    assert sanhua.attribute == "衍射" and sanhua.breach == 6
    assert sanhua.star_level == 5 and sanhua.weapon == "迅刀"
    assert sanhua.is_main is True
    assert sanhua.icon_url == "https://web-static.kurobbs.com/a.png"
    assert d[2].icon_url is None          # 缺 roleIconUrl → None
    assert d[2].star_level == 4


def test_role_data_accepts_inner_dict_and_defaults():
    d = parse_role_data(ROLE_INNER)       # 客户端 post 返回的内层 dict
    assert [e.name for e in d] == ["散华", "长离", "秧秧"]

    assert parse_role_data({}) == []      # 空数据 → 空列表
    assert parse_role_data("{not-json}") == []
    assert parse_role_data({"roleList": []}) == []
