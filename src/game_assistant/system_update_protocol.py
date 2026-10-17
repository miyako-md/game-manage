"""Small, bounded file protocol shared by the web API and the external updater.

The queue lock must cover publication AND worker claim. Lock files are permanent:
never unlink/replace a lock inode while another process may still hold it.
"""
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
import time

MAX_JSON_BYTES = 65536
ACTIVE_PHASES = frozenset({'queued', 'preparing', 'stopping', 'backing_up',
                           'activating', 'restarting', 'verifying'})
TERMINAL_PHASES = frozenset({'completed', 'failed', 'rolled_back', 'recovery_required'})
PHASES = ACTIVE_PHASES | TERMINAL_PHASES


class ProtocolError(ValueError):
    """Unsafe path, malformed/bounded file or unsupported protocol."""


class LockBusyError(ProtocolError):
    """Another thread/process currently owns this lock."""


def valid_sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{40}', value) is not None


def safe_path(value):
    """Refuse symlinks and Windows junctions/reparse points, including ancestors."""
    path = Path(value).absolute()
    for item in reversed((path, *path.parents)):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ProtocolError('unsafe_update_path')
    return path


def read_json(path, maxbytes=MAX_JSON_BYTES):
    if type(maxbytes) is not int or not 0 < maxbytes <= MAX_JSON_BYTES:
        raise ProtocolError('invalid_json_limit')
    path = safe_path(path)
    flags = os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maxbytes:
            raise ProtocolError('invalid_update_file')
        with os.fdopen(fd, 'rb') as handle:
            fd = None
            raw = handle.read(maxbytes + 1)
        if len(raw) > maxbytes:
            raise ProtocolError('update_file_too_large')
        # Reject non-finite values: timestamps must never be NaN/Infinity.
        def invalid_constant(_value):
            raise ProtocolError('invalid_update_json')
        value = json.loads(raw.decode('utf-8'), parse_constant=invalid_constant)
        if not isinstance(value, dict):
            raise ProtocolError('invalid_update_json')
        safe_path(path)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ProtocolError('invalid_update_json') from error
    finally:
        if fd is not None:
            os.close(fd)


def write_json_atomic(path, value):
    if not isinstance(value, dict):
        raise ProtocolError('invalid_update_json')
    try:
        encoded = (json.dumps(value, ensure_ascii=False, allow_nan=False,
                              separators=(',', ':')) + '\n').encode('utf-8')
    except (TypeError, ValueError, RecursionError) as error:
        raise ProtocolError('invalid_update_json') from error
    if len(encoded) > MAX_JSON_BYTES:
        raise ProtocolError('update_file_too_large')
    path = safe_path(path)
    if not path.parent.is_dir():
        raise ProtocolError('update_directory_missing')
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ProtocolError('invalid_update_file')
    except FileNotFoundError:
        pass
    fd, staging = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        os.chmod(staging, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            fd = None
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        safe_path(path)
        os.replace(staging, path)
        # Make publication durable before returning/allowing the queue lock to go.
        if os.name != 'nt':
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(staging)
        except FileNotFoundError:
            pass


_registry_guard = threading.Lock()
_thread_locks = {}


@contextmanager
def lock(path, blocking=False):
    path = safe_path(path)
    key = os.path.normcase(str(path))
    with _registry_guard:
        local = _thread_locks.setdefault(key, threading.Lock())
    if not local.acquire(blocking=blocking):
        raise LockBusyError('update_lock_busy')
    fd = None
    held = False
    try:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
        fd = os.open(path, flags, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ProtocolError('unsafe_update_lock')
        safe_path(path)
        if info.st_size == 0:
            os.write(fd, b'0')
        if os.name == 'nt':
            import msvcrt
            while True:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    held = True
                    break
                except OSError as error:
                    if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    if not blocking:
                        raise LockBusyError('update_lock_busy') from error
                    time.sleep(0.05)
        else:
            import fcntl
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
                held = True
            except BlockingIOError as error:
                raise LockBusyError('update_lock_busy') from error
        yield
    finally:
        if fd is not None:
            try:
                if held:
                    if os.name == 'nt':
                        import msvcrt
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        local.release()
