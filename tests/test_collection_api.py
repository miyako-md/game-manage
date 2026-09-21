from fastapi.testclient import TestClient

from game_assistant.api import create_app
from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult
from game_assistant.registry import GameRegistry
from game_assistant.snapshots import SnapshotStore


class SampleAdapter(BaseGameAdapter):
    game_id = "sample"
    display_name = "测试游戏"
    section = "mobile"
    capabilities = [Capability.STAMINA, Capability.ANNOUNCEMENT]


def build(tmp_path):
    settings = Settings(db_path=str(tmp_path / "data.db"))
    store = SnapshotStore(settings.db_path)
    registry = GameRegistry()
    registry.register(SampleAdapter())
    return TestClient(create_app(registry=registry, store=store, settings=settings, start_scheduler=False), base_url="http://127.0.0.1:8010"), store


def test_collection_status_includes_never_attempted_registered_capabilities(tmp_path):
    client, _ = build(tmp_path)
    body = client.get("/api/status").json()
    assert body["notify"]["enabled"] is False
    rows = body["collection"]
    assert {(r["game_id"], r["capability"], r["state"]) for r in rows} == {
        ("sample", "stamina", "never"), ("sample", "announcement", "never")}
    assert all(r["last_attempt_at"] is None and r["last_success_at"] is None for r in rows)


def test_failed_collection_keeps_payload_and_makes_source_state_visible(tmp_path):
    client, store = build(tmp_path)
    store.save("sample", "stamina", '{"current":12,"maximum":240}')
    store.record_poll("sample", "stamina", FetchResult(ok=False, error="上游返回异常", error_kind="source_error"))
    snapshot = client.get("/api/games/sample/snapshot/stamina").json()
    assert snapshot["payload"]["current"] == 12
    assert snapshot["stale"] is True
    assert snapshot["poll_status"]["state"] == "error"
    assert snapshot["poll_status"]["consecutive_failures"] == 1
    assert snapshot["poll_status"]["last_success_at"] == snapshot["fetched_at"]
    assert snapshot["poll_status"]["error"] == "上游返回异常"
    row = next(row for row in client.get("/api/status").json()["collection"] if row["capability"] == "stamina")
    assert row["state"] == "error"


def test_no_successful_snapshot_can_still_report_offline_state(tmp_path):
    client, store = build(tmp_path)
    store.record_poll("sample", "stamina", FetchResult(ok=False, error="客户端未运行", error_kind="offline"))
    snapshot = client.get("/api/games/sample/snapshot/stamina").json()
    assert snapshot["payload"] is None
    assert snapshot["poll_status"]["state"] == "offline"
    assert snapshot["poll_status"]["consecutive_failures"] == 0


def test_status_observation_time_exposes_newer_clear_without_faking_an_attempt(tmp_path):
    client, store = build(tmp_path)
    store.record_poll("sample", "stamina", FetchResult(ok=False, error="已失效", error_kind="auth_expired"))
    previous = client.get("/api/games/sample/snapshot/stamina").json()["poll_status"]
    store.clear_private("sample")
    current = next(row for row in client.get("/api/status").json()["collection"] if row["capability"] == "stamina")
    assert current["state"] == "never"
    assert current["last_attempt_at"] is None
    assert current["observed_at"] >= previous["observed_at"]
