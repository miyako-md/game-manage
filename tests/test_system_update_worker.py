"""Isolated updater transactions. Never download/build/update a user installation."""
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from game_assistant.system_update_protocol import lock, read_json, write_json_atomic, LockBusyError
from game_assistant.system_update_worker import (Updater, WorkerConfig, Platform, UpdateError,
    OFFICIAL_REPO, OFFICIAL_REF, Runner, DataScope, backup_data, restore_data,
    clean_environment, build_environment, WindowsPlatform)


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env={**os.environ, 'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':os.devnull})
    return result.stdout.strip()


class BuildRunner:
    """Real local Git history, fake toolchain; fixed official URL is asserted."""
    def __init__(self, remote):
        self.remote = remote
        self.calls = []
        self.fail_build = False
        self.fail_command = None
        self.last_failure = None
        self.bad_frontend = False
        self.real = Runner()

    def __call__(self, argv, **kwargs):
        argv = [str(x) for x in argv]
        self.calls.append((argv[:], kwargs.copy()))
        if argv[0] == 'git':
            if 'fetch' in argv:
                assert OFFICIAL_REPO in argv
                assert OFFICIAL_REF + ':refs/remotes/official/main' in argv
                argv = [str(self.remote) if x == OFFICIAL_REPO else x for x in argv]
            return self.real(argv, **kwargs)
        env = kwargs.get('env', {})
        assert not any(key.startswith(('GA_SECRET', 'VITE_SECRET', 'GITHUB_TOKEN')) for key in env)
        cwd = Path(kwargs['cwd'])
        if argv[:2] == ['uv', 'sync']:
            assert '--locked' in argv
            (cwd / '.venv/Scripts').mkdir(parents=True)
            (cwd / '.venv/Scripts/python.exe').write_text('fake environment')
        elif argv[:3] == ['npm.cmd', 'run', 'build']:
            if self.fail_build: raise UpdateError('test_build_failed')
            if self.fail_command:
                self.last_failure = {'command': 'npm.cmd run build', 'returncode': 1, 'stderr': self.fail_command}
                raise UpdateError('command_failed')
            (cwd / 'dist').mkdir()
            (cwd / 'dist/index.html').write_text('<div id="app"></div>')
            write_json_atomic(cwd / 'dist/build-info.json', {'schema':1,
                'commit':'f'*40 if self.bad_frontend else env['GA_BUILD_COMMIT']})
        return SimpleNamespace(returncode=0, stdout='')


class FakePlatform(Platform):
    def __init__(self, config, run):
        super().__init__(config, run)
        self.events = []
        self.fail_new_health = False
        self.fail_old_health = False
        self.fail_qq = False
        self.qq = False
        self.locked = False

    def preflight(self, previous):
        self.events.append('preflight')
        return {'api_active':True, 'qq_active':self.qq, 'original':previous == self.config.install_root}

    def scopes(self):
        return [DataScope(self.config.install_root / 'data', frozenset({'runtime','system-update'}))]

    @contextmanager
    def transaction(self):
        assert not self.locked
        self.locked = True; self.events.append('lock')
        try: yield
        finally: self.events.append('unlock'); self.locked = False

    def stop(self, state):
        assert self.locked
        self.events.append('stop')

    def start(self, state):
        assert self.locked
        self.events.append('start')
        if (self.config.install_root / 'data/runtime/active-release.json').exists():
            (self.config.install_root / 'data/database.txt').write_text('new-version-data')

    def start_qq(self, state):
        assert self.locked
        self.events.append('start_qq')
        if self.fail_qq: raise UpdateError('test_qq_start_failed')

    def healthy(self, commit, *, previous=False):
        assert self.locked
        self.events.append('health_old' if previous else 'health_new')
        return not (self.fail_old_health if previous else self.fail_new_health)


@pytest.fixture
def installation(tmp_path):
    remote = tmp_path / 'official'; remote.mkdir()
    git(remote, 'init', '-b', 'main'); git(remote, 'config', 'user.email', 'test@example.invalid')
    git(remote, 'config', 'user.name', 'Isolated test')
    (remote / 'frontend').mkdir()
    for name, text in {'uv.lock':'fixture', 'pyproject.toml':'[project]\nname="fixture"\n',
        'frontend/package-lock.json':'{}', 'frontend/package.json':'{}',
        '.gitignore':'data/\n.venv/\nfrontend/dist/\nfrontend/node_modules/\nconfig.toml\n',
        'source.txt':'old'}.items():
        (remote / name).write_text(text)
    git(remote, 'add', '.'); git(remote, 'commit', '-m', 'base')
    old = git(remote, 'rev-parse', 'HEAD')
    root = tmp_path / 'installation'
    subprocess.run(['git','clone',str(remote),str(root)], check=True, capture_output=True)
    (remote / 'source.txt').write_text('new'); git(remote, 'add', '.'); git(remote, 'commit', '-m', 'next')
    target = git(remote, 'rev-parse', 'HEAD')
    state = root / 'data/system-update'; state.mkdir(parents=True)
    (root / 'data/runtime').mkdir()
    (root / 'data/database.txt').write_text('original-data')
    (root / 'config.toml').write_text('private configuration preserved')
    config = WorkerConfig('windows', root, state)
    runner = BuildRunner(remote); platform = FakePlatform(config, runner)
    worker = Updater(config, platform, runner)
    request = {'schema':1,'job_id':'1'*32,'target_sha':target,'expected_sha':old,
               'requested_at':1000,'source':'main'}
    return SimpleNamespace(root=root,state=state,remote=remote,old=old,target=target,
                           worker=worker,platform=platform,runner=runner,request=request)


