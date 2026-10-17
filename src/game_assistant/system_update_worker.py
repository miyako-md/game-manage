"""Independent, fail-closed updater for managed Windows and systemd installs.

No HTTP request runs these commands. The only network source is OFFICIAL_REPO's
main branch; an operator config selects an installation, never a Git source.
Preparation has no service/data side effects. The private journal is the recovery
source of truth; the API-writable request/status directory is not trusted for it.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager, nullcontext
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import sqlite3
import subprocess
import sys
import threading
import tempfile
import time
import tomllib
import urllib.request
from urllib.parse import urlsplit
import uuid

from .system_update_protocol import (ACTIVE_PHASES, LockBusyError, ProtocolError,
    lock, read_json, safe_path, valid_sha, write_json_atomic)

OFFICIAL_REPO = 'https://github.com/miyako-md/game-manage.git'
OFFICIAL_REF = 'refs/heads/main'
SOURCE = 'miyako-md/game-manage'
TERMINAL = {'completed', 'failed', 'rolled_back', 'recovery_required'}
SERVICE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.@-]*\.service\Z')


class UpdateError(RuntimeError):
    """Only fixed safe codes cross the API/log boundary."""


def fail(code):
    raise UpdateError(code)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def clean_environment():
    # No GA_*, tokens, SSH agents, proxies, PYTHONPATH, npm configuration, Vite
    # overrides or ambient credentials reach fetched build/install scripts.
    names = ('PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
             'LANG', 'LC_ALL')
    result = {name: os.environ[name] for name in names if name in os.environ}
    result.update(GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1',
                  GIT_CONFIG_GLOBAL=os.devnull, PYTHONNOUSERSITE='1',
                  UV_NO_PROGRESS='1', UV_NO_MANAGED_PYTHON='1',
                  NPM_CONFIG_USERCONFIG=os.devnull, NPM_CONFIG_GLOBALCONFIG=os.devnull)
    return result


def protected_git_argv(argv):
    """Never run checkout-controlled hooks/fsmonitor under the helper UID."""
    argv = [str(x) for x in argv]
    if Path(argv[0]).name.lower() in {'git', 'git.exe'}:
        return [argv[0], '-c', 'core.hooksPath=' + os.devnull,
                '-c', 'core.fsmonitor=false', '-c', 'credential.helper=', *argv[1:]]
    return argv


class Runner:
    def __init__(self, lifecycle_unit='game-manage-updater.service'):
        # Only tests/operator-created runners override this. It is never an HTTP
        # or updater config parameter, so requests cannot bind arbitrary units.
        if not SERVICE_NAME.fullmatch(lifecycle_unit): fail('invalid_helper_unit')
        self.lifecycle_unit = lifecycle_unit
        self.last_unit = None

    @staticmethod
    def _run(argv, *, cwd=None, env=None, timeout=1800):
        try:
            return subprocess.run([str(x) for x in argv], cwd=cwd,
                env=env if env is not None else clean_environment(), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout,
                text=True, encoding='utf-8', errors='replace')
        except (OSError, subprocess.TimeoutExpired):
            fail('command_unavailable_or_timed_out')

    def _stopped(self, unit):
        result = self._run(['systemctl', 'show', unit, '--property=LoadState,ActiveState,ControlGroup'], timeout=15)
        values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if values.get('LoadState') == 'not-found': return True
        if result.returncode or values.get('ActiveState') not in {'inactive', 'failed'}: return False
        group = values.get('ControlGroup', '')
        if not group: return True
        if not group.startswith('/') or '..' in Path(group).parts: return False
        root = Path('/sys/fs/cgroup') / group.lstrip('/')
        # This helper requires unified cgroups, which the supported systemd
        # hosts provide. Never replace the kernel guarantee with a process scan.
        try:
            files = [root / 'cgroup.procs', *root.glob('**/cgroup.procs')]
            return all(not file.read_text().strip() for file in files if file.exists())
        except OSError:
            return False

    def _sandbox(self, argv, *, cwd, env, user, group, timeout, write_paths, private_network):
        if sys.platform != 'linux' or os.geteuid() != 0 or not user or not group:
            fail('unprivileged_build_identity_required')
        if not Path('/sys/fs/cgroup/cgroup.controllers').is_file():
            fail('unified_cgroups_required')
        if self._run(['systemctl', 'is-active', '--quiet', self.lifecycle_unit], timeout=15).returncode:
            fail('helper_lifecycle_unit_not_active')
        paths = [safe_path(path) for path in write_paths]
        if not paths or any(not path.is_dir() or any(ch.isspace() for ch in str(path)) for path in paths):
            fail('invalid_build_write_scope')
        cwd = safe_path(cwd)
        if not any(cwd == path or cwd.is_relative_to(path) for path in paths):
            fail('build_cwd_outside_scope')
        unit = 'game-manage-update-build-' + uuid.uuid4().hex + '.service'
        self.last_unit = unit
        properties = {
            'User': str(user), 'Group': str(group), 'SupplementaryGroups': '',
            'KillMode': 'control-group', 'SendSIGKILL': 'yes', 'TimeoutStopSec': '10s',
            'RuntimeMaxSec': str(timeout) + 's', 'UMask': '0022',
            'BindsTo': self.lifecycle_unit, 'After': self.lifecycle_unit,
            'PartOf': self.lifecycle_unit, 'NoNewPrivileges': 'yes',
            'ProtectSystem': 'strict', 'ProtectHome': 'yes', 'PrivateTmp': 'yes',
            'ProtectControlGroups': 'yes', 'ProtectKernelTunables': 'yes',
            'RestrictSUIDSGID': 'yes', 'Delegate': 'no',
            'InaccessiblePaths': '-/run/user -/run/dbus/system_bus_socket -/run/systemd/private',
            'ReadWritePaths': ' '.join(str(path) for path in paths),
            'BindPaths': ' '.join(str(path) for path in paths),
        }
        if private_network: properties['PrivateNetwork'] = 'yes'
        command = ['systemd-run', '--quiet', '--wait', '--pipe', '--service-type=exec',
                   '--unit=' + unit, '--working-directory=' + str(cwd)]
        command += ['--property=' + key + '=' + value for key, value in properties.items()]
        # env -i prevents the system manager from supplying business/Python env.
        environment = env if env is not None else clean_environment()
        executable = str(argv[0])
        if not os.path.isabs(executable):
            executable = shutil.which(executable, path=environment.get('PATH'))
            if not executable: fail('build_tool_unavailable')
        command += ['--', '/usr/bin/env', '-i', *[key + '=' + value for key, value in environment.items()],
                    executable, *argv[1:]]
        result = None
        try:
            result = self._run(command, timeout=timeout + 30)
        finally:
            # --wait is the first barrier. Also stop and prove the full unit is
            # empty on errors/timeouts, including children that used setsid().
            try:
                self._run(['systemctl', 'stop', unit], timeout=25)
                if not self._stopped(unit): fail('build_processes_not_quiescent')
            except UpdateError:
                fail('build_processes_not_quiescent')
            self._run(['systemctl', 'reset-failed', unit], timeout=15)
        return result

    def __call__(self, argv, *, cwd=None, env=None, user=None, group=None, timeout=1800,
                 check=True, write_paths=(), private_network=False):
        argv = protected_git_argv(argv)
        if user is not None:
            result = self._sandbox(argv, cwd=cwd, env=env, user=user, group=group,
                timeout=timeout, write_paths=write_paths, private_network=private_network)
        else:
            result = self._run(argv, cwd=cwd, env=env, timeout=timeout)
        if check and result.returncode: fail('command_failed')
        return result


@dataclass
class WorkerConfig:
    platform: str
    install_root: Path
    state_dir: Path
    config_path: Path | None = None
    data_root: Path | None = None
    qq_data_root: Path | None = None
    api_service: str = 'game-manage.service'
    qq_service: str = 'game-manage-qq.service'
    api_user: str = 'game-manage-cloud'
    qq_user: str = 'game-manage-qq'
    build_user: str = 'game-manage-build'
    extras: tuple[str, ...] = ()

    def validate(self, *, provisioned=True):
        if self.platform not in {'windows', 'linux'}:
            fail('unsupported_platform')
        self.install_root = safe_path(self.install_root)
        self.state_dir = safe_path(self.state_dir)
        if not self.install_root.is_dir() or (provisioned and not self.state_dir.is_dir()):
            fail('installation_not_provisioned')
        if set(self.extras) - {'dev', 'ocr', 'qq', 'qq-render'}:
            fail('unsupported_dependency_extra')
        if self.platform == 'windows':
            if self.state_dir != self.install_root / 'data/system-update':
                fail('unsupported_state_layout')
        else:
            for service in (self.api_service, self.qq_service):
                if not SERVICE_NAME.fullmatch(service):
                    fail('unsupported_service_name')
            if not self.config_path or not self.data_root or not self.qq_data_root:
                fail('operator_configuration_required')
            self.config_path = safe_path(self.config_path)
            self.data_root = safe_path(self.data_root)
            self.qq_data_root = safe_path(self.qq_data_root)
            paths = [self.install_root, self.state_dir, self.data_root, self.qq_data_root]
            if any(a == b or a.is_relative_to(b) or b.is_relative_to(a)
                   for i, a in enumerate(paths) for b in paths[i + 1:]):
                fail('overlapping_update_paths')
            if not self.config_path.is_file() or not all(p.is_dir() for p in paths if provisioned or p != self.state_dir):
                fail('installation_not_provisioned')
        return self

    @property
    def releases(self):
        return self.install_root / ('data/system-update/releases' if self.platform == 'windows' else 'releases')

    @property
    def private(self):
        return self.install_root / ('data/system-update/private' if self.platform == 'windows' else '.updater')


def release_identity(root):
    record = read_json(root / 'release.json')
    if (record.get('schema') != 1 or not valid_sha(record.get('commit')) or
        record.get('frontend_commit') != record['commit'] or
        record.get('source') != SOURCE or record.get('branch') != 'main'):
        fail('invalid_release_manifest')
    return record['commit']


def git_clean(root, run):
    if not (root / '.git').exists():
        fail('unverifiable_source_checkout')
    safe_path(root / '.git')
    result = run(['git', '-C', root, '-c', 'core.fsmonitor=false', 'status', '--porcelain', '--untracked-files=normal'], timeout=30)
    # release.json is the single generated, separately verified release marker.
    if any(line != '?? release.json' for line in result.stdout.splitlines()):
        fail('dirty_checkout')
    result = run(['git', '-C', root, 'rev-parse', '--verify', 'HEAD'], timeout=30).stdout.strip()
    if not valid_sha(result):
        fail('invalid_current_commit')
    return result


def verify_tree(root, *, ignored=frozenset()):
    """Never follow junctions/symlinks or copy device nodes from private data."""
    safe_path(root)
    if not root.is_dir():
        fail('data_directory_missing')
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        if base == root:
            dirs[:] = [name for name in dirs if name not in ignored]
            files = [name for name in files if name not in ignored]
        for name in dirs + files:
            path = safe_path(base / name)
            info = path.lstat()
            mode = info.st_mode
            if stat.S_ISREG(mode) and info.st_nlink > 1:
                fail('linked_data_file')
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                fail('unsupported_data_file')


@dataclass
class DataScope:
    path: Path
    excluded: frozenset[str] = field(default_factory=frozenset)


class Platform:
    def __init__(self, config, run):
        self.config, self.run = config, run

    def current(self):
        c = self.config
        if c.platform == 'windows':
            original = git_clean(c.install_root, self.run)
            marker = c.install_root / 'data/runtime/active-release.json'
            if not marker.exists():
                return c.install_root, original
            item = read_json(marker)
            if set(item) != {'schema', 'commit'} or item['schema'] != 1 or not valid_sha(item['commit']):
                fail('invalid_active_release')
            root = safe_path(c.releases / item['commit'])
        else:
            current = c.install_root / 'current'
            if not current.is_symlink():
                fail('unsupported_current_layout')
            destination = current.resolve(strict=True)
            root = safe_path(destination)
            if root.parent != safe_path(c.releases) or not valid_sha(root.name):
                fail('unsupported_current_layout')
        commit = release_identity(root)
        if commit != root.name or git_clean(root, self.run) != commit:
            fail('release_source_mismatch')
        return root, commit

    def preflight(self, previous):
        raise NotImplementedError

    def transaction(self):
        return nullcontext()

    def prepare_options(self, release):
        return {}

    def dependency_extras(self):
        return self.config.extras

    def validate_prepared(self, release, python, environment, options):
        pass

    def scopes(self):
        raise NotImplementedError

    def stop(self, state):
        raise NotImplementedError

    def start(self, state):
        raise NotImplementedError

    def start_qq(self, state):
        pass

    def activate(self, commit):
        c = self.config
        if c.platform == 'windows':
            marker = c.install_root / 'data/runtime/active-release.json'
            if commit is None:
                safe_path(marker).unlink(missing_ok=True)
            else:
                write_json_atomic(marker, {'schema': 1, 'commit': commit})
        else:
            if not valid_sha(commit) or release_identity(safe_path(c.releases / commit)) != commit:
                fail('invalid_activation_target')
            temporary = c.install_root / '.current-updating'
            if temporary.exists() or temporary.is_symlink():
                fail('activation_marker_exists')
            temporary.symlink_to(c.releases / commit, target_is_directory=True)
            os.replace(temporary, c.install_root / 'current')
            fd = os.open(c.install_root, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def healthy(self, commit, *, previous=False):
        raise NotImplementedError


def cloud_health_host(origins):
    """Use the reviewed HTTPS authority while connecting only to loopback."""
    if not isinstance(origins, list) or not origins: fail('invalid_cloud_health_origin')
    result = []
    for origin in origins:
        if not isinstance(origin, str) or any(c.isspace() or ord(c) < 32 for c in origin) or '\\' in origin:
            fail('invalid_cloud_health_origin')
        try:
            item = urlsplit(origin)
            if (item.scheme != 'https' or not item.hostname or item.username is not None or item.password is not None
                    or item.path not in ('', '/') or item.query or item.fragment):
                fail('invalid_cloud_health_origin')
            host, port = item.hostname.lower(), 443 if item.port is None else item.port
            if not host.isascii() or not 1 <= port <= 65535: fail('invalid_cloud_health_origin')
        except ValueError:
            fail('invalid_cloud_health_origin')
        if ':' in host: host = '[' + host + ']'
        result.append(host + (':' + str(port) if port != 443 else ''))
    return result[0]


class NoHealthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def health_at(url, commit, timeout=45, *, host=None):
    # Operator-defined loopback only. Do not use HTTP_PROXY or credentials.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoHealthRedirect())
    request = urllib.request.Request(url, headers={'Host': host} if host else {})
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        try:
            with opener.open(request, timeout=2) as response:
                raw = response.read(65537)
            if len(raw) <= 65536:
                data = json.loads(raw)
                version = data.get('version', {})
                if (data.get('status') == 'ok' and data.get('ready') is True and version.get('commit') == commit
                        and version.get('frontend_commit') == commit):
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(.5)
    return False


class WindowsPlatform(Platform):
    def bridge(self, action):
        script = Path(__file__).resolve().parents[2] / 'scripts/system-update-runtime.ps1'
        return self.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                         '-File', script, '-InstallRoot', self.config.install_root, '-Action', action,
                         '-JobId', read_json(self.config.private / 'journal.json')['job_id']],
                        timeout=90, env=dict(os.environ))

    def preflight(self, previous):
        if os.name != 'nt':
            fail('unsupported_platform')
        self.bridge('verify')
        # Resolve exactly as the currently managed runtime: config takes priority
        # over GA_* and defaults. No secret values are serialized or logged.
        from .config import Settings
        settings = Settings.load(str(self.config.install_root / 'config.toml'))
        if settings.cloud_accounts_enabled:
            fail('unsupported_local_runtime_mode')
        data = self.config.install_root / 'data'
        for value in (settings.db_path, settings.auth_store_path):
            if value:
                path = Path(value)
                path = safe_path(path if path.is_absolute() else self.config.install_root / path)
                if not path.is_relative_to(data) or path.is_relative_to(data / 'runtime') or path.is_relative_to(data / 'system-update'):
                    fail('unsupported_local_data_path')
        verify_tree(data, ignored=frozenset({'runtime', 'system-update'}))
        return {'api_active': True, 'qq_active': False, 'original': previous == self.config.install_root}

    def dependency_extras(self):
        extras = set(self.config.extras) | {'dev'}
        # Preserve OCR only when present in the active runtime, rather than
        # dropping it because the updater itself has a smaller dependency set.
        root, _ = self.current()
        python = root / '.venv/Scripts/python.exe'
        result = self.run([python, '-c', 'import importlib.util; print(int(importlib.util.find_spec("rapidocr_onnxruntime") is not None))'], timeout=30)
        if result.stdout.strip() == '1': extras.add('ocr')
        return tuple(sorted(extras))

    def transaction(self):
        return lock(self.config.install_root / 'data/runtime/service.lock')

    def scopes(self):
        return [DataScope(self.config.install_root / 'data', frozenset({'runtime', 'system-update'}))]

    def stop(self, state):
        self.bridge('stop')

    def start(self, state):
        self.bridge('start')

    def healthy(self, commit, *, previous=False):
        return health_at('http://127.0.0.1:8010/api/health', commit)


class LinuxPlatform(Platform):
    def __init__(self, config, run):
        super().__init__(config, run)
        import pwd
        self.api = pwd.getpwnam(config.api_user)
        self.qq = pwd.getpwnam(config.qq_user)
        self.builder = pwd.getpwnam(config.build_user)
        if any(account.pw_uid == 0 or account.pw_gid == 0 for account in (self.api, self.qq, self.builder)):
            fail('unprivileged_service_users_required')
        self.port = None
        self.health_host = None
        self.runtime_data = None
        self.previous = None

    def property(self, service, name):
        return self.run(['systemctl', 'show', service, '--property=' + name, '--value'], timeout=30).stdout.strip()

    def preflight(self, previous):
        c = self.config
        if os.name != 'posix' or sys.platform != 'linux' or os.geteuid() != 0:
            fail('linux_root_helper_required')
        for path in (c.config_path, c.private):
            info = safe_path(path).stat()
            if info.st_uid != 0 or info.st_mode & 0o022:
                fail('operator_configuration_not_protected')
        data = tomllib.loads(c.config_path.read_text(encoding='utf-8'))
        # Explicit layout excludes environment-dependent database destinations.
        identity = safe_path(Path(data.get('cloud_db_path', '')))
        cloud_data = safe_path(Path(data.get('cloud_data_root', '')))
        if identity != c.data_root / 'identity.db' or cloud_data != c.data_root / 'data':
            fail('unsupported_cloud_data_layout')
        if 'qq_images_enabled' not in data or 'qq_browser_render_enabled' not in data:
            fail('explicit_render_configuration_required')
        if not data.get('cloud_accounts_enabled'):
            fail('unsupported_cloud_runtime')
        self.health_host = cloud_health_host(data.get('cloud_allowed_origins'))
        self.runtime_data = data
        self.previous = previous
        runtime = data.get('runtime', {})
        self.port = runtime.get('port', 8020)
        if runtime.get('host', '127.0.0.1') != '127.0.0.1' or type(self.port) is not int or not 1024 <= self.port <= 65535:
            fail('unsupported_cloud_listener')
        states = {}
        for name, service, user, module, tail in (
            ('api', c.api_service, c.api_user, 'game_assistant.cloud_runtime', ['--config', str(c.config_path)]),
            ('qq', c.qq_service, c.qq_user, 'game_assistant.qq.runner', ['--state-file', str(c.qq_data_root / 'state.db')]),
        ):
            if self.property(service, 'User') != user:
                fail('unmanaged_service')
            if self.property(service, 'WorkingDirectory') not in {str(c.install_root / 'current'), str(previous)}:
                fail('unmanaged_service')
            # Restrict to the documented module entrypoint; no shell wrappers,
            # custom ExecStart flags, auxiliary processes or alternate state DBs.
            argv = [str(c.install_root / 'current/.venv/bin/python'), '-m', module, *tail]
            command = self.property(service, 'ExecStart')
            if 'argv[]=' + ' '.join(argv) + ' ;' not in command:
                fail('unmanaged_service_command')
            if any(self.property(service, prop) for prop in ('ExecStartPre','ExecStartPost','ExecStop','ExecStopPost','RootDirectory','RootImage')):
                fail('unmanaged_service_hook')
            if self.property(service, 'KillMode') != 'control-group':
                fail('unmanaged_service_process_group')
            states[name + '_active'] = self.property(service, 'ActiveState') == 'active'
        if not states['api_active']:
            fail('managed_api_not_running')
        for scope in self.scopes():
            verify_tree(scope.path)
        return states

    def prepare_options(self, release):
        # Build scripts run under a dedicated UID, without service secrets.
        for directory, dirs, files in os.walk(release):
            os.chmod(directory, 0o755)
            for name in [directory, *(str(Path(directory) / x) for x in dirs + files)]:
                os.chown(name, self.builder.pw_uid, self.builder.pw_gid, follow_symlinks=False)
                if Path(name).is_file():
                    os.chmod(name, stat.S_IMODE(Path(name).stat().st_mode) | 0o044)
        home = self.config.releases / ('.build-home-' + release.name + '-' + str(time.time_ns()))
        home.mkdir(mode=0o700)
        os.chown(home, self.builder.pw_uid, self.builder.pw_gid)
        return {'user': self.builder.pw_uid, 'group': self.builder.pw_gid, 'home': str(home),
                'write_paths': (release, home)}

    def dependency_extras(self):
        return tuple(sorted(set(self.config.extras) | {'qq', 'qq-render'}))

    def validate_prepared(self, release, python, environment, options):
        old = tomllib.loads((self.previous / 'pyproject.toml').read_text(encoding='utf-8'))
        new = tomllib.loads((release / 'pyproject.toml').read_text(encoding='utf-8'))
        if old['project']['optional-dependencies'].get('qq-render') != new['project']['optional-dependencies'].get('qq-render'):
            fail('browser_runtime_upgrade_requires_operator')
        data = self.runtime_data
        api_home = self.config.releases / ('.api-check-' + release.name + '-' + str(time.time_ns()))
        api_home.mkdir(mode=0o700)
        os.chown(api_home, self.api.pw_uid, self.api.pw_gid)
        api_environment = {**environment, 'HOME': str(api_home), 'USERPROFILE': str(api_home)}
        self.run([python, '-c', 'from game_assistant.cloud_runtime import load_runtime; import sys; load_runtime(sys.argv[1])',
                 self.config.config_path], cwd=release, env=api_environment, user=self.api.pw_uid, group=self.api.pw_gid, timeout=30,
                 write_paths=(release, api_home), private_network=True)
        # A browser path from a service environment is not assumed to survive.
        # Supported installs declare these non-secret paths in cloud.toml.
        if data.get('qq_images_enabled', False) and data.get('qq_browser_render_enabled', True):
            browser = data.get('qq_browser_render_executable_path', '')
            font = data.get('qq_image_font_path', '')
            if not browser or not font:
                fail('explicit_render_runtime_required')
            for value in (browser, font):
                path = safe_path(value)
                if not path.is_absolute() or not path.is_file():
                    fail('render_runtime_missing')
            # Launch only the configured existing browser, as the runtime user,
            # with no URL/network access. No system packages are installed here.
            script = ('from playwright.sync_api import sync_playwright; import sys; '
                      'p=sync_playwright().start(); b=p.chromium.launch(executable_path=sys.argv[1],headless=True); '
                      'page=b.new_page(); page.set_content("<p>ready</p>"); '
                      'assert page.locator("p").inner_text()=="ready"; b.close(); p.stop()')
            self.run([python, '-c', 'import sys; open(sys.argv[1], "rb").read(4)', font],
                     cwd=release, env=api_environment, user=self.api.pw_uid, group=self.api.pw_gid, timeout=30,
                 write_paths=(release, api_home), private_network=True)
            self.run([python, '-c', script, browser], cwd=release, env=api_environment,
                     user=self.api.pw_uid, group=self.api.pw_gid, timeout=45,
                     write_paths=(release, api_home), private_network=True)
        # Do not leave the active source owned by the build account. Normal venv
        # symlinks are retained; source symlinks were rejected before the build.
        for directory, dirs, files in os.walk(release, followlinks=False):
            for name in [directory, *(str(Path(directory) / x) for x in dirs + files)]:
                os.chown(name, 0, 0, follow_symlinks=False)
                mode = Path(name).lstat().st_mode
                if stat.S_ISDIR(mode): os.chmod(name, 0o755)
                elif stat.S_ISREG(mode): os.chmod(name, 0o644 | (mode & 0o111))
                elif not stat.S_ISLNK(mode): fail('unsupported_prepared_file')

    def scopes(self):
        return [DataScope(self.config.data_root), DataScope(self.config.qq_data_root)]

    def stop(self, state):
        # QQ can still write state while API is stopping, so stop it first.
        for name, service in (('qq', self.config.qq_service), ('api', self.config.api_service)):
            if state[name + '_active']:
                self.run(['systemctl', 'stop', service], timeout=120)
                if self.property(service, 'ActiveState') not in {'inactive', 'failed'}:
                    fail('service_did_not_stop')

    def start(self, state):
        if state['api_active']:
            self.run(['systemctl', 'start', self.config.api_service], timeout=120)
            if self.property(self.config.api_service, 'ActiveState') != 'active':
                fail('service_did_not_start')

    def start_qq(self, state):
        if state['qq_active']:
            self.run(['systemctl', 'start', self.config.qq_service], timeout=120)
            if self.property(self.config.qq_service, 'ActiveState') != 'active':
                fail('service_did_not_start')

    def healthy(self, commit, *, previous=False):
        return health_at(f'http://127.0.0.1:{self.port}/api/health', commit, host=self.health_host)


def backup_data(scopes, destination):
    destination = safe_path(destination)
    destination.mkdir(mode=0o700)
    entries = []
    for index, scope in enumerate(scopes):
        verify_tree(scope.path, ignored=scope.excluded)
        output = destination / str(index)
        output.mkdir(mode=0o700)
        for item in scope.path.iterdir():
            if item.name in scope.excluded:
                continue
            target = output / item.name
            if item.is_dir():
                shutil.copytree(item, target, copy_function=shutil.copy2)
            else:
                shutil.copy2(item, target)
        files, directories = {}, {}
        for item in output.rglob('*'):
            relative = str(item.relative_to(output))
            original = scope.path / relative
            info = original.stat()
            metadata = {'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}
            if item.is_file():
                checksum = digest(item)
                if digest(original) != checksum: fail('data_changed_during_backup')
                files[relative] = {**metadata, 'sha256': checksum}
                with item.open('rb') as stream: header = stream.read(16)
                if header == b'SQLite format 3\x00':
                    # Validate an isolated copy: SQLite may recreate/update WAL
                    # shared-memory files even for a read-only connection.
                    with tempfile.TemporaryDirectory(prefix='.verify-', dir=destination) as check_dir:
                        check = Path(check_dir) / 'database.sqlite'
                        shutil.copy2(item, check)
                        for suffix in ('-wal', '-shm'):
                            sidecar = Path(str(item) + suffix)
                            if sidecar.is_file(): shutil.copy2(sidecar, Path(str(check) + suffix))
                        with closing(sqlite3.connect(check.as_uri() + '?mode=ro', uri=True)) as db:
                            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                                fail('backup_database_integrity_failed')
            else:
                directories[relative] = metadata
        entries.append({'index': index, 'files': files, 'directories': directories})
    # This manifest is private and can exceed the public file protocol's bound.
    manifest = destination / 'manifest.json'
    with manifest.open('x', encoding='utf-8') as stream:
        json.dump({'schema': 1, 'scopes': entries}, stream)
        stream.flush(); os.fsync(stream.fileno())
    manifest.chmod(0o600)
    return destination


def restore_data(scopes, destination):
    safe_path(destination)
    if not (destination / 'manifest.json').is_file():
        fail('backup_manifest_missing')
    manifest = json.loads((destination / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or len(manifest.get('scopes', [])) != len(scopes):
        fail('backup_manifest_invalid')
    # Validate ALL backup files before deleting any data written by the failed version.
    for index, scope in enumerate(scopes):
        record = manifest['scopes'][index]
        if record['index'] != index:
            fail('backup_manifest_invalid')
        source = destination / str(index)
        verify_tree(source)
        actual = {str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}
        if actual != set(record['files']):
            fail('backup_inventory_mismatch')
        for name, metadata in record['files'].items():
            path = safe_path(source / name)
            if not path.is_relative_to(source) or digest(path) != metadata['sha256']:
                fail('backup_hash_mismatch')
        verify_tree(scope.path, ignored=scope.excluded)
    for index, scope in enumerate(scopes):
        for item in scope.path.iterdir():
            if item.name in scope.excluded:
                continue
            if item.is_dir(): shutil.rmtree(item)
            else: item.unlink()
        source = destination / str(index)
        for item in source.iterdir():
            if item.is_dir(): shutil.copytree(item, scope.path / item.name, copy_function=shutil.copy2)
            else: shutil.copy2(item, scope.path / item.name)
        if os.name != 'nt':
            # copy2 preserves modes/times, but not service account ownership.
            for name, metadata in {**manifest['scopes'][index]['directories'],
                                   **manifest['scopes'][index]['files']}.items():
                path = safe_path(scope.path / name)
                if not path.is_relative_to(scope.path): fail('backup_manifest_invalid')
                os.chown(path, metadata['uid'], metadata['gid'])
                os.chmod(path, metadata['mode'])
        for name, metadata in manifest['scopes'][index]['files'].items():
            if digest(scope.path / name) != metadata['sha256']:
                fail('restored_data_hash_mismatch')



def write_public_json(path, value, group):
    """Root-owned API-readable inode is fully ready before atomic replacement."""
    path = safe_path(path)
    raw = (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')
    if len(raw) > 65536: fail('public_status_too_large')
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        os.fchown(fd, 0, group)
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, 'wb') as stream:
            fd = None
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        safe_path(path)
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try: os.fsync(parent)
        finally: os.close(parent)
    finally:
        if fd is not None: os.close(fd)
        try: os.unlink(temporary)
        except FileNotFoundError: pass


class Updater:
    def __init__(self, config, platform=None, run=None):
        self.config = config.validate()
        self.run = run or Runner()
        self.platform = platform or (WindowsPlatform(config, self.run) if config.platform == 'windows' else LinuxPlatform(config, self.run))
        self.private = safe_path(config.private)
        self.private.mkdir(mode=0o700, exist_ok=True)
        if config.platform == 'linux' and (self.private.stat().st_uid != 0 or self.private.stat().st_mode & 0o077):
            fail('private_journal_not_protected')
        if config.platform == 'linux':
            import pwd
            group = pwd.getpwnam(config.api_user).pw_gid
            info = config.state_dir.stat()
            queue = safe_path(config.state_dir / 'queue.lock').stat()
            if (info.st_uid != 0 or info.st_gid != group or stat.S_IMODE(info.st_mode) != 0o3770
                    or queue.st_uid != 0 or queue.st_gid != group or stat.S_IMODE(queue.st_mode) != 0o660):
                fail('shared_state_not_provisioned')
        self.journal_path = self.private / 'journal.json'
        self.current_job = None

    def publish_file(self, name, value):
        path = self.config.state_dir / name
        if self.config.platform == 'linux':
            import pwd
            group = pwd.getpwnam(self.config.api_user).pw_gid
            write_public_json(path, value, group)
        else:
            write_json_atomic(path, value)

    def publish(self, status):
        self.publish_file('status.json', status)

    def phase(self, phase, error=None):
        job = self.current_job
        job['phase'] = phase; job['updated_at'] = time.time()
        if phase in TERMINAL: job['finished_at'] = time.time()
        if error: job['error_code'] = error
        write_json_atomic(self.journal_path, job)
        public = {key: job[key] for key in ('schema', 'job_id', 'target_sha', 'previous_sha',
                  'phase', 'updated_at', 'finished_at', 'error_code') if key in job}
        self.publish(public)

    def recover_interrupted(self):
        try:
            job = read_json(self.journal_path)
        except FileNotFoundError:
            return False
        self.current_job = job
        if job.get('phase') in ACTIVE_PHASES:
            # An interrupted prepare never changed the service. Any interruption
            # after stop may have migrated data: require operator-led recovery.
            phase = 'failed' if job['phase'] in {'queued', 'preparing'} else 'recovery_required'
            self.phase(phase, 'worker_interrupted')
        elif job.get('phase') in TERMINAL:
            self.phase(job['phase'], job.get('error_code'))
        else:
            fail('private_journal_invalid')
        return job.get('phase') == 'recovery_required'

    def claim(self):
        with lock(self.config.state_dir / 'queue.lock'):
            try:
                request = read_json(self.config.state_dir / 'request.json')
            except FileNotFoundError:
                return False
            if (set(request) != {'schema','job_id','target_sha','expected_sha','requested_at','source'} or
                request.get('schema') != 1 or request.get('source') != 'main' or
                not isinstance(request.get('job_id'), str) or not re.fullmatch('[0-9a-f]{32}', request['job_id']) or
                not valid_sha(request.get('target_sha')) or not valid_sha(request.get('expected_sha')) or
                type(request.get('requested_at')) not in (int, float) or not math.isfinite(request['requested_at'])):
                fail('invalid_update_request')
            old = None
            try: old = read_json(self.journal_path)
            except FileNotFoundError: pass
            if old and (old.get('phase') == 'recovery_required' or old.get('phase') in ACTIVE_PHASES):
                fail('operator_recovery_required')
            if old and old.get('job_id') == request['job_id']:
                self.current_job = old
                self.phase(old['phase'], old.get('error_code'))
                safe_path(self.config.state_dir / 'request.json').unlink()
                return False
            self.current_job = {'schema': 1, 'job_id': request['job_id'], 'target_sha': request['target_sha'].lower(),
                                'previous_sha': request['expected_sha'].lower(), 'phase': 'queued',
                                'worker_pid': os.getpid(), 'updated_at': time.time()}
            self.phase('preparing')
            safe_path(self.config.state_dir / 'request.json').unlink()
            return True

    def prepare(self, current, target):
        c = self.config
        cache = self.private / 'repository.git'
        if not cache.exists(): self.run(['git', 'init', '--bare', cache], timeout=30)
        # Never use the checkout's origin, refspec, hooks or credential helpers.
        self.run(['git', '-C', cache, '-c', 'credential.helper=', 'fetch', '--no-tags', '--force',
                  OFFICIAL_REPO, OFFICIAL_REF + ':refs/remotes/official/main'], timeout=180)
        official = self.run(['git', '-C', cache, 'rev-parse', 'refs/remotes/official/main'], timeout=30).stdout.strip()
        if official != target: fail('official_main_changed')
        if current == target: fail('already_current')
        # Missing current object is also not a verified ancestor (e.g. ahead,
        # diverged, an unmerged private commit); it must never be downgraded.
        result = self.run(['git', '-C', cache, 'merge-base', '--is-ancestor', current, target], check=False, timeout=30)
        if result.returncode: fail('current_not_ancestor')
        c.releases.mkdir(parents=True, exist_ok=True)
        release = safe_path(c.releases / target)
        ownership = self.private / ('prepared-' + target + '.json')
        if release.exists():
            try: created = read_json(ownership)
            except FileNotFoundError: fail('release_directory_exists')
            if (created.get('target') != target or created.get('previous') != current or
                    not re.fullmatch('[0-9a-f]{32}', str(created.get('job_id', ''))) or
                    created.get('job_id') == self.current_job['job_id']):
                fail('release_directory_exists')
            # Retain this helper's failed candidate for diagnosis; never delete
            # or adopt an unknown directory, and never move an active venv.
            archived = safe_path(c.releases / ('.failed-' + target + '-' + created['job_id']))
            if archived.exists(): fail('failed_candidate_archive_exists')
            os.replace(release, archived)
        write_json_atomic(ownership, {'schema':1, 'job_id':self.current_job['job_id'],
                                      'target':target, 'previous':current})
        self.run(['git', 'clone', '--no-hardlinks', '--no-checkout', cache, release], timeout=180)
        self.run(['git', '-C', release, 'remote', 'set-url', 'origin', OFFICIAL_REPO], timeout=30)
        self.run(['git', '-C', release, 'checkout', '--detach', target], timeout=60)
        # Explicitly reject tracked symlinks/submodules before executing a build.
        entries = self.run(['git', '-C', release, 'ls-files', '--stage'], timeout=30).stdout.splitlines()
        if any(not line.startswith(('100644 ', '100755 ')) for line in entries):
            fail('unsupported_source_entry')
        for name in ('uv.lock', 'pyproject.toml', 'frontend/package-lock.json', 'frontend/package.json'):
            if not safe_path(release / name).is_file(): fail('required_lockfile_missing')
        tracked = self.run(['git', '-C', release, 'ls-files', '-z'], timeout=30).stdout.split('\0')
        source_hashes = {name: digest(safe_path(release / name)) for name in tracked if name}
        git_config = (release / '.git/config').read_bytes()
        options = self.platform.prepare_options(release)
        environment = clean_environment()
        home = options.pop('home', str(self.private / 'build-home'))
        Path(home).mkdir(parents=True, exist_ok=True)
        environment.update(HOME=home, USERPROFILE=home, UV_CACHE_DIR=str(Path(home) / 'uv-cache'),
                           npm_config_cache=str(Path(home) / 'npm-cache'), GA_BUILD_COMMIT=target,
                           VITE_SERVICE_MODE='cloud' if c.platform == 'linux' else 'local',
                           UV_PROJECT_ENVIRONMENT=str(release / '.venv'))
        argv = ['uv', 'sync', '--locked', '--no-dev']
        for extra in self.platform.dependency_extras(): argv += ['--extra', extra]
        self.run(argv, cwd=release, env=environment, **options)
        npm = 'npm.cmd' if c.platform == 'windows' else 'npm'
        self.run([npm, 'ci'], cwd=release / 'frontend', env=environment, **options)
        python = release / ('.venv/Scripts/python.exe' if c.platform == 'windows' else '.venv/bin/python')
        if c.platform == 'linux':
            self.run([python, 'scripts/cloud/build_frontend.py', '--frontend', 'frontend'], cwd=release, env=environment, **options)
        else:
            self.run([npm, 'run', 'build'], cwd=release / 'frontend', env=environment, **options)
        build = read_json(release / 'frontend/dist/build-info.json')
        if build.get('commit') != target or not (release / 'frontend/dist/index.html').is_file():
            fail('frontend_commit_mismatch')
        self.run([python, '-c', 'import game_assistant.api, game_assistant.cloud_runtime'], cwd=release, env=environment, **options)
        self.platform.validate_prepared(release, python, environment, options)
        # All unprivileged cgroups are now empty and source ownership is frozen.
        # A dependency's install script must not gain root via Git config/filter
        # hooks. Check immutable source and .git paths before root invokes Git.
        if any(digest(safe_path(release / name)) != value for name, value in source_hashes.items()):
            fail('prepared_source_modified')
        verify_tree(release / '.git')
        safe_path(release / '.git/config').write_bytes(git_config)
        if git_clean(release, self.run) != target: fail('prepared_source_modified')
        write_json_atomic(release / 'release.json', {'schema':1, 'commit':target, 'frontend_commit':target,
                                                    'source':SOURCE, 'branch':'main'})
        if c.platform == 'linux':
            # Runtime users can read the immutable identity; never transfer the
            # root helper's private journal or operator config to the builder.
            os.chmod(release / 'release.json', 0o644)
        return release

    def execute(self):
        job = self.current_job
        critical_started = False
        try:
            previous, current = self.platform.current()
            if current != job['previous_sha']: fail('current_version_changed')
            state = self.platform.preflight(previous)
            self.prepare(current, job['target_sha'])
            again, commit = self.platform.current()
            if again != previous or commit != current: fail('current_version_changed')
            with self.platform.transaction():
                # Recheck running services/data after preparation, inside the
                # shared lock. Preserve their current active/inactive states.
                state = self.platform.preflight(previous)
                job['services'] = state
                job['previous_original'] = previous == self.config.install_root
                critical_started = True
                self._activate_transaction(state)
        except Exception as error:
            code = str(error) if isinstance(error, UpdateError) else 'update_operation_failed'
            self.phase('recovery_required' if critical_started or code == 'build_processes_not_quiescent' else 'failed', code)

    def _activate_transaction(self, state):
        job = self.current_job
        backup = None
        try:
            self.phase('stopping')
            self.platform.stop(state)
            self.phase('backing_up')
            scopes = self.platform.scopes()
            for scope in scopes: verify_tree(scope.path, ignored=scope.excluded)
            backup = backup_data(scopes, self.private / ('backup-' + job['job_id']))
            self.phase('activating')
            self.platform.activate(job['target_sha'])
            self.phase('restarting'); self.platform.start(state)
            self.phase('verifying')
            if not self.platform.healthy(job['target_sha']): fail('new_release_health_failed')
            if state.get('qq_active'):
                # A QQ connection can receive/acknowledge messages immediately.
                # After this durable boundary, restoring dedup state is unsafe.
                job['external_side_effects_possible'] = True
                self.phase('verifying')
                self.platform.start_qq(state)
            # Publishing completed can admit API writes/background work before
            # the publisher's final fsync returns. Commit the no-restore boundary
            # first, even on installations without QQ.
            if not job.get('external_side_effects_possible'):
                job['external_side_effects_possible'] = True
                self.phase('verifying')
            self.phase('completed')
        except Exception as error:
            code = str(error) if isinstance(error, UpdateError) else 'update_operation_failed'
            try:
                self.platform.stop(state)
                if job.get('external_side_effects_possible'):
                    self.phase('recovery_required', code)
                    return
                if backup is not None:
                    restore_data(self.platform.scopes(), backup)
                self.platform.activate(None if job.get('previous_original') else job['previous_sha'])
                self.platform.start(state)
                if not self.platform.healthy(job['previous_sha'], previous=True):
                    fail('rollback_health_failed')
                if state.get('qq_active'):
                    job['external_side_effects_possible'] = True
                    self.phase('verifying')
                    self.platform.start_qq(state)
                # rolled_back also reopens API writes/deferred schedulers. Its
                # publication has the same irreversible boundary as completed.
                if not job.get('external_side_effects_possible'):
                    job['external_side_effects_possible'] = True
                    self.phase('verifying')
                self.phase('rolled_back', code)
            except Exception:
                # The restored API may already have observed a terminal status.
                # Stop it before reporting uncertainty; never restore a second
                # time or discard writes accepted after that publication.
                try:
                    self.platform.stop(state)
                except Exception:
                    pass
                self.phase('recovery_required', code)

    def heartbeat(self):
        self.publish_file('worker.json', {'schema':1, 'pid':os.getpid(), 'platform':self.config.platform, 'updated_at':time.time()})

    def serve(self, once=False):
        with lock(self.config.state_dir / 'worker.lock'):
            blocked = self.recover_interrupted()
            stop = threading.Event()
            def pulse():
                while not stop.wait(5):
                    try: self.heartbeat()
                    except (OSError, ProtocolError): pass
            self.heartbeat()
            thread = threading.Thread(target=pulse, daemon=True); thread.start()
            try:
                while True:
                    if not blocked:
                        try:
                            if self.claim(): self.execute()
                        except (ProtocolError, UpdateError, OSError):
                            # Malformed queued requests remain for operator review;
                            # do not erase evidence or invent a successful job.
                            pass
                    if once: return
                    time.sleep(1)
            finally:
                stop.set(); thread.join(timeout=6)
                # No stale apparently-live heartbeat on a graceful exit.
                try:
                    path = self.config.state_dir / 'worker.json'
                    record = read_json(path)
                    if record.get('pid') == os.getpid(): path.unlink()
                except (OSError, ProtocolError): pass


def load_config(path):
    path = safe_path(path)
    if os.name != 'nt':
        info = path.stat()
        if info.st_uid != 0 or info.st_mode & 0o022: fail('operator_configuration_not_protected')
    raw = read_json(path)
    allowed = {'platform','install_root','state_dir','config_path','data_root','qq_data_root',
               'api_service','qq_service','api_user','qq_user','build_user','extras'}
    if set(raw) - allowed: fail('unknown_updater_setting')
    for name in ('install_root','state_dir','config_path','data_root','qq_data_root'):
        if name in raw: raw[name] = Path(raw[name])
    if 'extras' in raw: raw['extras'] = tuple(raw['extras'])
    return WorkerConfig(**raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--config', type=Path)
    group.add_argument('--windows-root', type=Path)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config) if args.config else WorkerConfig('windows', args.windows_root,
                    args.windows_root / 'data/system-update')
        Updater(config).serve(once=args.once)
    except LockBusyError:
        return 0
    except Exception:
        # Never print subprocess stderr or configuration contents.
        print('system_update_worker_unavailable', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
