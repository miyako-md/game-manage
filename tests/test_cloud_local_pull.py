import hashlib
import io
import json
from pathlib import Path
import tarfile
import subprocess
import sys

import pytest

from scripts.cloud import local_pull as pull
from scripts.cloud import local_pull_remote as remote

NAME = '20261014T000000Z-12345678'


def sample(root):
    root.mkdir(parents=True, exist_ok=True)
    files = []
    for relative in ('identity.db', 'data/snapshots.db'):
        path = root / 'cloud' / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'synthetic-' + relative.encode())
        files.append({'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'size': path.stat().st_size, 'kind': 'sqlite', 'sqlite_user_version': 3})
    (root / 'cloud/manifest.json').write_text(json.dumps({
        'format_version': 1, 'identity_schema_version': 3, 'key_included': False,
        'consistency': 'per_file_online', 'whole_system_snapshot': False, 'files': files}))
    (root / 'qq-state.db').write_bytes(b'synthetic-qq')
    (root / 'complete.json').write_text(json.dumps({
        'format': remote.FORMAT, 'key_included': False, 'consistency': 'per_file_online',
        'whole_system_snapshot': False,
        'qq_sha256': hashlib.sha256(b'synthetic-qq').hexdigest()}))
    return root


def archive(root):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as tar:
        for path in sorted(root.rglob('*')):
            if path.is_file():
                tar.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
    return output.getvalue()


class FakeTransport:
    def __init__(self, source):
        self.source = source
        self.downloads = 0

    def latest(self):
        return remote.inspect_set(self.source)

    def download(self, name, destination):
        assert name == NAME
        self.downloads += 1
        destination.write_bytes(archive(self.source))


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows NTFS atomic publication')
@pytest.mark.parametrize('version',[3,4])
def test_verified_set_is_published_and_repeat_skips_download(tmp_path,version):
    source = sample(tmp_path / 'server' / NAME)
    manifest_path=source/'cloud/manifest.json'
    manifest=json.loads(manifest_path.read_text())
    manifest['identity_schema_version']=version
    manifest_path.write_text(json.dumps(manifest))
    root = tmp_path / 'local'
    root.mkdir()
    transport = FakeTransport(source)
    assert pull.pull_latest(root, transport)['status'] == 'downloaded'
    assert (root / NAME / 'cloud/identity.db').read_bytes() == b'synthetic-identity.db'
    assert pull.pull_latest(root, transport)['status'] == 'already_present'
    assert transport.downloads == 1
    assert not (root / '.pull.lock').exists()


def test_tamper_preserves_existing_copy_and_does_not_publish(tmp_path):
    source = sample(tmp_path / 'server' / NAME)
    original = source / 'cloud/identity.db'
    original.write_bytes(b'x' * original.stat().st_size)
    root = tmp_path / 'local'
    root.mkdir()
    other = root / 'unrelated.txt'
    other.write_text('keep')
    with pytest.raises(ValueError, match='digest'):
        pull.pull_latest(root, FakeTransport(source))
    assert not (root / NAME).exists()
    assert other.read_text() == 'keep'
    assert list(root.glob('.pending-*'))


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'cloud/../escape', 'cloud/C:secret',
                                 'cloud\\escape', 'cloud/NUL', 'cloud/name.'])
def test_unsafe_tar_paths_never_write_outside_stage(tmp_path, name):
    content = io.BytesIO()
    with tarfile.open(fileobj=content, mode='w') as tar:
        info = tarfile.TarInfo(name)
        info.size = 1
        tar.addfile(info, io.BytesIO(b'x'))
    download = tmp_path / 'download.tar'
    download.write_bytes(content.getvalue())
    stage = tmp_path / 'stage'
    stage.mkdir()
    with pytest.raises(ValueError):
        pull.extract(download, stage)
    assert not (tmp_path / 'escape').exists()