def perform(f):
    write_json_atomic(f.state / 'request.json', f.request)
    assert f.worker.claim()
    f.worker.execute()
    return read_json(f.state / 'status.json')


def test_success_prepares_separate_venv_before_any_stop_and_verifies_exact_pair(installation, monkeypatch):
    f = installation
    monkeypatch.setenv('GA_SECRET', 'must-not-reach-build')
    monkeypatch.setenv('GITHUB_TOKEN', 'must-not-reach-build')
    result = perform(f)
    assert result['phase'] == 'completed'
    assert read_json(f.root / 'data/runtime/active-release.json')['commit'] == f.target
    assert git(f.root, 'rev-parse', 'HEAD') == f.old
    assert (f.root / 'config.toml').read_text() == 'private configuration preserved'
    release = f.worker.config.releases / f.target
    assert read_json(release / 'release.json')['frontend_commit'] == f.target
    assert f.platform.events == ['preflight','lock','preflight','stop','start','health_new','unlock']
    assert any(argv[:3] == ['npm.cmd','run','build'] for argv, _ in f.runner.calls)
    assert (f.worker.private / ('backup-' + f.request['job_id']) / '0/database.txt').read_text() == 'original-data'


@pytest.mark.parametrize('failure', ['build', 'frontend'])
def test_prepare_failure_never_stops_or_changes_old_installation(installation, failure):
    f = installation
    f.runner.fail_build = failure == 'build'; f.runner.bad_frontend = failure == 'frontend'
    result = perform(f)
    assert result['phase'] == 'failed'
    assert 'stop' not in f.platform.events
    assert not (f.root / 'data/runtime/active-release.json').exists()
    assert (f.root / 'data/database.txt').read_text() == 'original-data'


def test_health_failure_restores_data_and_old_marker_under_same_lock(installation):
    f = installation; f.platform.fail_new_health = True
    result = perform(f)
    assert result['phase'] == 'rolled_back'
    assert (f.root / 'data/database.txt').read_text() == 'original-data'
    assert not (f.root / 'data/runtime/active-release.json').exists()
    assert f.platform.events.count('lock') == 1
    assert f.platform.events[-4:] == ['stop','start','health_old','unlock']


def test_unprovable_restore_health_requires_operator_not_fake_success(installation):
    f = installation; f.platform.fail_new_health = f.platform.fail_old_health = True
    assert perform(f)['phase'] == 'recovery_required'


def test_qq_starts_only_after_api_verification_and_never_rolls_back_dedup_after_start(installation):
    f = installation; f.platform.qq = True; f.platform.fail_qq = True
    assert perform(f)['phase'] == 'recovery_required'
    assert f.platform.events.index('health_new') < f.platform.events.index('start_qq')
    assert 'health_old' not in f.platform.events
    assert (f.root / 'data/database.txt').read_text() == 'new-version-data'
    assert read_json(f.worker.journal_path)['external_side_effects_possible'] is True


@pytest.mark.parametrize('failure', ['dirty', 'wrong_target', 'wrong_expected', 'ahead'])
def test_wrong_target_dirty_checkout_and_nonancestor_never_stop(installation, failure):
    f = installation
    if failure == 'dirty': (f.root / 'source.txt').write_text('user edit')
    elif failure == 'wrong_target': f.request['target_sha'] = 'e' * 40
    elif failure == 'wrong_expected': f.request['expected_sha'] = 'e' * 40
    else:
        git(f.root, 'config', 'user.email', 'test@example.invalid'); git(f.root, 'config', 'user.name', 'Test')
        (f.root / 'local.txt').write_text('unmerged'); git(f.root, 'add', 'local.txt'); git(f.root, 'commit', '-m', 'local')
        f.request['expected_sha'] = git(f.root, 'rev-parse', 'HEAD')
    assert perform(f)['phase'] == 'failed'
    assert 'stop' not in f.platform.events


def test_repeated_completed_job_is_not_executed_twice(installation):
    f = installation; assert perform(f)['phase'] == 'completed'
    before = f.platform.events[:]
    write_json_atomic(f.state / 'request.json', f.request)
    assert f.worker.claim() is False
    assert f.platform.events == before
    assert not (f.state / 'request.json').exists()


@pytest.mark.parametrize('phase, expected', [('preparing','failed'),('stopping','recovery_required'),('verifying','recovery_required')])
def test_interrupted_private_journal_is_authoritative_not_public_status(installation, phase, expected):
    f = installation
    write_json_atomic(f.worker.journal_path, {'schema':1,'job_id':'2'*32,'target_sha':f.target,
        'previous_sha':f.old,'phase':phase,'updated_at':1})
    write_json_atomic(f.state / 'status.json', {'schema':1,'phase':'completed','previous_sha':'f'*40})
    assert f.worker.recover_interrupted() is (expected == 'recovery_required')
    assert read_json(f.state / 'status.json')['phase'] == expected
    assert f.platform.events == []


