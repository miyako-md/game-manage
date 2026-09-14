"""Opt-in real Windows process checks; never uses the personal service port."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    os.name != "nt" or os.environ.get("GA_RUN_RUNTIME_TESTS") != "1",
    reason="opt-in isolated Windows process checks: GA_RUN_RUNTIME_TESTS=1",
)


def script(name, port):
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(ROOT / "scripts" / f"{name}.ps1"), "-Sandbox", "-Port", str(port)],
        cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=55,
    )


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_lifecycle_repeated_start_and_pid_creation_guard():
    assert (ROOT / "scripts" / "start.ps1").is_file(), "start script missing"
    port = free_port()
    state_path = ROOT / "data" / "runtime" / f"sandbox-{port}" / "service.json"
    try:
        started = script("start", port)
        assert started.returncode == 0, started.stdout + started.stderr
        initial = json.loads(state_path.read_text(encoding="utf-8-sig"))
        again = script("start", port)
        assert again.returncode == 0, again.stdout + again.stderr
        assert json.loads(state_path.read_text(encoding="utf-8-sig"))["pid"] == initial["pid"]
        status = script("status", port)
        assert status.returncode == 0, status.stdout + status.stderr
        # A leftover stop request from another run must not stop this process.
        (state_path.parent / "stop.json").write_text(json.dumps({"runtime_id": "0" * 32}), encoding="utf-8")
        time.sleep(0.7)
        assert script("status", port).returncode == 0
        state_path.write_text(json.dumps({**initial, "creation_ticks": "1"}), encoding="utf-8")
        refused = script("stop", port)
        assert refused.returncode != 0
        state_path.write_text(json.dumps(initial), encoding="utf-8")
        assert script("status", port).returncode == 0
        restarted = script("restart", port)
        assert restarted.returncode == 0, restarted.stdout + restarted.stderr
        assert json.loads(state_path.read_text(encoding="utf-8-sig"))["runtime_id"] != initial["runtime_id"]
    finally:
        stopped = script("stop", port)
        assert stopped.returncode == 0, stopped.stdout + stopped.stderr
    assert script("stop", port).returncode == 0
    assert not state_path.exists()
    assert "Application shutdown complete" in (state_path.parent / "service.log").read_text(encoding="utf-8")
    shutil.rmtree(state_path.parent)


def test_occupied_port_refuses_start_and_leaves_foreign_listener_alive():
    assert (ROOT / "scripts" / "start.ps1").is_file(), "start script missing"
    port = free_port()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))
        listener.listen()
        result = script("start", port)
        assert result.returncode != 0
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            pass
    runtime_dir = ROOT / "data" / "runtime" / f"sandbox-{port}"
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)


def test_current_user_autostart_is_idempotent_and_reversible():
    assert (ROOT / "scripts" / "autostart.ps1").is_file(), "autostart script missing"

    def invoke(action):
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(ROOT / "scripts" / "autostart.ps1"), action],
            cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=20,
        )

    before = invoke("-Status")
    assert before.returncode == 0, before.stdout + before.stderr
    if "Enabled:" in before.stdout:
        pytest.skip("preserving an existing enabled startup entry")
    try:
        for _ in range(2):
            enabled = invoke("-Enable")
            assert enabled.returncode == 0, enabled.stdout + enabled.stderr
        assert "Enabled:" in invoke("-Status").stdout
    finally:
        disabled = invoke("-Disable")
        assert disabled.returncode == 0, disabled.stdout + disabled.stderr
    assert invoke("-Disable").returncode == 0
    assert "Disabled:" in invoke("-Status").stdout
