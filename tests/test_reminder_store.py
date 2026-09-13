from game_assistant.config import Settings
from game_assistant.reminder_store import ReminderDedup


def test_config_defaults():
    s = Settings(notify_send_key="")
    assert s.notify_stamina_full is True
    assert s.stamina_threshold_percent == 90
    assert s.activity_remind_days == 3
    assert s.fail_notify_threshold == 3


def test_dedup_roundtrip(tmp_path):
    d = ReminderDedup(str(tmp_path / "t.db"))
    assert d.already_sent("k1") is False
    d.mark_sent("k1")
    assert d.already_sent("k1") is True
    assert d.already_sent("k2") is False


def test_dedup_persists_across_instances(tmp_path):
    db = str(tmp_path / "t.db")
    ReminderDedup(db).mark_sent("k1")
    assert ReminderDedup(db).already_sent("k1") is True
