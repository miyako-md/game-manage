"""Trusted stdlib-only bootstrap, installed separately from every candidate venv.

Always run with the operator's system Python: /usr/bin/python3 -I -S entry.py.
This file and its two sibling modules are copied only during explicit operator
installation/review. A downloaded release never replaces the privileged helper.
"""
import importlib.util
import os
from pathlib import Path
import stat
import sys
import types


def trusted_path(value):
    path = Path(value).absolute()
    for entry in (path, *path.parents):
        info = entry.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0:
            raise RuntimeError('helper_path_not_trusted')
        # A root-owned sticky /tmp ancestor is safe for isolated acceptance
        # fixtures: unprivileged users cannot replace the root-owned child.
        if info.st_mode & 0o022 and not (stat.S_ISDIR(info.st_mode) and info.st_mode & stat.S_ISVTX):
            raise RuntimeError('helper_path_not_trusted')
    return path


def require_isolated_system_python():
    if not sys.flags.isolated or not sys.flags.no_site or sys.version_info < (3, 11):
        raise RuntimeError('system_python_isolation_required')
    executable = Path(sys.executable).resolve(strict=True)
    trusted_path(executable)
    if executable.parent != Path('/usr/bin'):
        raise RuntimeError('operator_system_python_required')
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise RuntimeError('linux_root_helper_required')


def load_bundle(directory):
    directory = trusted_path(directory)
    name = '_game_manage_trusted_updater'
    package = types.ModuleType(name)
    package.__path__ = [str(directory)]
    sys.modules[name] = package
    for module in ('system_update_protocol', 'system_update_worker'):
        filename = trusted_path(directory / (module + '.py'))
        if not stat.S_ISREG(filename.stat().st_mode):
            raise RuntimeError('helper_module_not_regular')
        full = name + '.' + module
        spec = importlib.util.spec_from_file_location(full, filename)
        loaded = importlib.util.module_from_spec(spec)
        sys.modules[full] = loaded
        spec.loader.exec_module(loaded)
    return sys.modules[name + '.system_update_worker']


def main():
    require_isolated_system_python()
    entry = trusted_path(Path(__file__).absolute())
    worker = load_bundle(entry.parent)
    if sys.argv[1:] == ['--probe']:
        print('trusted_system_update_helper_ready')
        return 0
    return worker.main()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('trusted_system_update_helper_unavailable', file=sys.stderr)
        raise SystemExit(1) from None
