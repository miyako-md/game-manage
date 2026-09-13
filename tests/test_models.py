from datetime import datetime, timezone

from game_assistant.models import (
    AccountInfo, AnnouncementItem, CalabashData, Capability, CountryGroup,
    CoreReward, DetectionSummary, ExplorationData, AreaSummary, FetchResult,
    MatchSummary, ProgressItem, RoleEntry, StaminaInfo, VersionActivity,
)


def test_capability_values():
    assert Capability.STAMINA == "stamina"
    assert Capability("account") is Capability.ACCOUNT


def test_capability_exploration_calabash_roles_values():
    assert Capability.EXPLORATION == "exploration"
    assert Capability.CALABASH == "calabash"
    assert Capability.ROLES == "roles"


def test_role_entry_roundtrip():
    e = RoleEntry(role_id=1402, name="散华", level=90, attribute="衍射",
                  breach=6, chain=6, star_level=5, weapon="迅刀",
                  icon_url="https://web-static.kurobbs.com/a.png", is_main=True)
    assert RoleEntry.model_validate(e.model_dump()) == e


def test_exploration_roundtrip():
    e = ExplorationData(
        detections=DetectionSummary(total=199,
                                    by_level={"轻波级": 120, "海啸级": 9}),
        country_groups=[CountryGroup(name="瑝珑", progress=67.06,
                                     areas=[AreaSummary(name="云陵谷",
                                                        progress=100.0)])])
    assert ExplorationData.model_validate(e.model_dump()) == e


def test_calabash_roundtrip():
    c = CalabashData(level=30, base_catch="20%", catch_quality=5,
                     cur_exp=1375, max_count=724)
    assert CalabashData.model_validate(c.model_dump()) == c


def test_capability_progress_value():
    assert Capability.PROGRESS == "progress"


def test_version_activity_roundtrip():
    a = VersionActivity(
        title="身赴三途",
        end_at=datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc),
        enabled=True,
        core_rewards=[CoreReward(name="若梦仍有回声", cur=3, total=5, status=0)])
    assert VersionActivity.model_validate(a.model_dump()) == a


def test_progress_item_roundtrip():
    p = ProgressItem(name="周度游历", cur=6000, total=6000,
                     refresh_at=datetime(2026, 9, 15, 4, 0, tzinfo=timezone.utc),
                     status=0)
    assert ProgressItem.model_validate(p.model_dump()) == p


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
