import importlib.util

from fastapi.testclient import TestClient


def test_sandbox_ignores_credentials_and_disables_upstream(tmp_path, monkeypatch):
    monkeypatch.setenv("GA_WUWA_TOKEN", "test-secret-must-not-load")
    monkeypatch.setenv("GA_NOTIFY_SEND_KEY", "test-notify-must-not-load")
    monkeypatch.setenv("GA_DB_PATH", str(tmp_path / "do-not-touch.db"))
    assert importlib.util.find_spec("game_assistant.runtime"), "runtime runner missing"
    from game_assistant.runtime import build_app

    app = build_app(tmp_path / "sandbox")
    assert app.state.settings.wuwa_token == ""
    assert app.state.settings.notify_send_key == ""
    assert app.state.scheduler is None
    assert app.state.registry.all() == []
    assert not (tmp_path / "do-not-touch.db").exists()
    assert (tmp_path / "sandbox" / "assistant.db").exists()
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/games").json() == []
