from datetime import datetime

from game_assistant.models import (
    AccountInfo, ActivityItem, AnnouncementItem, Capability, FetchResult, MatchSummary,
    StaminaInfo,
)


def test_capability_values():
    assert Capability.STAMINA == "stamina"
    assert Capability("account") is Capability.ACCOUNT


def test_stamina_roundtrip():
    s = StaminaInfo(current=180, maximum=240,
                    expected_full_at=datetime(2026, 9, 12, 20, 0),
                    updated_at=datetime(2026, 9, 12, 12, 0))
    assert StaminaInfo.model_validate(s.model_dump()) == s


def test_fetch_result_error():
    r = FetchResult(ok=False, error="未配置凭据")
    assert r.ok is False and r.payload is None


def test_capability_match_value():
    assert Capability.MATCH == "match"


def test_match_summary_roundtrip():
    m = MatchSummary(match_id="1234567890", queue_id=450, mode="ARAM",
                     start_at=datetime(2026, 9, 13, 20, 0, tzinfo=None),
                     duration_seconds=1234, win=True, champion_id=157,
                     kills=8, deaths=3, assists=10)
    assert MatchSummary.model_validate(m.model_dump()) == m
