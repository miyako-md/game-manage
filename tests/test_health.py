from fastapi.testclient import TestClient
from game_assistant.main import app


def test_health():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "game-assistant"}
