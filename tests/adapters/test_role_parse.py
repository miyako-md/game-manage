import json
from datetime import datetime, timedelta, timezone

from game_assistant.adapters.wuthering_waves.role import (
    parse_role_list, parse_widget_energy,
)

# 实测 /gamer/role/list 响应形状（2026-09-13）：data 为数组，gameLevel 是字符串
ROLE_LIST_RAW = {"code": 200, "msg": "success", "data": [{
    "roleId": "100000001", "serverId": "76402e5b20be2c39f095a152090afddc",
    "roleName": "测试漂泊者", "gameLevel": "80", "activeDay": 534,
    "achievementCount": 604, "roleNum": 46, "serverName": "鸣潮",
    "isDefault": True,
}]}
WIDGET_RAW = {"code": 200, "msg": "success", "data": {
    "energyData": {"name": "结晶波片", "cur": 180, "total": 240,
                   "refreshTimeStamp": 0, "expireTimeStamp": 0, "status": 0},
    "hasSignIn": True, "roleName": "测试漂泊者",
}}

NOW = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)


def test_parse_role_list_defaults_to_first_role():
    acc = parse_role_list(ROLE_LIST_RAW)
    assert acc.nickname == "测试漂泊者"
    assert acc.level == 80  # gameLevel 是字符串 "80"，必须转成 int
    assert acc.extra["role_id"] == "100000001"
    assert acc.extra["server_id"] == "76402e5b20be2c39f095a152090afddc"
    assert acc.extra["server_name"] == "鸣潮"
    assert acc.extra["active_day"] == 534
    assert acc.extra["achievement_count"] == 604
    assert acc.extra["role_num"] == 46


def test_parse_role_list_empty_data():
    acc = parse_role_list({"code": 200, "data": []})
    assert acc.nickname is None
    assert acc.level is None
    assert acc.extra["role_id"] is None


def test_widget_energy_eta_fallback_6min_per_point():
    st = parse_widget_energy(WIDGET_RAW, NOW)
    assert st.current == 180 and st.maximum == 240
    assert st.expected_full_at == NOW + timedelta(minutes=60 * 6)  # 60点×6分钟
    assert st.updated_at == NOW


def test_widget_energy_full_no_eta():
    raw = {"code": 200, "data": {"energyData": {"cur": 240, "total": 240}}}
    st = parse_widget_energy(raw, NOW)
    assert st.current == 240 and st.expected_full_at is None


def test_widget_energy_data_as_json_string():
    # 实测 data 可能为 JSON 字符串，需 json.loads 兜底
    raw = {"code": 200, "data": json.dumps(WIDGET_RAW["data"])}
    st = parse_widget_energy(raw, NOW)
    assert st.current == 180 and st.maximum == 240
    assert st.expected_full_at == NOW + timedelta(minutes=60 * 6)
