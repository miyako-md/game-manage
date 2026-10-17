"""Capture running code identity once; on-disk changes never relabel a live process."""
from dataclasses import dataclass
from pathlib import Path
import subprocess
import tomllib

from .system_update_protocol import ProtocolError, read_json, safe_path, valid_sha

REPOSITORY = 'miyako-md/game-manage'


def source_root(module_file=None, cwd=None):
    """An editable/source package outranks cwd; installed wheels use the release cwd."""
    module = Path(module_file or __file__).absolute()
    starts = (module.parent, Path(cwd).absolute() if cwd is not None else Path.cwd())
    for start in starts:
        for candidate in (start, *start.parents):
            manifest = candidate / 'pyproject.toml'
            try:
                safe_path(manifest)
                if manifest.stat().st_size > 65536:
                    continue
                project = tomllib.loads(manifest.read_text(encoding='utf-8')).get('project', {})
                if project.get('name') == 'game-assistant':
                    return candidate
            except (OSError, ValueError):
                continue
    return None


def git_state(root):
    """Read-only, bounded git queries; no shell, fetch, checkout or branch changes."""
    try:
        root = safe_path(root)
        if not (root / '.git').exists():
            return None, None
        safe_path(root / '.git')
        def run(*arguments):
            result = subprocess.run(['git', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-c', f'safe.directory={root}', '-C', str(root), *arguments],
                                    capture_output=True, timeout=4, check=True)
            if len(result.stdout) > 1048576:
                raise ValueError('git_output_limit')
            return result.stdout.decode('utf-8', errors='strict').strip()
        sha = run('rev-parse', '--verify', 'HEAD')
        # Build artifacts/venvs are ignored; untracked source files still block an update.
        dirty = any(line != '?? release.json' for line in run('status', '--porcelain', '--untracked-files=normal').splitlines())
        return (sha.lower(), dirty) if valid_sha(sha) else (None, None)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, None


@dataclass(frozen=True)
class RunningVersion:
    root: Path | None
    commit: str | None
    frontend_commit: str | None
    startup_dirty: bool | None
    manifest_valid: bool = False
    frontend_root: Path | None = None
    identity_valid: bool = True

    @property
    def ready(self):
        return self.identity_valid and valid_sha(self.commit) and self.frontend_sha() == self.commit

    def frontend_sha(self):
        return read_frontend_commit(self.frontend_root) if self.frontend_root is not None else self.frontend_commit

    def disk_state(self):
        if self.root is None:
            return None, None
        head, dirty = git_state(self.root)
        if head is not None:
            return head, dirty
        # A signed-off release tree may have no .git (wheel installation).
        if self.manifest_valid:
            try:
                manifest = release_manifest(self.root)
                if manifest['commit'] == self.commit:
                    return self.commit, False
            except (OSError, ValueError):
                pass
        return None, None

    def public(self):
        disk, dirty = self.disk_state()
        if disk is not None and self.commit and disk != self.commit:
            dirty = True
        if self.startup_dirty is True:
            dirty = True
        return {'sha': self.commit, 'frontend_sha': self.frontend_sha(), 'dirty': dirty}

    def health(self):
        return {'commit': self.commit, 'frontend_commit': self.frontend_sha()}


def release_manifest(root):
    value = read_json(Path(root) / 'release.json')
    if (type(value.get('schema')) is not int or value['schema'] != 1
            or value.get('source') != REPOSITORY or value.get('branch') != 'main'
            or not valid_sha(value.get('commit')) or not valid_sha(value.get('frontend_commit'))
            or value['commit'].lower() != value['frontend_commit'].lower()):
        raise ProtocolError('invalid_release_manifest')
    return {**value, 'commit': value['commit'].lower(), 'frontend_commit': value['frontend_commit'].lower()}


def _package_commit():
    try:
        build = read_json(Path(__file__).parent / 'build-info.json')
        commit = build.get('commit')
        if type(build.get('schema')) is int and build['schema'] == 1 and build.get('source') == REPOSITORY and valid_sha(commit):
            return commit.lower()
    except (OSError, ValueError):
        pass
    return None


def read_frontend_commit(directory):
    if directory is None:
        return None
    try:
        build = read_json(Path(directory) / 'build-info.json')
        value = build.get('commit')
        if type(build.get('schema')) is int and build['schema'] == 1 and build.get('source') == REPOSITORY and valid_sha(value):
            return value.lower()
    except (OSError, ValueError):
        pass
    return None


def capture_version(root=None, *, frontend_dist=None):
    # An explicit tree is for offline release inspection. Running installed
    # packages must identify their own code, never inherit a newer cwd checkout.
    explicit_root = root is not None
    package = Path(__file__).absolute().parent
    source_package = package.parent.name == 'src' and (package.parent.parent / 'pyproject.toml').is_file()
    installed_commit = _package_commit() if not explicit_root and not source_package else None
    root = Path(root).absolute() if root is not None else source_root()
    frontend = Path(frontend_dist).absolute() if frontend_dist is not None else root / 'frontend' / 'dist' if root is not None else None
    frontend_commit = read_frontend_commit(frontend)
    if root is None:
        return RunningVersion(None, _package_commit(), frontend_commit, None, frontend_root=frontend)
    try:
        root = safe_path(root)
        safe_path(root / 'release.json')
        manifest = release_manifest(root) if (root / 'release.json').exists() else None
        head, dirty = git_state(root)
        if not explicit_root and not source_package:
            commit = installed_commit
        else:
            commit = manifest['commit'] if manifest else head or _package_commit()
        identity_valid = not ((manifest and manifest['commit'] != commit) or (head is not None and head != commit))
        if manifest and head is not None and head != commit:
            dirty = True
        if manifest and head is None:
            dirty = False
        return RunningVersion(root, commit, frontend_commit, dirty, manifest is not None, frontend, identity_valid)
    except (OSError, ValueError):
        return RunningVersion(root, None, frontend_commit, None, frontend_root=frontend)


def release_root_matches(root, install_root):
    """Only the actual running tree, at an explicitly configured installation location."""
    if root is None or not install_root:
        return False
    try:
        root, install = safe_path(root), safe_path(install_root)
        if not root.is_dir() or not install.is_dir():
            return False
        if root == install:
            return True
        for releases in (install / 'releases', install / 'data' / 'system-update' / 'releases'):
            if root.parent == releases and valid_sha(root.name):
                manifest = release_manifest(root)
                return manifest['commit'] == root.name.lower()
    except (OSError, ValueError):
        return False
    return False
