from pathlib import Path
import shutil

import pytest
from fastapi.testclient import TestClient

from game_assistant import system_update_version as versions
from game_assistant.cloud_runtime import load_runtime, build_app, RuntimeConfigurationError
from game_assistant.cloud_web_ui import validate_dist
from tests.test_cloud_operations import fixture
from tests.test_system_update_version import marker, SHA


def configure(config, install, enabled=True, old_dist=None):
    text = config.read_text()
    settings = f'system_update_enabled={str(enabled).lower()}\nsystem_update_install_root="{install.as_posix()}"\n'
    text = text.replace('[runtime]', settings+'[runtime]')
    if old_dist is not None:
        text += f'frontend_dist="{old_dist.as_posix()}"\n'
    config.write_text(text)


def test_enabled_update_uses_actual_matching_release_assets_and_health_identity(tmp_path, monkeypatch):
    _,_,_,config = fixture(tmp_path)
    install = tmp_path/'installation'
    active = marker(install/'releases'/SHA)
    active_dist = active/'frontend/dist'
    (active_dist/'index.html').write_text('<html data-service-mode="cloud">current</html>')
    old = tmp_path/'old-dist'
    old.mkdir()
    (old/'index.html').write_text('<html data-service-mode="cloud">old</html>')
    configure(config, install, old_dist=old)
    monkeypatch.setattr(versions, 'source_root', lambda: active)
    runtime = load_runtime(config)
    assert runtime.frontend_dist == active_dist
    assert validate_dist(active_dist) == active_dist
    with TestClient(build_app(runtime,start_scheduler=False),base_url='https://localhost:8443') as client:
        assert 'current' in client.get('/').text
        health = client.get('/api/health')
        assert health.status_code == 200 and health.json()['ready'] is True
        assert health.json()['version'] == {'commit':SHA,'frontend_commit':SHA}
        assert client.get('/build-info.json').json()['commit'] == SHA


@pytest.mark.parametrize('enabled,matching', [(False,True),(True,False)])
def test_assets_are_not_guessed_without_enabled_and_matching_install_root(tmp_path,monkeypatch,enabled,matching):
    _,_,_,config = fixture(tmp_path)
    install = tmp_path/'installation'
    active = marker(install/'releases'/SHA)
    other = tmp_path/'different-install'
    other.mkdir()
    old = tmp_path/'old-dist'
    old.mkdir()
    (old/'index.html').write_text('<html data-service-mode="cloud">old</html>')
    configure(config, install if matching else other, enabled=enabled, old_dist=old)
    monkeypatch.setattr(versions,'source_root',lambda:active)
    assert load_runtime(config).frontend_dist == old


def test_current_release_assets_still_reject_symlinks_and_data_overlap(tmp_path,monkeypatch):
    _,_,_,config = fixture(tmp_path)
    install = tmp_path/'installation'
    active = marker(install/'releases'/SHA)
    configure(config,install)
    monkeypatch.setattr(versions,'source_root',lambda:active)
    dist = active/'frontend/dist'
    shutil.rmtree(dist)
    outside = tmp_path/'elsewhere'
    outside.mkdir()
    try:
        dist.symlink_to(outside,target_is_directory=True)
    except OSError:
        pytest.skip('symlink creation unavailable')
    with pytest.raises(RuntimeConfigurationError,match='symlink_path_rejected'):
        load_runtime(config)
    dist.unlink()
    # Root itself matching the configured install path never bypasses data overlap checks.
    data_root = tmp_path/'live'
    monkeypatch.setattr(versions,'source_root',lambda:data_root)
    text=config.read_text().replace(install.as_posix(),data_root.as_posix())
    config.write_text(text)
    with pytest.raises(RuntimeConfigurationError,match='frontend_data_overlap'):
        load_runtime(config)
