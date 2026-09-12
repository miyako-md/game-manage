from fastapi.testclient import TestClient

from game_assistant.api import create_app
from game_assistant.models import StaminaInfo
from game_assistant.snapshots import SnapshotStore
from tests.test_registry import DummyAdapter


class FakeRegistry:
    def __init__(self, adapter):
        self._adapter = adapter

    def all(self):
        return [self._adapter]

    def get(self, game_id):
        if game_id != self._adapter.game_id:
            raise KeyError(game_id)
        return self._adapter


def _app_with(tmp_path, snapshots=None):
    store = SnapshotStore(str(tmp_path / "t.db"))
    for gid, cap, payload in (snapshots or []):
        store.save(gid, cap, payload)
    client = TestClient(create_app(registry=FakeRegistry(DummyAdapter()), store=store))
    return client, store


def test_list_games(tmp_path):
    client, _ = _app_with(tmp_path)
    resp = client.get("/api/games")
    assert resp.status_code == 200
    g = resp.json()[0]
    assert g["game_id"] == "dummy" and g["section"] == "pc"
    assert g["capabilities"] == ["stamina"]


def test_snapshot_roundtrip(tmp_path):
    client, store = _app_with(tmp_path)
    store.save("dummy", "stamina", StaminaInfo(
        current=100, maximum=240, expected_full_at=None,
        updated_at="2026-09-12T12:00:00").model_dump_json())
    resp = client.get("/api/games/dummy/snapshot/stamina")
    assert resp.status_code == 200
    body = resp.json()
    assert body["payload"]["current"] == 100
    assert body["stale"] is False


def test_snapshot_missing_and_unknown_game(tmp_path):
    client, _ = _app_with(tmp_path)
    assert client.get("/api/games/dummy/snapshot/stamina").json()["payload"] is None
    assert client.get("/api/games/nope/snapshot/stamina").status_code == 404


def test_status_notify_disabled(tmp_path):
    client, _ = _app_with(tmp_path)
    assert client.get("/api/status").json()["notify"]["enabled"] is False
