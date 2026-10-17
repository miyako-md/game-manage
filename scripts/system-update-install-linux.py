"""Provision the standalone updater only on an explicitly managed Linux host.

Dry validation is the default. --install is an operator action, never invoked by
an HTTP endpoint. This does not adopt unverified releases or change live code.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import stat

# Do not import the application's site-packages even for the initial install.
# The operator must use /usr/bin/python3 -I -S on this reviewed root-owned source.
if not sys.flags.isolated or not sys.flags.no_site or Path(sys.executable).resolve().parent != Path('/usr/bin'):
    raise SystemExit('Use the reviewed system Python: /usr/bin/python3 -I -S this-script.py')
bootstrap_path = Path(__file__).resolve().with_name('system-update-helper.py')
for checked in (Path(__file__).resolve(), bootstrap_path):
    for item in (checked, *checked.parents):
        info = item.lstat()
        if (stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or
                info.st_mode & 0o022 and not (stat.S_ISDIR(info.st_mode) and info.st_mode & stat.S_ISVTX)):
            raise SystemExit('Installer source must be operator-reviewed and root-owned')
spec = importlib.util.spec_from_file_location('_trusted_updater_bootstrap', bootstrap_path)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
bootstrap.require_isolated_system_python()
bootstrap.trusted_path(Path(__file__).resolve())
bootstrap.trusted_path(bootstrap_path)
worker = bootstrap.load_bundle(Path(__file__).resolve().parents[1] / 'src/game_assistant')
safe_path = worker.safe_path
load_config, release_identity, Runner, git_clean = worker.load_config, worker.release_identity, worker.Runner, worker.git_clean


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() != 0:
        parser.error('run as the Linux operator (root)')
    config = load_config(args.config)
    if config.platform != 'linux': parser.error('linux configuration required')
    config.validate(provisioned=False)
    for name in (config.api_user, config.qq_user, config.build_user):
        if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', name): parser.error('invalid service user')
    root = safe_path(config.install_root)
    if root.stat().st_uid != 0 or root.stat().st_mode & 0o022:
        parser.error('installation must be root-owned and not group/world writable')
    current = root / 'current'
    if not current.is_symlink(): parser.error('current must be a controlled release symlink')
    release = safe_path(current.resolve(strict=True))
    if release.parent != root / 'releases' or release_identity(release) != release.name:
        parser.error('release identity/layout is not managed')
    if git_clean(release, Runner()) != release.name: parser.error('release checkout is dirty')
    if not (release / 'src/game_assistant/system_update_worker.py').is_file():
        parser.error('installed release has no updater; bootstrap a reviewed release first')
    api = pwd.getpwnam(config.api_user)
    pwd.getpwnam(config.qq_user)
    for path in (root, config.state_dir, config.data_root, config.qq_data_root, config.config_path, args.config.absolute()):
        if any(ch.isspace() for ch in str(path)):
            parser.error('managed updater service paths cannot contain whitespace')
        safe_path(path)
    if not args.install:
        print('updater_installation_preconditions_valid; use --install to provision the helper')
        return 0
    try: pwd.getpwnam(config.build_user)
    except KeyError:
        subprocess.run(['useradd', '--system', '--no-create-home', '--shell', '/usr/sbin/nologin', config.build_user], check=True)
    state = safe_path(config.state_dir)
    state.mkdir(mode=0o3770, parents=True, exist_ok=True)
    os.chown(state, 0, api.pw_gid); os.chmod(state, 0o3770)
    queue = safe_path(state / 'queue.lock')
    fd = os.open(queue, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o660)
    os.close(fd)
    os.chown(queue, 0, api.pw_gid); os.chmod(queue, 0o660)
    private = safe_path(root / '.updater')
    private.mkdir(mode=0o700, exist_ok=True)
    os.chown(private, 0, 0); os.chmod(private, 0o700)
    releases = safe_path(root / 'releases')
    os.chmod(releases, 0o755)
    config.validate()
    helper = safe_path(private / 'helper')
    helper.mkdir(mode=0o700, exist_ok=True)
    reviewed = {
        'entry.py': bootstrap_path,
        'system_update_worker.py': Path(__file__).resolve().parents[1] / 'src/game_assistant/system_update_worker.py',
        'system_update_protocol.py': Path(__file__).resolve().parents[1] / 'src/game_assistant/system_update_protocol.py',
    }
    for name, source in reviewed.items():
        source = bootstrap.trusted_path(source)
        destination = safe_path(helper / name)
        payload = source.read_bytes()
        if destination.exists() and destination.read_bytes() != payload:
            parser.error('installed trusted helper differs; stop and review it before an explicit helper upgrade')
        destination.write_bytes(payload)
        os.chown(destination, 0, 0); destination.chmod(0o400)
    helper.chmod(0o500)
    probe = subprocess.run(['/usr/bin/python3', '-I', '-S', str(helper / 'entry.py'), '--probe'],
                           capture_output=True, text=True, timeout=20)
    if probe.returncode or probe.stdout.strip() != 'trusted_system_update_helper_ready':
        parser.error('trusted helper bootstrap validation failed')
    template = Path(__file__).resolve().parents[1] / 'deploy/cloud/game-manage-updater.service'
    text = template.read_text(encoding='utf-8')
    replacements = {
        '/etc/game-manage-cloud/updater.json': str(args.config.absolute()),
        '/opt/game-manage-cloud': str(root),
        '/var/lib/game-manage-updater': str(state),
        '/var/lib/game-manage-cloud': str(config.data_root),
        '/var/lib/game-manage-qq': str(config.qq_data_root),
    }
    for old, new in replacements.items(): text = text.replace(old, new)
    unit = Path('/etc/systemd/system/game-manage-updater.service')
    safe_path(unit)
    if unit.exists() and unit.read_text(encoding='utf-8') != text:
        parser.error('an updater unit already exists; review it before replacing')
    unit.write_text(text, encoding='utf-8'); unit.chmod(0o644)
    # Only the queue directory becomes writable to the API. Source, releases,
    # root recovery journal, service control and QQ state remain inaccessible.
    dropin = safe_path(Path('/etc/systemd/system') / (config.api_service + '.d') / 'system-update-state.conf')
    dropin.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    rule = '[Service]\nReadWritePaths=' + str(state) + '\n'
    if dropin.exists() and dropin.read_text(encoding='utf-8') != rule:
        parser.error('API updater drop-in differs; operator review required')
    dropin.write_text(rule, encoding='utf-8'); dropin.chmod(0o644)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'game-manage-updater.service'], check=True)
    print('updater_helper_installed; restart API deliberately to apply its state-only sandbox allowance, then enable update settings after checking heartbeat')
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception:
        print('updater_installation_failed; no configuration values were logged', file=sys.stderr)
        raise SystemExit(1) from None
