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
