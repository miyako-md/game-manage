from game_assistant.snapshots import SnapshotStore


def test_save_and_get(tmp_path):
    store = SnapshotStore(str(tmp_path / "t.db"))
    store.save("wuwa", "stamina", '{"current": 180}')
    snap = store.get("wuwa", "stamina")
    assert snap["payload"] == '{"current": 180}'
    assert "fetched_at" in snap


def test_upsert_overwrites(tmp_path):
    store = SnapshotStore(str(tmp_path / "t.db"))
    store.save("wuwa", "stamina", '{"current": 180}')
    store.save("wuwa", "stamina", '{"current": 200}')
    assert store.get("wuwa", "stamina")["payload"] == '{"current": 200}'


def test_get_missing_returns_none(tmp_path):
    store = SnapshotStore(str(tmp_path / "t.db"))
    assert store.get("wuwa", "stamina") is None
