"""PowerShell launch selection in a synthetic tree; no service or port is used."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='isolated Windows launcher check')


@pytest.mark.parametrize('rebuild,valid_manifest', [(False, True), (True, True), (False, False)])
def test_launch_uses_verified_active_release_without_rebuilding_original_tree(tmp_path, rebuild, valid_manifest):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copy2(ROOT / 'scripts/launch.ps1', scripts / 'launch.ps1')
    runtime = (ROOT / 'scripts/runtime-common.ps1').read_text(encoding='utf-8')
    # Real initialization/manifest validation; stop before any process/network action.
    runtime += "\nfunction Invoke-LocalRuntime { throw ('ISOLATED_ACTIVE_START:' + $script:SourceRoot) }\n"
    (scripts / 'runtime-common.ps1').write_text(runtime, encoding='utf-8')
    (scripts / 'frontend-dependencies.ps1').write_text("throw 'UNEXPECTED_DEPENDENCY_BUILD'\n", encoding='utf-8')
    commit = 'a' * 40
    active = tmp_path / 'data/system-update/releases' / commit
    (active / '.venv/Scripts').mkdir(parents=True)
    (active / '.venv/Scripts/python.exe').write_bytes(b'not executed')
    (active / 'frontend/dist').mkdir(parents=True)
    (active / 'frontend/dist/index.html').write_text('<div id="app"></div>')
    (active / 'release.json').write_text(json.dumps({'schema': 1, 'commit': commit,
        'frontend_commit': commit if valid_manifest else 'b' * 40,
        'source': 'miyako-md/game-manage', 'branch': 'main'}))
    runtime_dir = tmp_path / 'data/runtime'
    runtime_dir.mkdir()
    (runtime_dir / 'active-release.json').write_text(json.dumps({'schema': 1, 'commit': commit}))
    command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
               '-File', str(scripts / 'launch.ps1'), '-NoBrowser']
    if rebuild:
        command.append('-Rebuild')
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=20)
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert 'UNEXPECTED_DEPENDENCY_BUILD' not in output
    if not valid_manifest:
        assert 'Active release identity mismatch' in output
    elif rebuild:
        assert '-Rebuild cannot rebuild or switch this release' in output
    else:
        assert 'ISOLATED_ACTIVE_START:' + str(active) in output
    assert not (tmp_path / '.venv').exists()
    assert not (tmp_path / 'frontend').exists()
