from datetime import datetime

from game_assistant.adapters.wuthering_waves.role import parse_role_data

RAW = {"code": 200, "data": {"name": "漂泊者", "level": 80,
                             "energy": {"power": 180, "max": 240}}}
NOW = datetime(2026, 9, 12, 12, 0, 0)


def test_account_fields():
    acc, _ = parse_role_data(RAW, NOW)
    assert acc.nickname == "漂泊者" and acc.level == 80


def test_stamina_eta_fallback_6min_per_point():
    _, st = parse_role_data(RAW, NOW)
    assert st.current == 180 and st.maximum == 240
    assert st.expected_full_at == datetime(2026, 9, 12, 18, 0)  # 60点×6分钟


def test_stamina_eta_from_refresh_timestamp():
    raw = {"code": 200, "data": {"energy": {"power": 200, "max": 240,
                                            "refreshTimestamp": 1788525600000}}}
    _, st = parse_role_data(raw, NOW)
    assert st.expected_full_at == datetime.fromtimestamp(1788525600)
