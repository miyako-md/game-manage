"""Serving a SPA must not turn missing assets/API routes into successful HTML."""
import importlib.util

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def ui(tmp_path):
    assert importlib.util.find_spec("game_assistant.web_ui"), "web UI installer missing"
    from game_assistant.web_ui import install_web_ui

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>game dashboard</html>", encoding="utf-8")
    (dist / "assets" / "main.js").write_text("window.ready = true", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("private", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "game-assistant"}

    install_web_ui(app, dist)
    return TestClient(app), dist


def test_root_and_navigation_serve_spa(ui):
    client, _ = ui
    for url in ("/", "/calendar", "/games/wuwa"):
        response = client.get(url)
        assert response.status_code == 200
        assert "game dashboard" in response.text
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["cache-control"] == "no-cache"


def test_static_asset_is_served(ui):
    client, _ = ui
    response = client.get("/assets/main.js")
    assert response.status_code == 200
    assert response.text == "window.ready = true"
    assert "javascript" in response.headers["content-type"]


@pytest.mark.parametrize("url", ["/api", "/api/missing", "/api/health/missing", "/assets/missing.js", "/missing.ico", "/assets/missing", "/%2e%2e/secret.txt", "/..%5csecret.txt"])
def test_unknown_api_assets_and_traversal_are_404(ui, url):
    client, _ = ui
    response = client.get(url)
    assert response.status_code == 404
    assert "game dashboard" not in response.text
    assert "private" not in response.text


def test_api_route_keeps_priority(ui):
    client, _ = ui
    assert client.get("/api/health").json()["service"] == "game-assistant"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_unknown_api_methods_are_404(ui, method):
    client, _ = ui
    assert client.request(method, "/api/not-registered").status_code == 404


def test_static_head_response(ui):
    client, _ = ui
    response = client.head("/assets/main.js")
    assert response.status_code == 200
    assert response.content == b""


def test_missing_dist_keeps_api_available(tmp_path):
    assert importlib.util.find_spec("game_assistant.web_ui"), "web UI installer missing"
    from game_assistant.web_ui import install_web_ui

    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    install_web_ui(app, tmp_path / "not-built")
    client = TestClient(app)
    assert client.get("/").status_code == 404
    assert client.get("/api/health").json() == {"status": "ok"}


def test_symlink_asset_outside_dist_is_not_exposed(ui, tmp_path):
    client, dist = ui
    try:
        (dist / "assets" / "secret.txt").symlink_to(tmp_path / "secret.txt")
    except OSError:
        pytest.skip("symlink creation requires Windows developer mode or permission")
    assert client.get("/assets/secret.txt").status_code == 404