def test_singleton_lock_does_not_publish_second_worker_heartbeat(installation):
    f = installation
    with lock(f.state / 'worker.lock'):
        with pytest.raises(LockBusyError): f.worker.serve(once=True)
    assert not (f.state / 'worker.json').exists()


def test_backup_hash_mismatch_does_not_delete_live_data(installation):
    f = installation; scopes = f.platform.scopes()
    backup = backup_data(scopes, f.worker.private / 'test-backup')
    (backup / '0/database.txt').write_text('corrupted')
    with pytest.raises(UpdateError, match='backup_hash_mismatch'): restore_data(scopes, backup)
    assert (f.root / 'data/database.txt').read_text() == 'original-data'


def test_linked_data_and_unknown_request_arguments_are_rejected(installation, tmp_path):
    f = installation
    if os.name != 'nt':
        (f.root / 'data/redirect').symlink_to(tmp_path)
        with pytest.raises(ProtocolError): backup_data(f.platform.scopes(), f.worker.private / 'bad-backup')
    write_json_atomic(f.state / 'request.json', {**f.request,'repo':'https://untrusted.invalid/repo'})
    with pytest.raises(UpdateError, match='invalid_update_request'): f.worker.claim()
    assert f.platform.events == []


def test_clean_environment_drops_credentials_build_overrides_and_hooks(monkeypatch):
    for key in ('GA_WUWA_TOKEN','GITHUB_TOKEN','ANTHROPIC_API_KEY','SSH_AUTH_SOCK','NODE_OPTIONS',
                'PYTHONPATH','VITE_API_URL','NPM_CONFIG_REGISTRY','UV_INDEX_URL','HTTPS_PROXY'):
        monkeypatch.setenv(key, 'must-be-absent')
    environment = clean_environment()
    assert not any(value == 'must-be-absent' for value in environment.values())
    assert environment['GIT_CONFIG_GLOBAL'] == os.devnull


def test_windows_scripts_share_byte_lock_and_active_release_is_not_arbitrary_path():
    root = Path(__file__).resolve().parents[1]
    common = (root / 'scripts/runtime-common.ps1').read_text()
    bridge = (root / 'scripts/system-update-runtime.ps1').read_text()
    assert '$lock.Lock(0, 1)' in common and '$lock.Unlock(0, 1)' in common
    assert '[IO.FileShare]::ReadWrite' in common
    assert 'data\\system-update\\releases\\' in common
    assert 'active.path' not in common
    assert '--project-root' in common
    assert 'ParentProcessId' in bridge and 'worker_pid' in bridge
    assert 'Get-VerifiedProcess' in bridge


# Imported here to keep the expected public protocol exception explicit.
from game_assistant.system_update_protocol import ProtocolError


def test_retry_preserves_own_failed_candidate_but_rebuilds_venv_at_stable_path(installation):
    f = installation; f.runner.fail_build = True
    assert perform(f)['phase'] == 'failed'
    first_job = f.request['job_id']
    f.request['job_id'] = '3'*32; f.runner.fail_build = False
    assert perform(f)['phase'] == 'completed'
    archived = f.worker.config.releases / ('.failed-' + f.target + '-' + first_job)
    assert archived.is_dir()
    assert (f.worker.config.releases / f.target / '.venv/Scripts/python.exe').is_file()


def test_unknown_release_directory_is_never_deleted_or_adopted(installation):
    f = installation; unknown = f.worker.config.releases / f.target
    unknown.mkdir(parents=True); (unknown / 'user-file').write_text('preserve')
    result = perform(f)
    assert result['phase'] == 'failed' and result['error_code'] == 'release_directory_exists'
    assert (unknown / 'user-file').read_text() == 'preserve'
    assert 'stop' not in f.platform.events


def test_offline_sqlite_backup_roundtrip_preserves_runtime_metadata(installation):
    import sqlite3
    f = installation; dbpath = f.root / 'data/example.db'
    with closing(sqlite3.connect(dbpath)) as db:
        db.execute('CREATE TABLE sample (value TEXT)'); db.execute("INSERT INTO sample VALUES ('before')")
        db.commit()
    keep = f.root / 'data/runtime/keep'; keep.write_text('runtime survives')
    backup = backup_data(f.platform.scopes(), f.worker.private / 'sqlite-backup')
    with closing(sqlite3.connect(dbpath)) as db:
        db.execute("UPDATE sample SET value='after'")
        db.commit()
    restore_data(f.platform.scopes(), backup)
    with closing(sqlite3.connect(dbpath)) as db:
        assert db.execute('SELECT value FROM sample').fetchone()[0] == 'before'
    assert keep.read_text() == 'runtime survives'


def test_linux_adapter_orders_both_writers_and_separates_api_from_qq_start():
    from game_assistant.system_update_worker import LinuxPlatform
    calls = []
    platform = LinuxPlatform.__new__(LinuxPlatform)
    platform.config = SimpleNamespace(api_service='game-manage.service', qq_service='game-manage-qq.service')
    platform.run = lambda argv, **kwargs: calls.append(argv)
    platform.property = lambda service, name: 'inactive'
    state = {'api_active':True,'qq_active':True}
    platform.stop(state)
    assert calls == [['systemctl','stop','game-manage-qq.service'], ['systemctl','stop','game-manage.service']]
    calls.clear(); platform.property = lambda service, name: 'active'
    platform.start(state)
    assert calls == [['systemctl','start','game-manage.service']]
    platform.start_qq(state)
    assert calls[-1] == ['systemctl','start','game-manage-qq.service']
    calls.clear(); platform.start_qq({'api_active':True,'qq_active':False})
    assert calls == []


