from game_assistant.config import Settings


def test_defaults_when_no_file(tmp_path):
    s = Settings.load(str(tmp_path / "missing.toml"))
    assert s.stamina_seconds == 300
    assert s.activity_seconds == 3600
    assert s.news_seconds == 14400
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
