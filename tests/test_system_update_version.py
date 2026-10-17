import json
import os
import subprocess
from pathlib import Path
import pytest

from game_assistant import system_update_version as versions
from game_assistant.system_update_version import (capture_version, source_root,
    release_root_matches, REPOSITORY)

SHA = 'a' * 40
OTHER = 'b' * 40


def marker(root, sha=SHA):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'release.json').write_text(json.dumps({'schema': 1, 'commit': sha,
        'frontend_commit': sha, 'source': REPOSITORY, 'branch': 'main'}))
    dist = root / 'frontend' / 'dist'
    dist.mkdir(parents=True, exist_ok=True)
    (dist / 'build-info.json').write_text(json.dumps({'schema': 1, 'commit': sha,
        'source': REPOSITORY, 'mode': 'cloud'}))
    return root


def test_module_source_root_outranks_cwd_and_wheels_use_release_working_directory(tmp_path):
    source, cwd = tmp_path / 'source', tmp_path / 'release'
    for root in [source, cwd]:
        root.mkdir()
        (root / 'pyproject.toml').write_text('[project]\nname="game-assistant"\n')
    assert source_root(source / 'src/game_assistant/system_update_version.py', cwd) == source
    assert source_root(tmp_path / 'site-packages/game_assistant/versions.py', cwd) == cwd


def test_startup_commit_does_not_follow_disk_updates_and_frontend_marker_is_checked_live(tmp_path):
    root = marker(tmp_path / 'release')
    version = capture_version(root)
    assert version.commit == SHA and version.ready
    marker(root, OTHER)
    assert version.commit == SHA
    assert version.health() == {'commit': SHA, 'frontend_commit': OTHER}
    assert version.ready is False
    assert version.disk_state() == (None, None)


def test_frontend_missing_or_wrong_commit_never_claims_ready(tmp_path):
    root = marker(tmp_path)
    (root / 'frontend/dist/build-info.json').unlink()
    version = capture_version(root)
    assert version.commit == SHA and version.frontend_commit is None and not version.ready
    marker(root)
    (root / 'frontend/dist/build-info.json').write_text(json.dumps({'schema': 1, 'commit': OTHER, 'source': REPOSITORY}))
    assert not capture_version(root).ready


def test_invalid_manifest_provenance_never_falls_back_to_claiming_a_main_release(tmp_path):
    root = marker(tmp_path)
    metadata = json.loads((root / 'release.json').read_text())
    for key, value in [('source', 'someone/else'), ('branch', 'feature'), ('schema', True), ('frontend_commit', OTHER)]:
        (root / 'release.json').write_text(json.dumps({**metadata, key: value}))
        assert capture_version(root).commit is None


def test_package_embedded_commit_is_not_assumed_to_be_a_main_installation(tmp_path, monkeypatch):
    package = tmp_path / 'site-packages' / 'game_assistant'
    package.mkdir(parents=True)
    monkeypatch.setattr(versions, '__file__', str(package / 'system_update_version.py'))
    monkeypatch.setattr(versions, 'source_root', lambda: None)
    (package / 'build-info.json').write_text(json.dumps({'schema': 1, 'source': REPOSITORY, 'commit': SHA}))
    version = capture_version()
    assert version.commit == SHA and version.root is None and not version.manifest_valid
    assert not release_root_matches(version.root, tmp_path)


def test_only_explicit_actual_release_locations_match_operator_install_root(tmp_path):
    install = tmp_path / 'installation'
    install.mkdir()
    assert release_root_matches(install, install)
    for releases in [install / 'releases', install / 'data/system-update/releases']:
        root = marker(releases / SHA)
        assert release_root_matches(root, install)
        assert not release_root_matches(marker(releases / 'not-a-commit'), install)
    assert not release_root_matches(marker(tmp_path / SHA), install)