def test_linux_current_only_accepts_controlled_release_symlink(installation, tmp_path):
    f = installation
    root = tmp_path / 'linux-install'; releases = root / 'releases'; releases.mkdir(parents=True)
    release = releases / f.old
    subprocess.run(['git','clone',str(f.root),str(release)], check=True, capture_output=True)
    write_json_atomic(release / 'release.json', {'schema':1,'commit':f.old,'frontend_commit':f.old,
        'source':'miyako-md/game-manage','branch':'main'})
    (root / 'current').symlink_to(release, target_is_directory=True)
    c = WorkerConfig('linux',root,tmp_path/'state')
    platform = Platform(c, Runner())
    assert platform.current() == (release, f.old)
    (root / 'current').unlink(); (root / 'current').symlink_to(f.root, target_is_directory=True)
    with pytest.raises(UpdateError, match='unsupported_current_layout'): platform.current()


@pytest.mark.skipif(os.name != 'nt', reason='real Windows file locking, isolated temp file only')
def test_windows_protocol_lock_excludes_new_and_legacy_powershell_scripts(tmp_path):
    path = tmp_path / 'service.lock'
    new = "$f=[IO.File]::Open($env:TEST_LOCK_PATH,'OpenOrCreate','ReadWrite','ReadWrite'); try {$f.Lock(0,1);exit 0} catch {exit 2} finally {$f.Dispose()}"
    old = "try {$f=[IO.File]::Open($env:TEST_LOCK_PATH,'OpenOrCreate','ReadWrite','None');$f.Dispose();exit 0} catch {exit 2}"
    with lock(path):
        for source in (new, old):
            result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',source],
                env={**os.environ,'TEST_LOCK_PATH':str(path)}, capture_output=True, timeout=15)
            assert result.returncode == 2


@pytest.mark.skipif(os.name == 'nt', reason='POSIX executable hook fixture')
def test_privileged_git_status_cannot_execute_post_index_change_or_fsmonitor(installation):
    import shlex
    f = installation; hook = f.root / '.git/hooks/post-index-change'; marker = f.root / 'hook-executed'
    hook.write_text('#!/bin/sh\nprintf bad > ' + shlex.quote(str(marker)) + '\n'); hook.chmod(0o755)
    source = f.root / 'source.txt'
    os.utime(source, (1111111111, 1111111111))
    # Demonstrate this is a real executable-hook regression, not only argv text.
    git(f.root, 'status', '--porcelain')
    assert marker.exists()
    marker.unlink(); os.utime(source, (1111111112, 1111111112))
    from game_assistant.system_update_worker import git_clean
    assert git_clean(f.root, Runner()) == f.old
    assert not marker.exists()
    fsmonitor = f.root / '.git/hooks/fsmonitor'
    fsmonitor.write_text('#!/bin/sh\nprintf bad > ' + shlex.quote(str(marker)) + '\n'); fsmonitor.chmod(0o755)
    git(f.root, 'config', 'core.fsmonitor', str(fsmonitor))
    assert git_clean(f.root, Runner()) == f.old
    assert not marker.exists()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX public-file ownership publication')
def test_public_status_permissions_are_set_before_replace(tmp_path, monkeypatch):
    import stat
    import game_assistant.system_update_worker as worker
    path = tmp_path / 'status.json'
    write_json_atomic(path, {'phase':'stopping'}); path.chmod(0o640)
    replace = worker.os.replace
    chown = worker.os.fchown
    seen = []
    def fchown(fd, uid, gid):
        assert uid == 0
        seen.append(('ownership', gid))
        # Current test user owns the temporary fixture; root behavior gets a
        # real cross-UID concurrent reader in the opt-in Linux acceptance test.
        chown(fd, os.getuid(), os.getgid())
    def publish(source, destination):
        assert stat.S_IMODE(Path(source).stat().st_mode) == 0o640
        assert json.loads(path.read_text())['phase'] == 'stopping'
        assert read_json(source)['phase'] == 'verifying'
        seen.append(('replace', None))
        return replace(source, destination)
    monkeypatch.setattr(worker.os, 'fchown', fchown)
    monkeypatch.setattr(worker.os, 'replace', publish)
    worker.write_public_json(path, {'phase':'verifying'}, os.getgid())
    assert seen == [('ownership', os.getgid()), ('replace', None)]
    assert path.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize('origins', [[], ['http://cloud.example'], ['https://user:secret@cloud.example'],
    ['https://cloud.example:0'], ['https://cloud.example/path'], ['https://cloud.example\r\nHost: evil'],
    ['https://cloud.example','https://evil.example/path']])
def test_health_host_rejects_unreviewable_origins(origins):
    from game_assistant.system_update_worker import cloud_health_host
    with pytest.raises(UpdateError): cloud_health_host(origins)


