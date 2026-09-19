"""Run the dependency installer in temporary folders, without npm/network/runtime."""
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows launcher")


@pytest.fixture
def frontend(tmp_path):
    (tmp_path / "package.json").write_text('{}')
    (tmp_path / "package-lock.json").write_text('{}')
    vite = tmp_path / "node_modules/vite/package.json"
    vite.parent.mkdir(parents=True)
    vite.write_text('{}')
    (tmp_path / "npm.cmd").write_text(
        '@echo off\nif not "%1"=="ci" exit /b 9\n'
        'echo installed>> installs.txt\n'
        'if exist fail exit /b 1\n'
        'if not exist node_modules\\vite mkdir node_modules\\vite\n'
        'echo {}> node_modules\\vite\\package.json\nexit /b 0\n'
    )
    return tmp_path


def install(frontend):
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"
    command = (
        "$ErrorActionPreference = 'Stop'; "
        f". {quote(ROOT / 'scripts/frontend-dependencies.ps1')}; "
        f"Ensure-FrontendDependencies -Frontend {quote(frontend)} "
        f"-NpmPath {quote(frontend / 'npm.cmd')}"
    )
    return subprocess.run(
        ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command],
        capture_output=True, text=True, errors='replace', timeout=20,
    )


def assert_installed(frontend):
    result = install(frontend)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'True' in result.stdout


def test_missing_stamp_installs_even_with_existing_vite_then_reuses(frontend):
    assert_installed(frontend)
    result = install(frontend)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'False' in result.stdout
    assert (frontend / 'installs.txt').read_text().splitlines() == ['installed']


@pytest.mark.parametrize('changed', ['package-lock.json', 'package.json'])
def test_changed_manifest_reinstalls_with_vite_already_present(frontend, changed):
    assert_installed(frontend)
    (frontend / changed).write_text('{"changed":true}')
    assert_installed(frontend)
    assert len((frontend / 'installs.txt').read_text().splitlines()) == 2


def test_failed_install_invalidates_stamp_and_retries(frontend):
    assert_installed(frontend)
    stamp = frontend / 'node_modules/.game-assistant-deps.sha256'
    assert stamp.is_file()
    old_lock = (frontend / 'package-lock.json').read_text()
    (frontend / 'package-lock.json').write_text('{"changed":true}')
    (frontend / 'fail').touch()
    result = install(frontend)
    assert result.returncode != 0
    assert not stamp.exists()
    # Even a rollback to the old lock must reinstall after a partial failure.
    (frontend / 'package-lock.json').write_text(old_lock)
    (frontend / 'fail').unlink()
    assert_installed(frontend)
    assert len((frontend / 'installs.txt').read_text().splitlines()) == 3


def test_missing_vite_reinstalls_despite_matching_stamp(frontend):
    assert_installed(frontend)
    (frontend / 'node_modules/vite/package.json').unlink()
    assert_installed(frontend)
    assert (frontend / 'node_modules/vite/package.json').is_file()
