from datetime import datetime, timezone

from fastapi.testclient import TestClient

from game_assistant.api import create_app
from game_assistant.config import Settings
from game_assistant.models import FetchResult, MatchDetail, MatchParticipant, \
    MatchTeam, StaminaInfo
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
    client = TestClient(create_app(
        registry=FakeRegistry(DummyAdapter()), store=store,
        settings=Settings(notify_send_key="", db_path=str(tmp_path / "unused.db"))), base_url="http://127.0.0.1:8010")
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


def test_status_notify_enabled_with_configured_settings(tmp_path):
    settings = Settings(notify_send_key="SK", db_path=str(tmp_path / "s.db"))
    client = TestClient(create_app(registry=FakeRegistry(DummyAdapter()),
                                   settings=settings, start_scheduler=False), base_url="http://127.0.0.1:8010")
    notify = client.get("/api/status").json()["notify"]
    assert notify["enabled"] is True
    assert notify["provider"] == "serverchan"


class DetailAdapter(DummyAdapter):
    """带 fetch_match_detail 的适配器（模拟 LoL）。"""

    def __init__(self):
        super().__init__()
        self.requested = None

    async def fetch_match_detail(self, match_id: str) -> FetchResult:
        self.requested = match_id
        if getattr(self, "fail", False):
            return FetchResult(ok=False, error="LOL 客户端未运行")
        detail = MatchDetail(
            match_id="987654321", mode="CLASSIC",
            start_at=datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc),
            duration_seconds=2135,
            teams=[MatchTeam(team_id=100, win=True, participants=[
                MatchParticipant(champion_id=157, level=18, kills=8, deaths=3,
                                 assists=10, items=[1001, 3003], damage=20030,
                                 gold=12000, win=True, team_id=100, is_own=True),
            ])],
        )
        return FetchResult(ok=True, payload=detail)


def _client_with(adapter, tmp_path):
    return TestClient(create_app(
        registry=FakeRegistry(adapter), store=SnapshotStore(str(tmp_path / "t.db")),
        settings=Settings(notify_send_key="", db_path=str(tmp_path / "unused.db"))), base_url="http://127.0.0.1:8010")


def test_match_detail_unregistered_game(tmp_path):
    client = _client_with(DummyAdapter(), tmp_path)
    assert client.get("/api/games/nope/match/123/detail").status_code == 404


def test_match_detail_not_supported_for_non_lol_adapter(tmp_path):
    # DummyAdapter 沿用基类的 fetch_match_detail → 404"该游戏不支持对局详情"
    client = _client_with(DummyAdapter(), tmp_path)
    resp = client.get("/api/games/dummy/match/123/detail")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "该游戏不支持对局详情"


def test_match_detail_ok_serializes_payload(tmp_path):
    a = DetailAdapter()
    client = _client_with(a, tmp_path)
    resp = client.get("/api/games/dummy/match/987654321/detail")
    assert resp.status_code == 200
    assert a.requested == "987654321"
    body = resp.json()
    assert "error" not in body
    p = body["payload"]
    assert p["match_id"] == "987654321" and p["mode"] == "CLASSIC"
    assert p["start_at"] == "2026-09-13T12:00:00Z"  # mode="json" 序列化
    assert p["teams"][0]["participants"][0]["is_own"] is True
    assert p["teams"][0]["participants"][0]["items"] == [1001, 3003]


def test_match_detail_error_passthrough(tmp_path):
    a = DetailAdapter()
    a.fail = True
    client = _client_with(a, tmp_path)
    resp = client.get("/api/games/dummy/match/987654321/detail")
    assert resp.status_code == 200
    assert resp.json() == {"error": "LOL 客户端未运行"}
