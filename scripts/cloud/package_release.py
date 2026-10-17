"""Build a local cloud release from one exact Git commit; never deploy it.

Work directories retain build dependencies/logs and are not release artifacts.
No working-tree file is copied into the release.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import uuid
import zipfile


class PackageError(ValueError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path(value):
    path = Path(value).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise PackageError('linked_path_rejected')
    return path.resolve()


def member_path(name, *, source=False):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise PackageError('unsafe_archive_path')
    parts = {part.lower() for part in path.parts}
    if source and '.superpowers' in parts:
        return None
    if parts & {'.git', '.superpowers', '.venv', 'node_modules', '__pycache__', '.pytest_cache',
                'private-backups', '.private-cloud-probes', 'local-game-icons', 'data', 'private'}:
        raise PackageError('private_or_dependency_path_rejected')
    lower = path.name.lower()
    if (lower == 'config.toml' or lower.startswith('.env') and lower != '.env.example'
            or lower.endswith(('.db', '.sqlite', '.sqlite3', '.pyc', '.pyo', '.key', '.pem', '.map'))
            or '.credentials.' in lower or lower.endswith('.env')):
        raise PackageError('private_or_generated_file_rejected')
    return path


def export_source(raw_tar, destination, archive, epoch):
    excluded, seen = [], set()
    with tarfile.open(fileobj=io.BytesIO(raw_tar), mode='r:') as incoming, tarfile.open(archive, 'w:gz') as outgoing:
        for member in incoming:
            relative = member_path(member.name, source=True)
            if relative is None:
                excluded.append(member.name)
                continue
            if member.isdir():
                continue
            if not member.isfile() or str(relative).casefold() in seen:
                raise PackageError('special_or_duplicate_source_member')
            seen.add(str(relative).casefold())
            payload = incoming.extractfile(member).read()
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            if os.name != 'nt':
                target.chmod(member.mode & 0o777)
            info = tarfile.TarInfo(str(relative))
            info.size, info.mode, info.mtime = len(payload), member.mode & 0o777, epoch
            outgoing.addfile(info, io.BytesIO(payload))
    return sorted(excluded)


def archive_tree(root, archive, epoch):
    with tarfile.open(archive, 'w:gz') as output:
        for item in sorted(root.rglob('*')):
            safe_path(item)
            if not item.is_file():
                continue
            relative = member_path(item.relative_to(root).as_posix())
            payload = item.read_bytes()
            info = tarfile.TarInfo(str(relative))
            info.size, info.mode, info.mtime = len(payload), 0o644, epoch
            output.addfile(info, io.BytesIO(payload))


def verify_wheel(source, wheel):
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(name.casefold() for name in names)):
            raise PackageError('duplicate_wheel_member')
        for name in names:
            member_path(name)
        count = 0
        for item in (source / 'src/game_assistant').rglob('*'):
            if item.is_file() and item.suffix in {'.py', '.json'}:
                relative = item.relative_to(source / 'src').as_posix()
                if relative not in names or archive.read(relative) != item.read_bytes():
                    raise PackageError('wheel_source_mismatch')
                count += 1
        return count


def write_build_metadata(source, commit):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise PackageError('full_commit_sha_required')
    path = source / 'src/game_assistant/build-info.json'
    path.write_text(json.dumps({'schema': 1, 'source': 'miyako-md/game-manage', 'commit': commit}) + '\n', encoding='utf-8')


def package(repo, commit, output_root, work_root, npm):
    repo, output_root, work_root = map(safe_path, (repo, output_root, work_root))
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise PackageError('full_commit_sha_required')
    for left, right in ((repo, output_root), (repo, work_root)):
        if left == right or left.is_relative_to(right):
            raise PackageError('output_overlaps_source_root')
    if output_root == work_root or output_root.is_relative_to(work_root) or work_root.is_relative_to(output_root):
        raise PackageError('work_and_artifacts_overlap')
    final = output_root / commit
    if final.exists():
        raise PackageError('release_already_exists')
    resolved = subprocess.check_output(['git', 'rev-parse', commit + '^{commit}'], cwd=repo, text=True).strip()
    if resolved != commit:
        raise PackageError('commit_mismatch')
    epoch = int(subprocess.check_output(['git', 'show', '-s', '--format=%ct', commit], cwd=repo, text=True))
    output_root.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)
    work = work_root / (commit[:12] + '-' + uuid.uuid4().hex[:8])
    source, artifacts = work / 'source', output_root / ('.pending-' + uuid.uuid4().hex[:12])
    source.mkdir(parents=True)
    artifacts.mkdir()
    env = dict(os.environ, SOURCE_DATE_EPOCH=str(epoch), PYTHONPATH='', PYTHONNOUSERSITE='1', GA_BUILD_COMMIT=commit)
    # Keep ambient Vite variables and local dotenv files out of this cloud build.
    env = {key: value for key, value in env.items() if not key.startswith('VITE_')}
    npm_path = shutil.which(npm)
    if not npm_path:
        raise PackageError('npm_unavailable')
    env['PATH'] = str(Path(npm_path).parent) + os.pathsep + env.get('PATH', '')
    logs = work / 'logs'
    logs.mkdir()

    def run(label, args, cwd=source):
        with (logs / (label + '.log')).open('wb') as log:
            result = subprocess.run(args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        if result.returncode:
            raise PackageError('build_step_failed:' + label)
        print('release_step_ok:' + label, flush=True)

    source_archive = artifacts / ('game-manage-source-' + commit + '.tar.gz')
    raw = subprocess.check_output(['git', '-c', 'core.autocrlf=false', 'archive', '--format=tar', commit], cwd=repo)
    excluded = export_source(raw, source, source_archive, epoch)
    driver = source / 'scripts/cloud/package_release.py'
    if not driver.is_file() or driver.read_bytes() != Path(__file__).read_bytes():
        raise PackageError('packaging_driver_must_match_commit')
    if not (source / 'docs/cloud-unified-release-package.md').is_file():
        raise PackageError('committed_release_runbook_required')
    project = tomllib.loads((source / 'pyproject.toml').read_text(encoding='utf-8'))
    if project['project']['optional-dependencies']['qq-render'] != ['playwright==1.58.0']:
        raise PackageError('browser_runtime_pin_requires_review')
    write_build_metadata(source, commit)
    build_env = work / 'build-env'
    run('build-environment', [sys.executable, '-m', 'venv', str(build_env)])
    build_python = build_env / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    run('build-tools', [str(build_python), '-m', 'pip', 'install', 'build==1.3.0',
                       *project['build-system']['requires'], 'wheel'])
    run('wheel', [str(build_python), '-m', 'build', '--wheel', '--no-isolation', '--outdir', str(artifacts)])
    wheels = list(artifacts.glob('*.whl'))
    if len(wheels) != 1:
        raise PackageError('one_wheel_required')
    matched = verify_wheel(source, wheels[0])
    run('npm-ci', [npm_path, 'ci'], cwd=source / 'frontend')
    run('cloud-frontend', [sys.executable, 'scripts/cloud/build_frontend.py', '--frontend', 'frontend'])
    dist = source / 'frontend/dist'
    if not (dist / 'render.html').is_file() or 'data-service-mode="cloud"' not in (dist / 'index.html').read_text(encoding='utf-8'):
        raise PackageError('cloud_render_entry_required')
    # Use the existing static validator with the caller's application environment.
    run('static-validation', [sys.executable, '-c',
        'import sys; sys.path.insert(0,"src"); from game_assistant.cloud_web_ui import validate_dist; validate_dist("frontend/dist")'])
    frontend_archive = artifacts / ('game-manage-cloud-frontend-' + commit + '.tar.gz')
    archive_tree(dist, frontend_archive, epoch)
    bundle = work / 'bundle'
    shutil.copytree(source / 'deploy/cloud', bundle / 'deploy/cloud')
    shutil.copytree(source / 'scripts/cloud', bundle / 'scripts/cloud')
    (bundle / 'docs').mkdir()
    for name in ('cloud-unified-release-package.md', 'cloud-operations.md', 'qq-browser-rendering.md',
                 '2026-10-14-phase-one-validation.md'):
        shutil.copyfile(source / 'docs' / name, bundle / 'docs' / name)
    archive_tree(bundle, artifacts / ('game-manage-cloud-operations-' + commit + '.tar.gz'), epoch)
    lockfiles = {name: sha256(source / name) for name in ('pyproject.toml', 'uv.lock', 'frontend/package-lock.json')}
    build_packages = subprocess.check_output([str(build_python), '-m', 'pip', 'freeze'], cwd=work, env=env, text=True).splitlines()
    manifest = {
        'format_version': 1, 'status': 'local_package_built', 'release_kind': 'candidate', 'source_commit': commit,
        'source_tree': subprocess.check_output(['git', 'rev-parse', commit + '^{tree}'], cwd=repo, text=True).strip(),
        'source_commit_time_utc': datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
        'built_at_utc': datetime.now(timezone.utc).isoformat(), 'build_platform': platform.platform(),
        'python_version': platform.python_version(),
        'node_version': subprocess.check_output(['node', '--version'], env=env, text=True).strip(),
        'npm_version': subprocess.check_output([npm_path, '--version'], env=env, text=True).strip(),
        'build_packages': build_packages, 'lockfiles_sha256': lockfiles,
        'packaging_driver_sha256': sha256(driver),
        'frontend_mode': 'cloud', 'frontend_render_entry': 'render.html',
        'wheel_source_files_byte_verified': matched, 'excluded_tracked_paths': excluded,
        'private_state_included': False, 'runtime_dependencies_bundled': False,
        'deployed': False, 'production_services_restarted': False,
        'linux_runtime_verified': False, 'real_cloud_account_acceptance_verified': False,
        'production_release_ready': False,
        'runtime_install': {'extras': ['qq', 'qq-render'], 'playwright': '1.58.0',
                            'linux_dependencies_and_browser': 'install matching Chromium with OS dependencies before service start',
                            'font': 'licensed service-readable Chinese font, not bundled'},
        'deployment_gates': ['Linux matching Chromium/system dependencies/font',
                             'Linux explicit sandbox verification (headless alone is not evidence)',
                             'actual systemd MemoryMax/TasksMax/CPUQuota load and shutdown validation',
                             'backups and new-directory restore/migration drill',
                             'real cloud grant/role/revoke and passive QQ reply acceptance'],
        'excluded_features': ['proactive QQ reminders', 'proactive subscription push', 'rankings', 'excluded old phase-two work'],
        'artifacts': [{'path': item.name, 'size': item.stat().st_size, 'sha256': sha256(item)}
                      for item in sorted(artifacts.iterdir())],
    }
    manifest_path = artifacts / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (artifacts / 'SHA256SUMS').write_text(''.join(sha256(item) + '  ' + item.name + '\n'
        for item in sorted(artifacts.iterdir()) if item.is_file()), encoding='utf-8')
    artifacts.rename(final)
    print(json.dumps({'status': 'local_package_built', 'commit': commit, 'artifacts': str(final),
                      'build_logs': str(logs), 'deployed': False}, ensure_ascii=False))
    return final


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--commit', required=True, help='Full immutable 40-character commit SHA')
    parser.add_argument('--output-root', required=True, help='Ignored local artifacts directory')
    parser.add_argument('--work-root', required=True, help='Separate ignored build/dependency directory')
    parser.add_argument('--npm', default='npm.cmd' if os.name == 'nt' else 'npm')
    args = parser.parse_args(argv)
    try:
        package(args.repo, args.commit, args.output_root, args.work_root, args.npm)
    except (PackageError, OSError, subprocess.SubprocessError, tarfile.TarError, zipfile.BadZipFile) as error:
        print('local_package_failed:' + (str(error) if isinstance(error, PackageError) else type(error).__name__), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
