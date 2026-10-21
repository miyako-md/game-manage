"""Exercise the API service/worker disk protocol without changing a real install."""
import time

import pytest

from game_assistant.config import Settings
from game_assistant.system_update import GITHUB_ROOT, SystemUpdateService, UpdateError
from game_assistant.system_update_protocol import read_json, write_json_atomic
from game_assistant.system_update_version import REPOSITORY, capture_version
from tests.test_system_update_worker import installation


@pytest.mark.parametrize('new_health', [True, False])
def test_checked_request_survives_api_restart_and_worker_result_uses_real_version_files(installation, new_health):
    f = installation
    dist = f.root / 'frontend/dist'
    dist.mkdir()
    write_json_atomic(dist / 'build-info.json', {'schema': 1, 'source': REPOSITORY, 'commit': f.old})
    settings = Settings(system_update_enabled=True, system_update_install_root=str(f.root),
                        system_update_state_dir=str(f.state))

    def fetch(url):
        assert url == GITHUB_ROOT + '/commits/main?per_page=1'
        return {'sha': f.target, 'commit': {'message': 'Isolated next release',
                'committer': {'date': '2026-10-18T00:00:00Z'}}}

    def api(root):
        return SystemUpdateService(settings, version=capture_version(root), fetch=fetch,
                                   platform_name='windows')

    # The real heartbeat and check make the real service eligible to publish.
    f.worker.heartbeat()
    service = api(f.root)
    assert service.check()['can_apply'] is True
    queued = service.apply(f.old, f.target)
    assert queued['job']['phase'] == 'queued'
    assert api(f.root).status()['job'] == queued['job']
    assert f.worker.claim() is True
    assert api(f.root).status()['job']['phase'] == 'preparing'
    with pytest.raises(UpdateError, match='job_active'):
        api(f.root).apply(f.old, f.target)

    # Only toolchain/OS control are substituted. Git history, queue, commit
    # manifests, backup and activation markers are the implementation under test.
    runner = f.runner

    def build(argv, **kwargs):
        result = runner(argv, **kwargs)
        if [str(arg) for arg in argv[:3]] == ['npm.cmd', 'run', 'build']:
            build_file = kwargs['cwd'] / 'dist/build-info.json'
            value = read_json(build_file)
            write_json_atomic(build_file, {**value, 'source': REPOSITORY})
        return result

    f.worker.run = build
    f.platform.fail_new_health = not new_health
    f.worker.execute()
    expected_phase = 'completed' if new_health else 'rolled_back'
    disk = read_json(f.state / 'status.json')
    assert disk['job_id'] == queued['job']['job_id']
    assert disk['phase'] == expected_phase
    assert time.time() - disk['finished_at'] < 10
    assert not (f.state / 'request.json').exists()
    active = f.worker.config.releases / f.target if new_health else f.root
    status = api(active).status()
    expected = f.target if new_health else f.old
    assert status['current'] == {'sha': expected, 'frontend_sha': expected, 'dirty': False}
    assert status['job']['phase'] == expected_phase
    assert capture_version(active).ready is True
    if new_health:
        # A process still running the old code cannot claim the completed target.
        stale = service.status()
        assert stale['unavailable_reason'] == 'running_version_mismatch'
        assert stale['current']['sha'] == f.old
    else:
        assert (f.root / 'data/database.txt').read_text() == 'original-data'
    assert (f.root / 'config.toml').read_text() == 'private configuration preserved'
