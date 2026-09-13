from datetime import datetime, timezone

from game_assistant.adapters.wuthering_waves.widget import (
    parse_progress, parse_version_activity)
from game_assistant.models import CoreReward, ProgressItem, VersionActivity

# 实测响应形状（2026-09-13，/gamer/widget/game3/getData 的 data 字段）
WIDGET_DATA = {
    "energyData": {"name": "结晶波片", "cur": 240, "total": 240,
                   "refreshTimeStamp": 0, "expireTimeStamp": 0, "status": 0},
    "activityData": {
        "enabled": True, "title": "身赴三途",
        "bgImg": "https://img.kurobbs.com/bg.jpg", "endTime": 1790654399,
        "coreRewards": [
            {"name": "若梦仍有回声", "cur": 0, "total": 0, "status": 0,
             "refreshTimeStamp": 1790625599},
            {"name": "清弦纪流年", "cur": 0, "total": 0,
             "refreshTimeStamp": 1789934399},
        ],
    },
    "livenessData": {"name": "活跃度", "cur": 100, "total": 100,
                     "refreshTimeStamp": 0},
    "storeEnergyData": {"name": "结晶单质", "cur": 381, "total": 480,
                        "refreshTimeStamp": 0},
    "towerData": {"name": "逆境深塔·深境区", "cur": 36, "total": 36,
                  "refreshTimeStamp": 1789329600},
    "slashTowerData": {"name": "冥歌海墟·再生-湍渊", "cur": 3, "total": 3,
                       "refreshTimeStamp": 1790539200},
    "weeklyData": {"name": "战歌重奏", "cur": 0, "total": 3, "refreshTimeStamp": 0},
    "weeklyRougeData": {"name": "千道门扉的异想", "cur": 0, "total": 6000,
                        "refreshTimeStamp": 0},
    "newTowerData": {"name": "终焉矩阵-稳态协议", "cur": 0, "total": 0,
                     "value": "暂无挑战记录", "refreshTimeStamp": 1790712000},
    "weeklyFrameData": {"name": "周度游历", "cur": 6000, "total": 6000,
                        "refreshTimeStamp": 0},
    "battlePassData": [
        {"name": "电台等级", "cur": 41, "total": 0, "refreshTimeStamp": 0},
        {"name": "本周经验", "cur": 8600, "total": 12000, "refreshTimeStamp": 0},
    ],
    "hasSignIn": False,
}


def _raw(data):
    return {"code": 200, "msg": "success", "data": data}


def test_parse_version_activity():
    act = parse_version_activity(_raw(WIDGET_DATA))
    assert isinstance(act, VersionActivity)
    assert act.title == "身赴三途"
    assert act.enabled is True
    # 10 位秒级时间戳 → aware UTC
    assert act.end_at == datetime.fromtimestamp(1790654399, tz=timezone.utc)
    assert act.core_rewards == [
        CoreReward(name="若梦仍有回声", cur=0, total=0, status=0),
        CoreReward(name="清弦纪流年", cur=0, total=0, status=0),
    ]


def test_parse_version_activity_data_as_json_string():
    # 实测 data 可能为 JSON 字符串形状（role.parse_widget_energy 同款兜底）
    import json
    act = parse_version_activity(_raw(json.dumps(WIDGET_DATA, ensure_ascii=False)))
    assert act.title == "身赴三途"
    assert len(act.core_rewards) == 2


def test_parse_version_activity_missing_returns_none():
    assert parse_version_activity(_raw({"energyData": {}})) is None
    assert parse_version_activity(_raw(None)) is None


def test_parse_progress_fixed_keys_and_battle_pass():
    items = parse_progress(_raw(WIDGET_DATA))
    # 8 个固定 key（energyData 除外，体力单独走 stamina 能力）+ battlePassData 扁平化 2 项
    assert len(items) == 10
    names = [it.name for it in items]
    assert names[:8] == [
        "逆境深塔·深境区", "冥歌海墟·再生-湍渊", "战歌重奏", "千道门扉的异想",
        "终焉矩阵-稳态协议", "周度游历", "活跃度", "结晶单质",
    ]
    assert names[8:] == ["电台等级", "本周经验"]
    tower = items[0]
    assert (tower.cur, tower.total) == (36, 36)
    assert tower.refresh_at == datetime.fromtimestamp(1789329600, tz=timezone.utc)
    # battlePassData 同样解析 cur/total（total=0 保留原值，由前端做无进度展示）
    bp = items[9]
    assert (bp.cur, bp.total) == (8600, 12000)
    assert all(isinstance(it, ProgressItem) for it in items)


def test_parse_progress_refresh_zero_or_invalid_to_none():
    items = parse_progress(_raw(WIDGET_DATA))
    by_name = {it.name: it for it in items}
    # refreshTimeStamp=0 → None（无重置语义）
    assert by_name["战歌重奏"].refresh_at is None
    assert by_name["活跃度"].refresh_at is None


def test_parse_progress_invalid_timestamp_values_to_none():
    raw = _raw({"towerData": {"name": "逆境深塔", "cur": 1, "total": 10,
                              "refreshTimeStamp": "abc"}})
    assert parse_progress(raw)[0].refresh_at is None
    raw = _raw({"towerData": {"name": "逆境深塔", "cur": 1, "total": 10,
                              "refreshTimeStamp": -5}})
    assert parse_progress(raw)[0].refresh_at is None


def test_parse_progress_empty_or_missing_data():
    assert parse_progress(_raw({})) == []
    assert parse_progress(_raw(None)) == []
