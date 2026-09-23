from fastapi.testclient import TestClient

from game_assistant.api import create_app
from game_assistant.config import Settings
from game_assistant.scheduler import PollingScheduler
from game_assistant.snapshots import SnapshotStore
from tests.test_reminder import FakeNotify


def test_refresh_endpoint(tmp_path):
    settings = Settings(db_path=str(tmp_path / "t.db"))
    store = SnapshotStore(settings.db_path)
    registry = build_dummy_registry()
    sched = PollingScheduler(registry, store, settings, FakeNotify())
    client = TestClient(create_app(registry=registry, store=store, settings=settings,
                                   scheduler=sched, notifier=FakeNotify()), base_url="http://127.0.0.1:8010")
    resp = client.post("/api/games/dummy/refresh", headers={'X-Game-Assistant': '1'})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results["stamina"]["ok"] is True
    assert client.get("/api/games/dummy/snapshot/stamina").json()["fetched_at"] is not None


def test_refresh_unknown_game(tmp_path):
    settings = Settings(db_path=str(tmp_path / "t.db"))
    store = SnapshotStore(settings.db_path)
    client = TestClient(create_app(registry=build_dummy_registry(), store=store, settings=settings,
                                   scheduler=None, notifier=None), base_url="http://127.0.0.1:8010")
    assert client.post("/api/games/nope/refresh", headers={'X-Game-Assistant': '1'}).status_code == 404


def build_dummy_registry():
    from tests.test_registry import DummyAdapter
    from game_assistant.registry import GameRegistry
    reg = GameRegistry()
    reg.register(DummyAdapter())
    return reg