def test_loopback_health_request_interoperates_with_real_cloud_boundary(monkeypatch):
    import io
    import re
    import urllib.error
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from game_assistant.cloud_app import CloudBoundary
    from game_assistant.system_update_worker import cloud_health_host, health_at
    commit = 'a'*40
    app = FastAPI()
    @app.get('/api/health')
    def health():
        return {'status':'ok','ready':True,'version':{'commit':commit,'frontend_commit':commit}}
    owner = SimpleNamespace(state=SimpleNamespace(cloud_route_policy=[
        (re.compile(r'^/api/health$'),frozenset({'GET'}),'public')],
        identity=SimpleNamespace(authenticate=lambda cookie:None)))
    boundary = CloudBoundary(app, owner, SimpleNamespace(cloud_allowed_origins=['https://cloud.example:8443'],cloud_body_limit_bytes=65536))
    client = TestClient(boundary, base_url='http://127.0.0.1:8020')
    visited = []
    class Opener:
        def open(self, request, timeout):
            visited.append((request.full_url, request.get_header('Host')))
            response = client.get(request.full_url, headers=dict(request.header_items()), follow_redirects=False)
            if response.status_code != 200:
                raise urllib.error.HTTPError(request.full_url, response.status_code,'boundary rejected',{},None)
            return io.BytesIO(response.content)
    monkeypatch.setattr('game_assistant.system_update_worker.urllib.request.build_opener', lambda *handlers:Opener())
    monkeypatch.setattr('game_assistant.system_update_worker.time.sleep', lambda seconds:None)
    assert not health_at('http://127.0.0.1:8020/api/health', commit, timeout=.005)
    assert health_at('http://127.0.0.1:8020/api/health', commit, timeout=.1,
                     host=cloud_health_host(['https://cloud.example:8443']))
    assert visited[-1] == ('http://127.0.0.1:8020/api/health','cloud.example:8443')
    assert client.get('/api/health', headers={'Host':'untrusted.example'}).status_code == 403


def test_root_helper_unit_never_starts_candidate_interpreter_or_site_packages():
    root = Path(__file__).resolve().parents[1]
    unit = (root / 'deploy/cloud/game-manage-updater.service').read_text()
    installer = (root / 'scripts/system-update-install-linux.py').read_text()
    assert 'ExecStart=/usr/bin/python3 -I -S /opt/game-manage-cloud/.updater/helper/entry.py' in unit
    assert 'current/.venv' not in unit
    assert 'ReadOnlyPaths=/opt/game-manage-cloud/.updater/helper' in unit
    assert "'system_update_worker.py':" in installer and "'system_update_protocol.py':" in installer
    assert 'from game_assistant.' not in installer


@pytest.mark.parametrize('tasks_max', [64, 128])
def test_transient_command_has_lifecycle_binding_and_is_fully_reaped_before_return(tmp_path, monkeypatch, tasks_max):
    import game_assistant.system_update_worker as worker
    calls = []
    run = Runner('isolated-test-lifecycle.service')
    monkeypatch.setattr(worker.sys, 'platform', 'linux')
    monkeypatch.setattr(worker.os, 'geteuid', lambda:0, raising=False)
    original = Path.is_file
    monkeypatch.setattr(Path, 'is_file', lambda path:True if path.as_posix()=='/sys/fs/cgroup/cgroup.controllers' else original(path))
    def command(argv, **kwargs):
        calls.append(argv)
        stdout = 'LoadState=loaded\nActiveState=inactive\nControlGroup=\n' if argv[:2]==['systemctl','show'] else ''
        return SimpleNamespace(returncode=0,stdout=stdout)
    monkeypatch.setattr(run, '_run', command)
    result = run([sys.executable, '-c', 'pass'],cwd=tmp_path,user=65534,group=65534,
                 write_paths=(tmp_path,),env={'PATH':'/usr/bin:/bin'},tasks_max=tasks_max)
    assert result.returncode == 0
    systemd = next(argv for argv in calls if argv[0]=='systemd-run')
    assert '--wait' in systemd and '--service-type=exec' in systemd
    assert '--property=TasksMax=' + str(tasks_max) in systemd
    for setting in ('KillMode=control-group','BindsTo=isolated-test-lifecycle.service',
                    'After=isolated-test-lifecycle.service','PartOf=isolated-test-lifecycle.service',
                    'ProtectSystem=strict','ProtectControlGroups=yes','NoNewPrivileges=yes'):
        assert '--property='+setting in systemd
    assert calls[-3][0:2] == ['systemctl','stop']
    assert calls[-2][0:2] == ['systemctl','show']
    assert calls[-1][0:2] == ['systemctl','reset-failed']


def test_visible_completed_publish_failure_never_restores_after_api_can_write(installation, monkeypatch):
    f = installation
    publish = f.worker.publish
    def fail_after_publication(status):
        publish(status)
        if status['phase'] == 'completed':
            assert read_json(f.worker.journal_path)['external_side_effects_possible'] is True
            (f.root / 'data/database.txt').write_text('accepted-after-completed')
            raise OSError('injected directory fsync failure after replace')
    monkeypatch.setattr(f.worker, 'publish', fail_after_publication)
    result = perform(f)
    assert result['phase'] == 'recovery_required'
    assert 'health_old' not in f.platform.events
    assert (f.root / 'data/database.txt').read_text() == 'accepted-after-completed'
    assert read_json(f.root / 'data/runtime/active-release.json')['commit'] == f.target


