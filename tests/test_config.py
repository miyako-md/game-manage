from game_assistant.config import Settings


def test_defaults_when_no_file(tmp_path):
    s = Settings.load(str(tmp_path / "missing.toml"))
    assert s.stamina_seconds == 300
    assert s.activity_seconds == 3600
    assert s.news_seconds == 14400
    # Cloud public sources (news, announcements, calendars) are collected every 6 hours.
    assert s.cloud_public_poll_seconds == 21600 and s.cloud_private_poll_seconds == 900
    assert s.notify_send_key == ""
    assert s.wuwa_enabled is True


def test_load_from_toml(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'stamina_seconds = 120\n'
        'notify_send_key = "abc123"\n'
        'wuwa_token = "tok"\n',
        encoding="utf-8",
    )
    s = Settings.load(str(cfg))
    assert s.stamina_seconds == 120
    assert s.notify_send_key == "abc123"
    assert s.wuwa_token == "tok"


def test_nte_events_default_empty(tmp_path):
    s = Settings.load(str(tmp_path / "missing.toml"))
    assert s.nte_events == []


def test_nte_events_toml_array_of_tables(tmp_path):
    # TOML 数组表 [[nte_events]]：每项 name/category/start/end
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[[nte_events]]\n'
        'name = "第二索拉·诡影迷踪"\n'
        'category = "休闲活动"\n'
        'start = "2026-08-27 04:00"\n'
        'end = "2026-09-14 03:59"\n'
        '[[nte_events]]\n'
        'name = "签到赠礼"\n'
        'start = "2026-08-27 04:00"\n'
        'end = "2026-09-14 03:59"\n',
        encoding="utf-8",
    )
    s = Settings.load(str(cfg))
    assert isinstance(s.nte_events, list) and len(s.nte_events) == 2
    assert s.nte_events[0]["name"] == "第二索拉·诡影迷踪"
    assert s.nte_events[0]["category"] == "休闲活动"
    assert s.nte_events[1]["start"] == "2026-08-27 04:00"
    assert "category" not in s.nte_events[1]


def test_load_accepts_pre_release_template_keys(tmp_path):
    # app_host/app_port/wuwa_app_token 来自 0.1.0 之前的配置模板；Settings 用
    # extra='forbid'拒绝未知键，这三个键必须继续被接受才不会让旧配置报错。
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'app_host = "0.0.0.0"\n'
        'app_port = 9000\n'
        'wuwa_app_token = ""\n'
        'lol_enabled = false\n',
        encoding="utf-8",
    )
    s = Settings.load(str(cfg))
    assert s.lol_enabled is False


def test_endfield_challenge_interval_is_separate_and_bounded(tmp_path):
    import pytest
    from pydantic import ValidationError
    s = Settings.load(str(tmp_path / "missing.toml"))
    assert s.cloud_endfield_challenge_poll_seconds == 900
    s = Settings(cloud_private_poll_seconds=600, cloud_endfield_challenge_poll_seconds=1800)
    assert s.private_poll_seconds('endfield', 'combat') == 1800
    # Wuthering Waves has its own "combat" capability on the general interval.
    assert s.private_poll_seconds('wuthering_waves', 'combat') == 600
    assert s.private_poll_seconds('endfield', 'account') == 600
    for value in (299, 86401):
        with pytest.raises(ValidationError):
            Settings(cloud_endfield_challenge_poll_seconds=value)
    cfg = tmp_path / "config.toml"
    cfg.write_text("cloud_endfield_challenge_poll_seconds = 1800\n", encoding="utf-8")
    assert Settings.load(str(cfg)).cloud_endfield_challenge_poll_seconds == 1800


def test_guide_check_time_is_a_validated_beijing_hh_mm(tmp_path):
    import pytest
    from pydantic import ValidationError
    assert Settings.load(str(tmp_path / "missing.toml")).cloud_guide_check_time == "05:30"
    for value in ("00:00", "23:59", "04:15"):
        assert Settings(cloud_guide_check_time=value).cloud_guide_check_time == value
    for value in ("24:00", "5:30", "05:60", "05:30:00", "abc", "", "０５:３０", "٠٥:٣٠"):
        with pytest.raises(ValidationError):
            Settings(cloud_guide_check_time=value)
    cfg = tmp_path / "config.toml"
    cfg.write_text('cloud_guide_check_time = "06:00"\n', encoding="utf-8")
    assert Settings.load(str(cfg)).cloud_guide_check_time == "06:00"
