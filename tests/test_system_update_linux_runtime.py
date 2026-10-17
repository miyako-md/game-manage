"""Opt-in root/systemd acceptance, using only random transient units/temp data.

Run only on a disposable Linux CI host with GA_RUN_LINUX_UPDATER_TESTS=1.
No game-manage/QQ service, real data, installed account or deployment is touched.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

import pytest

from game_assistant.system_update_worker import Runner, UpdateError, write_public_json

pytestmark = pytest.mark.skipif(
    sys.platform != 'linux' or getattr(os, 'geteuid', lambda:-1)() != 0
    or os.environ.get('GA_RUN_LINUX_UPDATER_TESTS') != '1',
    reason='explicit isolated Linux root/systemd acceptance only',
)


def systemctl(*args):
    return subprocess.run(['systemctl', *args], capture_output=True, text=True, timeout=30)


@pytest.fixture
def isolated():
    # /tmp is root-owned/sticky; the trusted bootstrap rejects user-owned
    # ancestors such as /home/runner even if the immediate file is root-owned.
    with tempfile.TemporaryDirectory(prefix='game-manage-updater-test-', dir='/tmp') as tmp:
        root = Path(tmp); root.chmod(0o755)
        candidate = root / 'candidate'; candidate.mkdir(mode=0o755)
        home = root / 'build-home'; home.mkdir(mode=0o700)
        os.chown(candidate, 65534, 65534); os.chown(home, 65534, 65534)
        unit = 'game-manage-updater-test-lifecycle-' + uuid.uuid4().hex + '.service'
        subprocess.run(['systemd-run','--quiet','--unit='+unit,'--service-type=exec',
                        '--property=KillMode=control-group','/bin/sleep','120'],
                       check=True, capture_output=True, timeout=30)
        run = Runner(unit)
        try:
            assert systemctl('is-active','--quiet',unit).returncode == 0
            yield root, candidate, home, unit, run
        finally:
            if run.last_unit:
                systemctl('stop',run.last_unit); systemctl('reset-failed',run.last_unit)
            systemctl('stop',unit); systemctl('reset-failed',unit)


def wait_file(path, seconds=12):
    until = time.monotonic()+seconds
    while time.monotonic()<until:
        if path.is_file(): return
        time.sleep(.05)
    pytest.fail('isolated child did not reach its readiness point')


def assert_not_running(pid):
    info = Path('/proc')/str(pid)/'stat'
    if info.exists():
        assert info.read_text().split(') ',1)[1].split()[0] in {'Z','X'}, 'background process is still live'


def test_background_setsid_child_with_open_write_fd_is_gone_before_build_returns(isolated):
    root, candidate, home, unit, run = isolated
    target = candidate/'source.txt'; target.write_text('before'); os.chown(target,65534,65534)
    child = (
        'import os,sys,time; '
        'fd=os.open(sys.argv[1],os.O_WRONLY|os.O_TRUNC); '
        'open(sys.argv[2],"w").write(str(os.getpid())); '
        'time.sleep(2); os.write(fd,b"late modification"); os.close(fd)'
    )
    parent = (
        'import subprocess,sys,time,pathlib; '
        'p=subprocess.Popen([sys.executable,"-I","-S","-c",sys.argv[1],sys.argv[2],sys.argv[3]],'
        'start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); '
        '\nwhile not pathlib.Path(sys.argv[3]).exists(): time.sleep(.01)\n'
    )
    pidfile=candidate/'child.pid'
    run(['/usr/bin/python3','-I','-S','-c',parent,child,str(target),str(pidfile)],
        cwd=candidate, env={'PATH':'/usr/bin:/bin','HOME':str(home)},user=65534,group=65534,
        write_paths=(candidate,home),timeout=15)
    pid=int(pidfile.read_text()); assert_not_running(pid)
    # The worker's final hash/freeze starts here, after Runner has returned.
    target.write_text('frozen'); os.chown(target,0,0); target.chmod(0o644)
    time.sleep(2.2)
    assert target.read_text() == 'frozen', 'a retained FD mutated the frozen candidate'
    assert run._stopped(run.last_unit)


def test_stopping_lifecycle_unit_reaps_build_and_detached_children(isolated):
    root, candidate, home, unit, run = isolated
    pidfile = candidate/'child.pid'
    child = 'import os,sys,time;open(sys.argv[1],"w").write(str(os.getpid()));time.sleep(90)'
    parent = 'import subprocess,sys,time;subprocess.Popen([sys.executable,"-I","-S","-c",sys.argv[1],sys.argv[2]],start_new_session=True);time.sleep(90)'
    errors=[]
    def build():
        try:
            run(['/usr/bin/python3','-I','-S','-c',parent,child,str(pidfile)],cwd=candidate,
                env={'PATH':'/usr/bin:/bin','HOME':str(home)},user=65534,group=65534,
                write_paths=(candidate,home),timeout=100)
        except UpdateError as error: errors.append(str(error))
    thread=threading.Thread(target=build,daemon=True);thread.start()
    wait_file(pidfile)
    assert systemctl('stop',unit).returncode == 0
    thread.join(timeout=25)
    assert not thread.is_alive(), 'lifecycle stop left a running build'
    assert_not_running(int(pidfile.read_text()))
    assert run._stopped(run.last_unit)


def test_trusted_helper_does_not_execute_candidate_pth_even_with_poisoned_environment():
    source=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='game-manage-updater-bootstrap-',dir='/tmp') as tmp:
        root=Path(tmp);root.chmod(0o700)
        candidate=root/'candidate-venv'
        subprocess.run(['/usr/bin/python3','-I','-S','-m','venv','--without-pip',str(candidate)],
                       check=True,capture_output=True,timeout=30)
        site=next((candidate/'lib').glob('python*/site-packages'))
        marker=root/'pth-executed'
        (site/'unsafe.pth').write_text('import pathlib; pathlib.Path('+repr(str(marker))+').write_text("executed")\n')
        subprocess.run([str(candidate/'bin/python'),'-c','pass'],check=True,capture_output=True,timeout=15)
        assert marker.exists(), 'control did not demonstrate candidate .pth execution'
        marker.unlink()
        helper=root/'helper';helper.mkdir(mode=0o700)
        for name,original in {
            'entry.py':source/'scripts/system-update-helper.py',
            'system_update_worker.py':source/'src/game_assistant/system_update_worker.py',
            'system_update_protocol.py':source/'src/game_assistant/system_update_protocol.py',
        }.items():
            shutil.copyfile(original,helper/name);(helper/name).chmod(0o400)
        helper.chmod(0o500)
        result=subprocess.run(['/usr/bin/python3','-I','-S',str(helper/'entry.py'),'--probe'],
            cwd=candidate,env={**os.environ,'PYTHONPATH':str(site),'VIRTUAL_ENV':str(candidate),
                              'PATH':str(candidate/'bin')+':/usr/bin:/bin'},capture_output=True,text=True,timeout=15)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == 'trusted_system_update_helper_ready'
        assert not marker.exists()


def test_atomic_public_status_is_always_readable_by_api_group():
    with tempfile.TemporaryDirectory(prefix='game-manage-updater-public-',dir='/tmp') as tmp:
        root=Path(tmp);root.chmod(0o755)
        state=root/'state';state.mkdir();os.chown(state,0,65534);state.chmod(0o3770)
        status=state/'status.json';ready=state/'reader-ready';stop=state/'reader-stop'
        write_public_json(status,{'phase':'stopping'},65534)
        script=(
            'import json,pathlib,sys; s,r,stop=map(pathlib.Path,sys.argv[1:]); '
            'r.write_text("ready"); n=0\n'
            'while not stop.exists():\n'
            ' data=json.loads(s.read_text()); assert data["phase"] in {"stopping","verifying"}; n+=1\n'
            'print(n)\n'
        )
        child=subprocess.Popen(['/usr/bin/python3','-I','-S','-c',script,str(status),str(ready),str(stop)],
            user=65534,group=65534,extra_groups=[],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            wait_file(ready)
            for _ in range(50):
                write_public_json(status,{'phase':'verifying'},65534)
                assert status.stat().st_uid==0 and status.stat().st_gid==65534
                assert status.stat().st_mode & 0o777==0o640
                time.sleep(.001)
            stop.write_text('stop');stop.chmod(0o644)
            stdout,stderr=child.communicate(timeout=10)
            assert child.returncode==0,stderr
            assert int(stdout.strip())>0
        finally:
            if child.poll() is None: child.kill();child.wait(timeout=5)