def test_real_git_dirty_state_and_startup_head_are_not_replaced_by_later_git_commit(tmp_path):
    root = tmp_path / 'git'
    root.mkdir()
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True).stdout.decode().strip()
    git('init', '-q')
    git('config', 'user.name', 'Synthetic test')
    git('config', 'user.email', 'fixture@example.invalid')
    (root / 'tracked.py').write_text('one')
    git('add', 'tracked.py')
    git('commit', '-qm', 'one')
    first = capture_version(root)
    assert first.startup_dirty is False
    (root / 'tracked.py').write_text('two')
    assert first.public()['dirty'] is True
    git('add', 'tracked.py')
    git('commit', '-qm', 'two')
    assert first.commit != git('rev-parse', 'HEAD')
    assert first.public()['dirty'] is True


def test_git_state_handles_other_owner_without_persisting_trust_or_running_fsmonitor(tmp_path, monkeypatch):
    # CI hosts may globally trust every checkout. The control must exercise
    # Git's default ownership boundary, independently of host policy.
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)
    root = tmp_path / 'release'
    root.mkdir()
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True).stdout.decode().strip()
    git('init', '-q')
    git('config', 'user.name', 'Synthetic test')
    git('config', 'user.email', 'fixture@example.invalid')
    (root / '.gitignore').write_text((Path(__file__).parents[1] / '.gitignore').read_text())
    (root / 'tracked.py').write_text('one')
    git('add', '.gitignore', 'tracked.py')
    git('commit', '-qm', 'one')
    head = git('rev-parse', 'HEAD')
    hook = tmp_path / 'fsmonitor'
    invoked = tmp_path / 'fsmonitor-ran'
    hook.write_text(f'#!/bin/sh\ntouch "{invoked.as_posix()}"\n')
    hook.chmod(0o700)
    git('config', 'core.fsmonitor', hook.as_posix())
    config_before = (root / '.git/config').read_bytes()
    monkeypatch.setenv('GIT_TEST_ASSUME_DIFFERENT_OWNER', '1')
    # Git's ownership guard is active, as it is for root-owned Linux releases.
    plain = subprocess.run(['git', '-C', str(root), 'status', '--porcelain'], capture_output=True)
    assert plain.returncode != 0 and b'dubious ownership' in plain.stderr
    assert versions.git_state(root) == (head, False)
    assert not invoked.exists()
    assert (root / '.git/config').read_bytes() == config_before
    # Generated release/backend/frontend identity files do not block the next update.
    marker(root, head)
    package = root / 'src/game_assistant'
    package.mkdir(parents=True)
    (package / 'build-info.json').write_text('{}')
    assert versions.git_state(root) == (head, False)
    (root / 'tracked.py').write_text('changed')
    assert versions.git_state(root) == (head, True)


@pytest.mark.parametrize('embedded_commit',[SHA,None])
def test_installed_wheel_cannot_inherit_a_new_checkout_or_release_identity(tmp_path,monkeypatch,embedded_commit):
    root = tmp_path / 'release'
    root.mkdir()
    (root/'pyproject.toml').write_text('[project]\nname="game-assistant"\n')
    (root/'.gitignore').write_text('.venv/\ndist/\n')
    def git(*args):
        return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True).stdout.decode().strip()
    git('init','-q')
    git('config','user.name','Synthetic test')
    git('config','user.email','fixture@example.invalid')
    git('add','pyproject.toml','.gitignore')
    git('commit','-qm','new source')
    current = git('rev-parse','HEAD')
    marker(root,current)
    package = root/'.venv/lib/site-packages/game_assistant'
    package.mkdir(parents=True)
    monkeypatch.setattr(versions,'__file__',str(package/'system_update_version.py'))
    monkeypatch.chdir(root)
    if embedded_commit:
        (package/'build-info.json').write_text(json.dumps({'schema':1,'source':REPOSITORY,'commit':embedded_commit}))
    running = capture_version()
    assert running.root == root and running.commit == embedded_commit
    assert running.health() == {'commit':embedded_commit,'frontend_commit':current}
    assert running.ready is False
    # Even matching the stale wheel's frontend cannot validate the newer tree.
    marker(root,embedded_commit or SHA)
    assert not capture_version().ready
    marker(root,current)
    assert capture_version(root).commit == current and capture_version(root).ready
    # An editable source package does identify the actual checked-out source.
    source = root/'src/game_assistant'
    source.mkdir(parents=True)
    monkeypatch.setattr(versions,'__file__',str(source/'system_update_version.py'))
    assert capture_version().commit == current and capture_version().ready