@pytest.mark.parametrize('stop_fails', [False, True])
def test_visible_rolled_back_publish_failure_stops_old_service_without_second_restore(installation, monkeypatch, stop_fails):
    import game_assistant.system_update_worker as worker
    f = installation; f.platform.fail_new_health = True
    publish, restore, stop = f.worker.publish, worker.restore_data, f.platform.stop
    restores = []
    terminal_seen = []
    def counted_restore(scopes, destination):
        restores.append(destination)
        return restore(scopes, destination)
    def fail_after_publication(status):
        publish(status)
        if status['phase'] == 'rolled_back':
            assert read_json(f.worker.journal_path)['external_side_effects_possible'] is True
            assert read_json(f.state / 'status.json')['phase'] == 'rolled_back'
            terminal_seen.append(True)
            (f.root / 'data/database.txt').write_text('accepted-after-rolled-back')
            raise OSError('injected directory fsync failure after rolled_back replace')
    def record_stop(state):
        stop(state)
        if terminal_seen and stop_fails:
            raise UpdateError('injected_restored_service_stop_failure')
    monkeypatch.setattr(worker, 'restore_data', counted_restore)
    monkeypatch.setattr(f.worker, 'publish', fail_after_publication)
    monkeypatch.setattr(f.platform, 'stop', record_stop)
    result = perform(f)
    assert result['phase'] == 'recovery_required'
    assert len(restores) == 1
    assert f.platform.events[-3:] == ['health_old', 'stop', 'unlock']
    assert (f.root / 'data/database.txt').read_text() == 'accepted-after-rolled-back'
    assert not (f.root / 'data/runtime/active-release.json').exists()


