from fastapi.testclient import TestClient
from game_assistant.api import create_app
from game_assistant.config import Settings


def test_health(tmp_path):
    app = create_app(settings=Settings(db_path=str(tmp_path / 'health.db'),
        wuwa_enabled=False, nte_enabled=False, lol_enabled=False, notify_send_key=''),
        start_scheduler=False)
    client = TestClient(app, base_url="http://127.0.0.1:8010")
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "game-assistant"}