@pytest.mark.parametrize('kind', [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_links_and_special_archive_members_rejected(tmp_path, kind):
    download = tmp_path / 'download.tar'
    with tarfile.open(download, 'w') as tar:
        info = tarfile.TarInfo('cloud/identity.db')
        info.type = kind
        info.linkname = '../outside'
        tar.addfile(info)
    stage = tmp_path / 'stage'
    stage.mkdir()
    with pytest.raises(ValueError, match='archive'):
        pull.extract(download, stage)


def test_case_collision_and_duplicate_archive_names_rejected(tmp_path):
    for index, names in enumerate([('cloud/a.db', 'cloud/A.db'), ('cloud/a.db', 'cloud/a.db')]):
        download = tmp_path / 'download.tar'
        with tarfile.open(download, 'w') as tar:
            for name in names:
                info = tarfile.TarInfo(name)
                tar.addfile(info)
        stage = tmp_path / str(index)
        stage.mkdir(exist_ok=True)
        with pytest.raises(ValueError):
            pull.extract(download, stage)


def test_extra_secret_and_manifest_traversal_are_rejected(tmp_path):
    source = sample(tmp_path / 'set')
    (source / 'grants.key').write_bytes(b'never copy')
    with pytest.raises(ValueError, match='inventory'):
        remote.inspect_set(source)
    (source / 'grants.key').unlink()
    manifest = json.loads((source / 'cloud/manifest.json').read_text())
    manifest['files'][0]['path'] = '../grants.key'
    (source / 'cloud/manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        remote.inspect_set(source)


def test_remote_listing_only_reads_metadata_and_skips_pending(tmp_path, monkeypatch):
    sample(tmp_path / NAME)
    (tmp_path / '.pending-failed').mkdir()
    original = Path.open
    def guarded(path, *args, **kwargs):
        if path.name not in {'complete.json', 'manifest.json'}:
            raise AssertionError('payload read during metadata listing')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)
    assert remote.latest(tmp_path)['name'] == NAME


def test_no_completed_set_does_not_create_stage(tmp_path):
    class Empty:
        def latest(self):
            return None
    assert pull.pull_latest(tmp_path, Empty())['status'] == 'no_complete_set'
    assert not list(tmp_path.glob('.pending-*'))


def test_count_size_and_timeout_are_bounded(tmp_path, monkeypatch):
    source = sample(tmp_path / 'set')
    monkeypatch.setattr(remote, 'MAX_FILES', 2)
    with pytest.raises(ValueError, match='limit'):
        remote.inspect_set(source)
    assert pull.TIMEOUT_SECONDS <= 900
    assert pull.MAX_ARCHIVE_BYTES <= 2 * 1024**3 + 16 * 1024**2


def test_default_cli_is_metadata_only_and_failure_output_is_safe(tmp_path, monkeypatch, capsys):
    class Metadata:
        def __init__(self, *args):
            pass
        def latest(self):
            return {'name': NAME, 'files': 4, 'bytes': 100}
        def download(self, *args):
            raise AssertionError('download in dry run')
    monkeypatch.setattr(pull, 'SSHTransport', Metadata)
    assert pull.main([]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'metadata_only'
    class Broken(Metadata):
        def latest(self):
            raise ValueError('private TOKEN must never print')
    monkeypatch.setattr(pull, 'SSHTransport', Broken)
    assert pull.main([]) == 2
    output = capsys.readouterr()
    assert 'TOKEN' not in output.err + output.out
    assert output.err.strip() == 'local_pull_failed'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows NTFS directory permissions')
def test_ntfs_root_permissions_and_unsafe_existing_acl(tmp_path):
    root = tmp_path / 'owner-only'
    assert pull.prepare_root(root) == root
    pending = root / '.pending-valid'
    pending.mkdir()
    (pending / 'partial.tar').write_bytes(b'synthetic')
    assert pull.prepare_root(root) == root
    with pytest.raises(ValueError, match='secure_root'):
        pull.prepare_root(tmp_path)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows NTFS directory permissions')
def test_windows_private_mkdir_acl_is_accepted_without_widening(tmp_path):
    root = pull.prepare_root(tmp_path / 'secured')
    pending = root / '.pending-private'
    pending.mkdir(mode=0o700)
    (pending / 'set').mkdir(mode=0o700)
    (pending / 'set/partial.tar').write_bytes(b'synthetic')
    assert pull.prepare_root(root) == root


def test_parent_link_is_rejected_before_manifest_read(tmp_path, monkeypatch):
    source = sample(tmp_path / 'set')
    original = remote.plain
    def reject_cloud(path):
        if path == source / 'cloud':
            raise ValueError('unsafe_file')
        return original(path)
    monkeypatch.setattr(remote, 'plain', reject_cloud)
    original_metadata = remote.metadata
    def guarded_metadata(path):
        if path == source / 'cloud/manifest.json':
            raise AssertionError('manifest read before checking parent')
        return original_metadata(path)
    monkeypatch.setattr(remote, 'metadata', guarded_metadata)
    with pytest.raises(ValueError, match='unsafe_file'):
        remote.inspect_set(source)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows NTFS directory permissions')
def test_existing_child_acl_cannot_bypass_owner_only_root(tmp_path):
    root = pull.prepare_root(tmp_path / 'secured')
    pending = root / '.pending-synthetic'
    pending.mkdir()
    script = """
$ErrorActionPreference='Stop'
$p='PATH_LITERAL'
$directory=New-Object System.IO.DirectoryInfo($p)
$acl=$directory.GetAccessControl()
$everyone=New-Object System.Security.Principal.SecurityIdentifier('S-1-1-0')
$acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($everyone,'Read','Allow')))
$directory.SetAccessControl($acl)
""".replace('PATH_LITERAL', str(pending).replace("'", "''"))
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', script], capture_output=True)
    assert result.returncode == 0
    with pytest.raises(ValueError, match='secure_root'):
        pull.prepare_root(root)


def test_incomplete_download_never_publishes_or_leaves_lock(tmp_path):
    source = sample(tmp_path / 'server' / NAME)
    root = tmp_path / 'local'
    root.mkdir()
    class Interrupted(FakeTransport):
        def download(self, name, destination):
            destination.write_bytes(b'partial')
            raise OSError('network disconnected; private text')
    with pytest.raises(OSError):
        pull.pull_latest(root, Interrupted(source))
    assert not (root / NAME).exists()
    assert not (root / '.pull.lock').exists()
    assert list(root.glob('.pending-*'))


def test_concurrent_lock_is_not_deleted_by_rejected_process(tmp_path):
    source = sample(tmp_path / 'server' / NAME)
    root = tmp_path / 'local'
    root.mkdir()
    (root / '.pull.lock').write_bytes(b'existing lock')
    with pytest.raises(FileExistsError):
        pull.pull_latest(root, FakeTransport(source))
    assert (root / '.pull.lock').read_bytes() == b'existing lock'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows SSH process creation flags')
@pytest.mark.parametrize('mode', ['limit', 'timeout', 'exit'])
def test_transport_bounds_real_local_subprocess(tmp_path, monkeypatch, mode):
    key = tmp_path / 'synthetic.pem'
    key.write_bytes(b'not a real key')
    transport = pull.SSHTransport(key)
    assert 'StrictHostKeyChecking=yes' in transport.base
    assert 'BatchMode=yes' in transport.base
    monkeypatch.setattr(pull, 'MAX_ARCHIVE_BYTES', 10)
    code = "import sys,time; sys.stdin.buffer.read(); "
    code += {'limit': 'sys.stdout.buffer.write(b"x"*20)',
             'timeout': 'time.sleep(30)', 'exit': 'sys.exit(2)'}[mode]
    monkeypatch.setattr(transport, 'command', lambda *args: [sys.executable, '-c', code])
    monkeypatch.setattr(pull, 'TIMEOUT_SECONDS', 0.2 if mode == 'timeout' else 10)
    with pytest.raises(ValueError):
        transport.download(NAME, tmp_path / 'download.tar')


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows .NET ACL descriptor policy')
@pytest.mark.parametrize('case,owner,token_owner,enabled,aces,expected', [
    ('ordinary-user', 'user', 'user', False, [('user','FullControl','Allow','None')], True),
    ('ordinary-owner-rights', 'user', 'user', False, [('owner-rights','FullControl','Allow','None')], True),
    ('verified-admin-inherited-user', 'admin', 'admin', True, [('user','FullControl','Allow','None'),('admin','FullControl','Allow','None')], True),
    ('verified-admin-owner-rights', 'admin', 'admin', True, [('owner-rights','FullControl','Allow','None'),('system','FullControl','Allow','None')], True),
    ('disabled-admin', 'admin', 'admin', False, [('user','FullControl','Allow','None')], False),
    ('admin-is-not-token-owner', 'admin', 'user', True, [('user','FullControl','Allow','None')], False),
    ('foreign-owner', 'foreign', 'admin', True, [('user','FullControl','Allow','None')], False),
    ('foreign-default-owner', 'foreign', 'foreign', True, [('owner-rights','FullControl','Allow','None')], False),
    ('everyone-extra-read', 'admin', 'admin', True, [('user','FullControl','Allow','None'),('everyone','Read','Allow','None')], False),
    ('users-extra-full', 'admin', 'admin', True, [('owner-rights','FullControl','Allow','None'),('users','FullControl','Allow','None')], False),
    ('limited-user-rights', 'user', 'user', False, [('user','Read','Allow','None')], False),
    ('deny-user', 'user', 'user', False, [('user','FullControl','Deny','None')], False),
    ('inheritable-only', 'admin', 'admin', True, [('owner-rights','FullControl','Allow','InheritOnly')], False),
    ('user-owner-admin-ace-only', 'user', 'admin', True, [('admin','FullControl','Allow','None')], False),
    ('admin-owner-without-creator-access', 'admin', 'admin', True, [('system','FullControl','Allow','None')], False),
    ('empty-dacl', 'admin', 'admin', True, [], False),
])
def test_child_acl_uses_verified_actual_token_owner_without_widening(case,owner,token_owner,enabled,aces,expected):
    policy=getattr(pull,'CHILD_ACL_POLICY','')
    assert policy, 'Child ACL validator must distinguish User from the enabled actual token owner'
    ids={'user':'S-1-5-21-111111111-222222222-333333333-1001',
         'foreign':'S-1-5-21-111111111-222222222-333333333-1002',
         'admin':'S-1-5-32-544','system':'S-1-5-18','owner-rights':'S-1-3-4','everyone':'S-1-1-0','users':'S-1-5-32-545'}
    value={'user':ids['user'],'owner':ids[owner],'token_owner':ids[token_owner],'enabled':enabled,
           'aces':[[ids[principal],rights,kind,propagation] for principal,rights,kind,propagation in aces]}
    script=policy+"""
$ErrorActionPreference='Stop'
$value=ConvertFrom-Json 'JSON_LITERAL'
$acl=New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetOwner((New-Object System.Security.Principal.SecurityIdentifier($value.owner)))
$acl.SetAccessRuleProtection($true,$false)
foreach($ace in $value.aces){
    $rule=New-Object System.Security.AccessControl.FileSystemAccessRule(
        (New-Object System.Security.Principal.SecurityIdentifier($ace[0])),
        $ace[1],'ContainerInherit,ObjectInherit',$ace[3],$ace[2])
    $acl.AddAccessRule($rule)
}
$before=$acl.GetSecurityDescriptorSddlForm('All')
$result=Test-TrustedChildAcl $acl $value.user $value.token_owner $value.enabled
$after=$acl.GetSecurityDescriptorSddlForm('All')
@{accepted=[bool]$result;unchanged=($before -eq $after)} | ConvertTo-Json -Compress
""".replace('JSON_LITERAL',json.dumps(value,separators=(',',':')))
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,timeout=30)
    assert result.returncode==0,case
    observed=json.loads(result.stdout)
    assert observed=={'accepted':expected,'unchanged':True},case