@pytest.mark.parametrize('integrity_ok', [True, False])
def test_backup_validation_closes_sqlite_before_temporary_directory_cleanup(installation, monkeypatch, integrity_ok):
    import sqlite3
    import game_assistant.system_update_worker as worker
    f = installation
    dbpath = f.root / 'data/validation.db'
    with closing(sqlite3.connect(dbpath)) as db:
        db.execute('CREATE TABLE sample (value TEXT)')
        db.execute("INSERT INTO sample VALUES ('committed-before-backup')")
        db.commit()
    connect, temporary_directory = sqlite3.connect, worker.tempfile.TemporaryDirectory
    connections, events = [], []
    class TrackedConnection(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if not integrity_ok and sql == 'PRAGMA integrity_check':
                return SimpleNamespace(fetchone=lambda:('injected integrity failure',))
            return super().execute(sql, *args, **kwargs)
        def close(self):
            super().close()
            events.append('connection_closed')
    def tracked_connect(*args, **kwargs):
        connection = connect(*args, factory=TrackedConnection, **kwargs)
        connections.append(connection)
        return connection
    @contextmanager
    def checked_temporary_directory(*args, **kwargs):
        with temporary_directory(*args, **kwargs) as path:
            try:
                yield path
            finally:
                assert connections
                for connection in connections:
                    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
                        connection.execute('SELECT 1')
                events.append('temporary_directory_cleanup')
    monkeypatch.setattr(worker.sqlite3, 'connect', tracked_connect)
    monkeypatch.setattr(worker.tempfile, 'TemporaryDirectory', checked_temporary_directory)
    destination = f.worker.private / 'close-order-backup'
    if integrity_ok:
        backup_data(f.platform.scopes(), destination)
    else:
        with pytest.raises(UpdateError, match='backup_database_integrity_failed'):
            backup_data(f.platform.scopes(), destination)
    assert events == ['connection_closed', 'temporary_directory_cleanup']
    assert not list(destination.glob('.verify-*'))


class CachePlatform(FakePlatform):
    """Sandbox-shaped options plus shared caches, as LinuxPlatform provides them."""
    def __init__(self, config, run, caches):
        super().__init__(config, run)
        self.caches = caches

    def prepare_options(self, release):
        home = release.parent / ('.build-home-' + release.name)
        home.mkdir()
        return {'home': str(home), 'write_paths': (release, home)}

    def dependency_caches(self, release):
        for path in self.caches.values(): path.mkdir(exist_ok=True)
        return dict(self.caches)


def test_dependency_steps_alone_use_and_write_their_shared_cache(installation, tmp_path):
    f = installation
    caches = {'uv': tmp_path / 'uv-cache-shared', 'npm': tmp_path / 'npm-cache-shared'}
    f.worker.platform = platform = CachePlatform(f.worker.config, f.runner, caches)
    assert perform(f)['phase'] == 'completed'
    steps = {tuple(argv[:2]): kwargs for argv, kwargs in f.runner.calls if argv[0] != 'git'}
    uv, npm_ci = steps[('uv', 'sync')], steps[('npm.cmd', 'ci')]
    assert [argv for argv, _ in f.runner.calls if argv[:2] == ['npm.cmd', 'ci']] == [
        ['npm.cmd', 'ci', '--prefer-offline', '--no-audit', '--no-fund']]
    assert uv['env']['UV_CACHE_DIR'] == str(caches['uv']) and caches['uv'] in uv['write_paths']
    assert uv['env']['UV_LINK_MODE'] == 'copy'
    assert npm_ci['env']['npm_config_cache'] == str(caches['npm']) and caches['npm'] in npm_ci['write_paths']
    assert caches['npm'] not in uv['write_paths'] and caches['uv'] not in npm_ci['write_paths']
    assert uv['timeout'] == npm_ci['timeout'] == 3600
    # Later steps execute dependency code: no shared cache in their env or write scope.
    later = [kwargs for argv, kwargs in f.runner.calls
             if argv[0] != 'git' and tuple(argv[:2]) not in {('uv', 'sync'), ('npm.cmd', 'ci')}]
    assert later
    for kwargs in later:
        assert not set(caches.values()) & set(kwargs.get('write_paths', ()))
        assert str(caches['uv']) != kwargs['env']['UV_CACHE_DIR']
        assert str(caches['npm']) != kwargs['env']['npm_config_cache']
    assert platform.events


class FlakyFetch(BuildRunner):
    def __init__(self, remote, failures):
        super().__init__(remote)
        self.failures = failures

    def __call__(self, argv, **kwargs):
        if 'fetch' in [str(x) for x in argv] and self.failures:
            self.failures -= 1
            self.calls.append(([str(x) for x in argv], kwargs.copy()))
            raise UpdateError('command_unavailable_or_timed_out')
        return super().__call__(argv, **kwargs)


@pytest.mark.parametrize('failures,phase', [(2, 'completed'), (3, 'failed')])
def test_official_fetch_is_retried_before_failing(installation, monkeypatch, failures, phase):
    import game_assistant.system_update_worker as worker_module
    monkeypatch.setattr(worker_module, 'FETCH_RETRY_SECONDS', 0)
    f = installation
    f.runner = FlakyFetch(f.remote, failures)
    f.worker.run = f.worker.platform.run = f.runner
    status = perform(f)
    assert status['phase'] == phase
    assert sum('fetch' in argv for argv, _ in f.runner.calls) == min(failures + 1, 3)
    if phase == 'failed':
        assert status['error_code'] == 'command_unavailable_or_timed_out'


@pytest.mark.skipif(os.name == 'nt', reason='POSIX ownership and modes')
def test_linux_dependency_caches_follow_the_exact_lockfile_and_stay_bounded(tmp_path):
    from game_assistant.system_update_worker import LinuxPlatform
    releases = tmp_path / 'releases'; releases.mkdir()
    platform = SimpleNamespace(config=SimpleNamespace(releases=releases),
                               builder=SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid()))
    def release(name, uv_lock, npm_lock='{}'):
        root = releases / name; (root / 'frontend').mkdir(parents=True)
        (root / 'uv.lock').write_text(uv_lock); (root / 'frontend/package-lock.json').write_text(npm_lock)
        return root
    first = LinuxPlatform.dependency_caches(platform, release('a', 'lock-1'))
    again = LinuxPlatform.dependency_caches(platform, release('b', 'lock-1'))
    assert first == again and first['uv'] != first['npm']
    assert all((path.stat().st_mode & 0o777) == 0o700 for path in first.values())
    (first['uv'] / 'wheel').write_text('kept while the lockfile is unchanged')
    second = LinuxPlatform.dependency_caches(platform, release('c', 'lock-2'))
    assert second['uv'] != first['uv'] and second['npm'] == first['npm']
    assert (first['uv'] / 'wheel').is_file()
    third = LinuxPlatform.dependency_caches(platform, release('d', 'lock-3'))
    uv_caches = sorted(p.name for p in (releases / '.build-cache').iterdir() if p.name.startswith('uv-'))
    assert uv_caches == sorted([second['uv'].name, third['uv'].name])
    assert not first['uv'].exists()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX symlinks')
def test_linux_dependency_cache_root_must_not_be_a_link(tmp_path):
    from game_assistant.system_update_worker import LinuxPlatform
    releases = tmp_path / 'releases'; releases.mkdir()
    elsewhere = tmp_path / 'elsewhere'; elsewhere.mkdir()
    (releases / '.build-cache').symlink_to(elsewhere, target_is_directory=True)
    root = releases / 'a'; (root / 'frontend').mkdir(parents=True)
    (root / 'uv.lock').write_text('x'); (root / 'frontend/package-lock.json').write_text('{}')
    platform = SimpleNamespace(config=SimpleNamespace(releases=releases),
                               builder=SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid()))
    with pytest.raises(Exception):
        LinuxPlatform.dependency_caches(platform, root)
    assert not list(elsewhere.iterdir())


def test_build_environment_keeps_npm_user_and_global_config_distinct(tmp_path):
    first = build_environment(tmp_path, tmp_path / 'release', 'a' * 40, 'linux')
    second = build_environment(tmp_path, tmp_path / 'release', 'a' * 40, 'linux')
    # npm 10 exits before doing anything when one file is loaded as both layers.
    assert first['NPM_CONFIG_GLOBALCONFIG'] == os.devnull
    assert first['NPM_CONFIG_USERCONFIG'] != first['NPM_CONFIG_GLOBALCONFIG']
    assert Path(first['NPM_CONFIG_USERCONFIG']).parent == tmp_path
    assert not Path(first['NPM_CONFIG_USERCONFIG']).exists()
    assert first['NPM_CONFIG_USERCONFIG'] != second['NPM_CONFIG_USERCONFIG']
    assert first['npm_config_cache'] == str(tmp_path / 'npm-cache')
    assert first['VITE_SERVICE_MODE'] == 'cloud'
    assert build_environment(tmp_path, tmp_path, 'a' * 40, 'windows')['VITE_SERVICE_MODE'] == 'local'


