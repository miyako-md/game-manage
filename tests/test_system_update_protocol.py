import os
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
from types import SimpleNamespace

import pytest

from game_assistant.system_update_protocol import (MAX_JSON_BYTES, ProtocolError,
    LockBusyError, lock, read_json, write_json_atomic, safe_path, valid_sha)


def test_bounded_atomic_json_and_private_file_mode(tmp_path):
    path = tmp_path / 'request.json'
    write_json_atomic(path, {'schema': 1, 'message': '真实状态'})
    assert read_json(path) == {'schema': 1, 'message': '真实状态'}
    assert not list(tmp_path.glob('.request.json-*'))
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600
    write_json_atomic(path, {'schema': 1, 'next': True})
    assert read_json(path) == {'schema': 1, 'next': True}


@pytest.mark.parametrize('raw', ['[]', 'null', '{', '{"time":NaN}', '{"time":Infinity}', 'x' * (MAX_JSON_BYTES+1)],
                         ids=['list', 'null', 'malformed', 'nan', 'infinity', 'oversized'])
def test_malformed_or_oversized_json_is_not_an_empty_state(tmp_path, raw):
    path = tmp_path / 'status.json'
    path.write_text(raw)
    with pytest.raises((ValueError, ProtocolError)):
        read_json(path)


def test_missing_file_stays_distinct_and_rejected_write_preserves_old_status(tmp_path):
    path = tmp_path / 'status.json'
    with pytest.raises(FileNotFoundError):
        read_json(path)
    write_json_atomic(path, {'state': 'old'})
    for value in [[], {'text': 'a' * MAX_JSON_BYTES}, {'value': float('nan')}]:
        with pytest.raises(ProtocolError):
            write_json_atomic(path, value)
        assert read_json(path) == {'state': 'old'}


def test_linked_files_and_linked_parent_are_rejected_without_changing_target(tmp_path):
    target = tmp_path / 'outside'
    target.mkdir()
    original = target / 'status.json'
    original.write_text('{"old":true}')
    link = tmp_path / 'linked'
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip('symlink creation is unavailable on this runner')
    for operation in [lambda: read_json(link / 'status.json'),
                      lambda: write_json_atomic(link / 'status.json', {'old': False}),
                      lambda: lock(link / 'queue.lock').__enter__()]:
        with pytest.raises(ProtocolError):
            operation()
    assert original.read_text() == '{"old":true}'


def test_windows_reparse_attributes_are_rejected_even_when_not_a_symlink(tmp_path, monkeypatch):
    from pathlib import Path
    original = Path.lstat
    def attributes(path):
        info = original(path)
        return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400) if path == tmp_path else info
    monkeypatch.setattr(Path, 'lstat', attributes)
    with pytest.raises(ProtocolError):
        safe_path(tmp_path / 'request.json')


def test_lock_is_cross_thread_nonblocking_and_different_paths_are_independent(tmp_path):
    path = tmp_path / 'queue.lock'
    def attempt():
        with lock(path):
            return True
    with lock(path):
        with pytest.raises(LockBusyError):
            with lock(path):
                pass
        with ThreadPoolExecutor(1) as pool:
            with pytest.raises(LockBusyError):
                pool.submit(attempt).result()
        with lock(tmp_path / 'worker.lock'):
            pass
    assert attempt() is True


def test_lock_is_cross_process_and_released_after_exception(tmp_path):
    path = tmp_path / 'queue.lock'
    script = '''
from game_assistant.system_update_protocol import lock, LockBusyError
import sys
try:
 with lock(sys.argv[1]): pass
except LockBusyError:
 sys.exit(7)
'''
    with lock(path):
        result = subprocess.run([sys.executable, '-c', script, str(path)], capture_output=True)
        assert result.returncode == 7, result.stderr.decode()
    with pytest.raises(RuntimeError):
        with lock(path):
            raise RuntimeError()
    assert subprocess.run([sys.executable, '-c', script, str(path)], capture_output=True).returncode == 0


def test_sha_is_exact_and_never_a_branch_path_or_client_command():
    assert valid_sha('a' * 40) and valid_sha('B' * 40)
    for value in ['main', 'a' * 39, 'a' * 41, 'a' * 40 + '\n', '../main', '$(whoami)', None, 4]:
        assert not valid_sha(value)


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='named pipes are POSIX-only')
def test_named_pipe_is_rejected_without_waiting_for_a_writer_or_replacing_it(tmp_path):
    import stat
    path = tmp_path / 'status.json'
    os.mkfifo(path)
    with pytest.raises(ProtocolError):
        read_json(path)
    with pytest.raises(ProtocolError):
        write_json_atomic(path, {'schema':1})
    assert stat.S_ISFIFO(path.stat().st_mode)