def test_real_npm_starts_with_the_exact_build_environment(tmp_path):
    environment = build_environment(tmp_path / 'home', tmp_path / 'release', 'a' * 40,
                                    'windows' if os.name == 'nt' else 'linux')
    (tmp_path / 'home').mkdir()
    npm = shutil.which('npm', path=environment.get('PATH'))
    if not npm:
        pytest.skip('npm is not installed')
    result = Runner._run([npm, '--version'], cwd=tmp_path, env=environment, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()


def test_failing_command_keeps_its_output_tail_for_the_failure_log(tmp_path):
    runner = Runner()
    script = "import sys; sys.stderr.write('x' * 5000 + 'npm error tail'); sys.exit(3)"
    with pytest.raises(UpdateError, match='command_failed'):
        runner([sys.executable, '-c', script], cwd=tmp_path, timeout=60)
    assert runner.last_failure['returncode'] == 3
    assert runner.last_failure['stderr'].endswith('npm error tail')
    assert len(runner.last_failure['stderr']) == 4096
    assert Path(runner.last_failure['command']).name.startswith('python')


def test_failed_build_writes_a_private_failure_log_without_publishing_output(installation):
    f = installation; f.runner.fail_command = 'double-loading config "/dev/null"'
    status = perform(f)
    assert status['phase'] == 'failed' and status['error_code'] == 'command_failed'
    assert 'double-loading' not in json.dumps(status)
    log = json.loads((f.worker.private / 'last-command-failure.log').read_text(encoding='utf-8'))
    assert log['job_id'] == f.request['job_id'] and log['returncode'] == 1
    assert log['command'] == 'npm.cmd run build' and 'double-loading' in log['stderr']
    if os.name != 'nt':
        assert (f.worker.private / 'last-command-failure.log').stat().st_mode & 0o077 == 0
    # Only the private journal directory (nested under state on Windows) may hold the output.
    published = [p for p in f.state.rglob('*') if p.is_file() and f.worker.private not in p.parents]
    assert published and not any('double-loading' in p.read_text(encoding='utf-8', errors='ignore') for p in published)


def _dist(root, files):
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


def test_reachable_assets_follow_entry_pages_and_skip_chunks_carried_from_older_releases(tmp_path):
    from game_assistant.system_update_worker import reachable_assets
    dist = _dist(tmp_path / 'dist', {
        'index.html': '<script type="module" src="/assets/index-A1.js"></script>',
        'render-a.html': '<script src="/assets/renderA-A1.js"></script>',
        'assets/index-A1.js': 'import("./CloudApp-A1.js");const m=["assets/CloudApp-A1.css"]',
        'assets/CloudApp-A1.js': 'import "./index-A1.js";export const icon="icon-A1.svg"',
        'assets/CloudApp-A1.css': '@font-face{src:url(./font-A1.woff2)}',
        'assets/font-A1.woff2': 'f', 'assets/icon-A1.svg': '<svg/>', 'assets/renderA-A1.js': '',
        # Carried forward by an earlier upgrade; nothing in this build names it.
        'assets/CloudApp-OLD.js': 'import("./Gone-OLD.js")', 'assets/Gone-OLD.js': '',
    })
    files = [path for path in (dist / 'assets').iterdir()]
    names = {path.name for path in reachable_assets(dist, files)}
    assert names == {'index-A1.js', 'renderA-A1.js', 'CloudApp-A1.js', 'CloudApp-A1.css', 'font-A1.woff2', 'icon-A1.svg'}


def test_retained_render_assets_keep_one_previous_release_instead_of_every_earlier_one(tmp_path):
    from types import SimpleNamespace
    from game_assistant.system_update_worker import LinuxPlatform

    def build(name, tag, previous=None):
        release = tmp_path / name
        _dist(release / 'frontend/dist', {'index.html': f'<script src="/assets/index-{tag}.js"></script>',
                                          f'assets/index-{tag}.js': f'import("./Page-{tag}.js")', f'assets/Page-{tag}.js': '',
                                          'game-icons/wuwa.png': 'icon'})
        if previous is not None:
            LinuxPlatform.retain_render_assets(SimpleNamespace(previous=previous, runtime_data={}), release)
        return release

    first = build('first', 'A')
    second = build('second', 'B', first)
    assert {p.name for p in (second / 'frontend/dist/assets').iterdir()} == {'index-A.js', 'Page-A.js', 'index-B.js', 'Page-B.js'}
    third = build('third', 'C', second)
    # The first release's chunks were only reachable from its own pages, so they are not carried again.
    assert {p.name for p in (third / 'frontend/dist/assets').iterdir()} == {'index-B.js', 'Page-B.js', 'index-C.js', 'Page-C.js'}
    assert (third / 'frontend/dist/game-icons/wuwa.png').is_file()
