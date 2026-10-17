import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from scripts.cloud.backup import OperationError, backup
from scripts.cloud.restore import restore
from game_assistant.cloud_runtime import load_runtime, build_app


def fixture(tmp_path):
    from game_assistant.identity.store import IdentityStore
    from game_assistant.auth.store import CredentialStore
    from game_assistant.accounts.service import AccountService
    from game_assistant.identity.models import Principal
    from game_assistant.snapshots import SnapshotStore
    root = tmp_path / 'live'
    root.mkdir()
    key = tmp_path / 'grant.key'
    key.write_bytes(b'k' * 32)
    key.chmod(0o600)
    identity = root / 'identity.db'
    store = IdentityStore(str(identity))
    with store.connect(write=True) as db:
        db.execute("INSERT INTO users(user_id,username,password_hash) VALUES('a','alice','synthetic')")
    db = sqlite3.connect(identity)
    db.execute('PRAGMA foreign_keys=ON')
    accounts = AccountService(db, CredentialStore(root / 'unused', connection=db, key_path=key))
    row = accounts.save_verified(Principal('a', False), 'tajiduo',
        {'center_uid':'synthetic','role_id':'1','access_token':'fake','device_id':'fake'})
    snapshots = SnapshotStore(str(root / 'snapshots.db'))
    snapshots._conn.close()
    db.close()
    config = tmp_path / 'cloud.toml'
    config.write_text('cloud_accounts_enabled=true\ncloud_db_path="' + identity.as_posix() +
        '"\ncloud_data_root="' + root.as_posix() + '"\ncloud_credentials_key_path="' + key.as_posix() +
        '"\ncloud_allowed_origins=["https://localhost:8443"]\n'
        'wuwa_enabled=false\nnte_enabled=false\nendfield_enabled=false\n'
        '[runtime]\nport=8020\n', encoding='utf-8')
    return root, identity, key, config


def test_backup_is_consistent_with_wal(tmp_path):
    root, identity, key, _ = fixture(tmp_path)
    writer = sqlite3.connect(identity)
    writer.execute('PRAGMA journal_mode=WAL')
    writer.execute("UPDATE users SET username='committed'")
    writer.commit()
    writer.execute("UPDATE users SET username='uncommitted'")
    result = backup(root, identity, tmp_path / 'backup', key)
    with sqlite3.connect(tmp_path / 'backup/identity.db') as db:
        assert db.execute('SELECT username FROM users').fetchone()[0] == 'committed'
    assert result['consistency'] == 'per_file_online'
    assert result['key_included'] is False
    writer.rollback()
    writer.close()


def test_restore_requires_matching_key(tmp_path):
    root, identity, key, _ = fixture(tmp_path)
    backup(root, identity, tmp_path / 'backup', key)
    wrong = tmp_path / 'wrong.key'
    wrong.write_bytes(b'x' * 32)
    wrong.chmod(0o600)
    with pytest.raises(OperationError, match='key_mismatch'):
        restore(tmp_path / 'backup', tmp_path / 'restore', wrong)
    assert not (tmp_path / 'restore').exists()
    result = restore(tmp_path / 'backup', tmp_path / 'restore', key)
    assert result['credential_readability'] == 'verified'
    assert identity.exists()


@pytest.mark.parametrize('version',[2,3,4])
def test_backup_restore_preserves_exact_identity_schema_version(tmp_path,version):
    from game_assistant.migrations.cloud_v2 import migrate_identity_schema
    from game_assistant.migrations.cloud_v3 import migrate_qq_schema
    from game_assistant.migrations.current import initialize_cloud_schema
    from game_assistant.snapshots import SnapshotStore
    initializers={2:migrate_identity_schema,3:migrate_qq_schema,4:initialize_cloud_schema}
    root=tmp_path/'live';root.mkdir()
    identity=root/'identity.db';key=tmp_path/'external.key'
    key.write_bytes(b'k'*32);key.chmod(0o600)
    with sqlite3.connect(identity) as db:initializers[version](db)
    snapshots=SnapshotStore(str(root/'snapshots.db'));snapshots._conn.close()
    manifest=backup(root,identity,tmp_path/'backup',key)
    assert manifest['identity_schema_version']==version
    restored=restore(tmp_path/'backup',tmp_path/'restored',key)
    assert restored['identity_schema_version']==version
    with sqlite3.connect(tmp_path/'restored/identity.db') as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==version


@pytest.mark.parametrize('destination', ['live', 'live/child', 'backup'])
def test_invalid_destination_rejected(tmp_path, destination):
    root, identity, key, _ = fixture(tmp_path)
    output = tmp_path / destination
    if destination == 'backup':
        output.mkdir()
    with pytest.raises(OperationError):
        backup(root, identity, output, key)


def test_restore_rejects_manifest_tampering_and_future_version(tmp_path):
    root, identity, key, _ = fixture(tmp_path)
    backup(root, identity, tmp_path / 'backup', key)
    manifest_path = tmp_path / 'backup/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['format_version'] = 99
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(OperationError, match='unsupported_backup_version'):
        restore(tmp_path / 'backup', tmp_path / 'restore', key)
    manifest['format_version'] = 1
    manifest['files'][0]['path'] = '../escape.db'
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(OperationError):
        restore(tmp_path / 'backup', tmp_path / 'restore', key)


def test_cloud_starts_one_scheduler(tmp_path):
    _, _, _, config = fixture(tmp_path)
    runtime = load_runtime(config)
    app = build_app(runtime)
    with TestClient(app, base_url='https://localhost:8443') as client:
        assert app.state.scheduler._running
        app.state.scheduler.start()
        health = client.get('/api/health')
        assert health.status_code == 200 and health.json()['status'] == 'ok'
        assert set(health.json()['version']) == {'commit', 'frontend_commit'}
        assert isinstance(health.json()['ready'], bool)
        assert client.get('/internal/operations/health').status_code == 401
        second = build_app(runtime)
        with pytest.raises(RuntimeError, match='scheduler'):
            with TestClient(second, base_url='https://localhost:8443'):
                pass
    assert not app.state.scheduler._running


def test_explicit_config_required_and_no_public_bind(tmp_path):
    with pytest.raises(ValueError):
        load_runtime(tmp_path / 'absent.toml')
    _, _, _, config = fixture(tmp_path)
    config.write_text(config.read_text().replace('port=8020', 'port=8020\nhost="0.0.0.0"'))
    with pytest.raises(ValueError, match='loopback_required'):
        load_runtime(config)


def test_static_ui_never_serves_api_or_symlink_data(tmp_path):
    from game_assistant.cloud_web_ui import install_cloud_ui
    _, _, _, config = fixture(tmp_path)
    app = build_app(load_runtime(config), start_scheduler=False)
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<html data-service-mode="cloud">cloud</html>')
    (dist / 'asset.js').write_text('safe')
    (dist / 'game-icons').mkdir()
    (dist / 'game-icons/sources.json').write_text('{}')
    install_cloud_ui(app, dist)
    with TestClient(app, base_url='https://localhost:8443') as client:
        assert client.get('/').status_code == 200
        assert client.get('/asset.js').text == 'safe'
        assert client.get('/game-icons/sources.json').json() == {}
        assert client.get('/private/identity.db').status_code == 404
        assert client.get('/api/unknown').status_code == 404
    (dist / 'index.html').write_text('<html>local</html>')
    with pytest.raises(ValueError, match='cloud build'):
        install_cloud_ui(app, dist)


def test_static_ui_lets_browsers_keep_only_hashed_build_files(tmp_path):
    from game_assistant.cloud_web_ui import install_cloud_ui
    _, _, _, config = fixture(tmp_path)
    app = build_app(load_runtime(config), start_scheduler=False)
    dist = tmp_path / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('<html data-service-mode="cloud">cloud</html>')
    (dist / 'assets/main-Ab12Cd34.js').write_text('safe')
    install_cloud_ui(app, dist)
    lookups = []
    authenticate = app.state.identity.authenticate
    app.state.identity.authenticate = lambda token: lookups.append(token) or authenticate(token)
    with TestClient(app, base_url='https://localhost:8443') as client:
        asset = client.get('/assets/main-Ab12Cd34.js')
        assert asset.headers['cache-control'] == 'public, max-age=31536000, immutable' and 'pragma' not in asset.headers
        assert lookups == []
        for path in ('/', '/index.html', '/api/health'):
            assert client.get(path).headers['cache-control'] == 'no-store'
        (dist / 'assets/main-Ab12Cd34.js').unlink()
        assert client.get('/assets/main-Ab12Cd34.js').headers['cache-control'] == 'no-store'


def test_backup_rejects_unknown_private_file(tmp_path):
    root, identity, key, _ = fixture(tmp_path)
    (root / 'private').mkdir()
    (root / 'private/arbitrary.json').write_text('{}')
    with pytest.raises(OperationError, match='unrecognized_data_file'):
        backup(root, identity, tmp_path / 'backup', key)


def test_backup_preserves_known_migration_metadata(tmp_path):
    root, identity, key, _ = fixture(tmp_path)
    (root/'migration-manifest.json').write_text('{"version":1}')
    (root/'report.json').write_text('{"activation_ready":false}')
    backup(root,identity,tmp_path/'backup',key)
    restore(tmp_path/'backup',tmp_path/'restore',key)
    assert (tmp_path/'restore/data/report.json').read_text() == '{"activation_ready":false}'


def test_wal_backup_is_self_contained_and_restore_preserves_source(tmp_path):
    from scripts.cloud.backup import digest
    root,identity,key,_ = fixture(tmp_path)
    writer = sqlite3.connect(identity)
    writer.execute('PRAGMA journal_mode=WAL')
    writer.execute("UPDATE users SET username='wal-user'")
    writer.commit()
    backup(root,identity,tmp_path/'backup',key)
    before = {path.relative_to(tmp_path/'backup').as_posix():digest(path)
              for path in (tmp_path/'backup').rglob('*') if path.is_file()}
    restore(tmp_path/'backup',tmp_path/'restore',key)
    after = {path.relative_to(tmp_path/'backup').as_posix():digest(path)
             for path in (tmp_path/'backup').rglob('*') if path.is_file()}
    assert before == after
    assert not any(name.endswith(('-wal','-shm')) for name in before)
    writer.close()


def test_static_ui_cannot_shadow_lifespan_account_routes(tmp_path):
    from game_assistant.cloud_web_ui import install_cloud_ui
    from tests.test_identity import write
    _,_,_,config = fixture(tmp_path)
    app = build_app(load_runtime(config),start_scheduler=False)
    dist = tmp_path/'dist'
    dist.mkdir()
    (dist/'index.html').write_text('<html data-service-mode="cloud">cloud</html>')
    install_cloud_ui(app,dist)
    # Fixture's existing synthetic hash is replaced with a real test-only hash.
    with app.state.identity.store.connect(write=True) as db:
        db.execute('UPDATE users SET password_hash=?',(app.state.identity.hasher.hash('Synthetic-password-123'),))
    with TestClient(app,base_url='https://localhost:8443') as client:
        assert write(client,'/api/identity/login',{'username':'alice','password':'Synthetic-password-123'}).status_code==200
        assert client.get('/api/accounts').status_code==200


def test_static_ui_font_manifest_allows_startup_without_public_route(tmp_path):
    from dataclasses import replace
    from game_assistant.cloud_web_ui import validate_dist
    _, _, _, config = fixture(tmp_path)
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<html data-service-mode="cloud">cloud</html>')
    font = b'wOF2-test-font'
    (dist / 'render-font.woff2').write_bytes(font)
    (dist / 'render-font.json').write_text('{"schema_version":1}')
    assert validate_dist(dist) == dist.resolve()
    app = build_app(replace(load_runtime(config), frontend_dist=dist), start_scheduler=False)
    assert '/render-font.json' not in {getattr(route, 'path', None) for route in app.routes}
    with TestClient(app, base_url='https://localhost:8443') as client:
        health = client.get('/api/health')
        assert health.status_code == 200 and health.json()['status'] == 'ok'
        assert set(health.json()['version']) == {'commit', 'frontend_commit'}
        assert isinstance(health.json()['ready'], bool)
        assert client.get('/').status_code == 200
        assert client.get('/render-font.woff2').content == font
        for method in (client.get, client.head):
            assert method('/render-font.json').status_code == 404
        assert client.get('/api/unknown').status_code == 404
        assert client.get('/private/render-font.json').status_code == 404


@pytest.mark.parametrize('relative', ['other.json', 'assets/render-font.json',
                                       'private/secret.json', 'render-font.JSON'])
def test_static_ui_font_manifest_exception_is_exact(tmp_path, relative):
    from game_assistant.cloud_web_ui import validate_dist
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<html data-service-mode="cloud">cloud</html>')
    path = dist / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{}')
    with pytest.raises(ValueError, match='Unexpected static artifact'):
        validate_dist(dist)


def test_restore_rejects_sidefile_escape_and_changed_payload(tmp_path):
    root,identity,key,_ = fixture(tmp_path)
    backup(root,identity,tmp_path/'backup',key)
    path=tmp_path/'backup/data/snapshots.db'
    with path.open('ab') as stream: stream.write(b'tampered')
    with pytest.raises(OperationError,match='backup_digest_mismatch'):
        restore(tmp_path/'backup',tmp_path/'restore',key)
    assert not (tmp_path/'restore').exists()


def test_restore_cannot_create_directory_inside_live_root(tmp_path):
    root,identity,key,_ = fixture(tmp_path)
    backup(root,identity,tmp_path/'backup',key)
    with pytest.raises(OperationError,match='overlapping_paths'):
        restore(tmp_path/'backup',root/'nested-restore',key,live_root=root)
    assert not (root/'nested-restore').exists()


@pytest.mark.parametrize('statement', ['PRAGMA user_version=999', 'DROP INDEX default_account_by_user_game'])
def test_backup_rejects_future_or_drifted_identity_schema(tmp_path,statement):
    root,identity,key,_ = fixture(tmp_path)
    with sqlite3.connect(identity) as db: db.execute(statement)
    with pytest.raises(OperationError,match='unsupported_identity_schema'):
        backup(root,identity,tmp_path/'backup',key)
    assert not (tmp_path/'backup').exists()


def test_configuration_check_rejects_plain_http_without_opening_db(tmp_path):
    _,identity,_,config=fixture(tmp_path)
    config.write_text(config.read_text().replace('https://localhost:8443','http://localhost:8443'))
    before=identity.read_bytes()
    with pytest.raises(ValueError,match='https_origins_required'):
        load_runtime(config)
    assert identity.read_bytes()==before


def test_backup_includes_private_manifest_and_public_side_databases(tmp_path):
    from game_assistant.accounts.models import AccountScope
    from game_assistant.nte_gacha import GachaStore
    from game_assistant.endfield_blueprints import BlueprintStore
    from game_assistant.private_data import list_scope_files
    root,identity,key,_=fixture(tmp_path)
    with sqlite3.connect(identity) as db:
        row=db.execute('SELECT user_id,account_id,role_id FROM roles').fetchone()
    scope=AccountScope(*row)
    for cls in (GachaStore,BlueprintStore):
        ledger=cls.for_scope(scope,root/'private',role_uid='1',server_id='official')
        ledger.close()
    with sqlite3.connect(root/'public.endfield-public.sqlite3') as db:
        db.execute('CREATE TABLE public_fixture(value TEXT)')
        db.execute("INSERT INTO public_fixture VALUES('synthetic')")
    result=backup(root,identity,tmp_path/'backup',key)
    assert sum(entry['path'].startswith('data/private/') for entry in result['files'])==2
    assert [item['scope'] for item in list_scope_files(tmp_path/'backup/data/private')]==[scope,scope]
    assert 'data/public.endfield-public.sqlite3' in [entry['path'] for entry in result['files']]
    restore(tmp_path/'backup',tmp_path/'restore',key)


def test_backup_rejects_symbolic_escape(tmp_path):
    root,identity,key,_=fixture(tmp_path)
    target=tmp_path/'outside.db'
    target.write_bytes(identity.read_bytes())
    try:
        (root/'public.db').symlink_to(target)
    except OSError:
        pytest.skip('Windows account cannot create synthetic symlink')
    with pytest.raises(OperationError,match='symlink_path_rejected'):
        backup(root,identity,tmp_path/'backup',key)

async def test_real_backup_restore_preserves_passport_grant_and_parent_revocation(tmp_path,monkeypatch):
    from game_assistant.accounts.service import AccountService
    from game_assistant.auth.service import ScopedLoginService
    from game_assistant.auth.store import CredentialStore, CredentialStoreError
    from game_assistant.adapters.endfield import hypergryph, skland_client
    from game_assistant.identity.models import Principal
    from scripts.cloud.backup import credential_check
    from tests.test_cloud_skland_passport import Client, Passport

    root,identity,key,_ = fixture(tmp_path)
    Client.roles = [('role','1')]
    Client.expired = Client.fail = False
    Client.entered = Client.release = None
    Client.calls = 0
    monkeypatch.setattr(hypergryph,'HypergryphClient',Passport)
    monkeypatch.setattr(skland_client,'SklandClient',Client)
    owner = Principal('a',False)
    with sqlite3.connect(identity) as db:
        credentials = CredentialStore(root/'unused',connection=db,key_path=key)
        accounts = AccountService(db,credentials)
        login = ScopedLoginService(accounts,providers={})
        parent = accounts.save_verified(owner,'hypergryph',{
            'uid':'hg-user','role_id':'role','server_id':'1','hg_token':'passport-secret'})
        derived = await login.connect_skland_passport(owner,parent['account_id'],parent['role_id'])
        before = credentials.load_grant('a',derived['grant_id'])
        manifest = backup(root,identity,tmp_path/'backup',key)
        assert manifest['credential_readability'] == 'verified'
        assert manifest['key_included'] is False
        assert 'secret' not in json.dumps(manifest)
        result = restore(tmp_path/'backup',tmp_path/'restored',key,live_root=root)
        assert result['credential_readability'] == 'verified'
        with sqlite3.connect(tmp_path/'restored/identity.db') as restored:
            restored_credentials = CredentialStore('unused',connection=restored,key_path=key)
            restored_accounts = AccountService(restored,restored_credentials)
            assert restored_credentials.load_grant('a',derived['grant_id']) == before
            scope = restored_accounts.require_scope(owner,derived['account_id'],derived['role_id'])
            assert restored_accounts.describe(scope)['provider'] == 'skland'
            assert credential_check(tmp_path/'restored/identity.db',key) == 'verified'
            restored_accounts.revoke(owner,parent['account_id'])
            with pytest.raises(CredentialStoreError):
                restored_credentials.load_grant('a',derived['grant_id'])
            with pytest.raises(LookupError):
                restored_accounts.describe(scope)
            assert restored.execute('SELECT state FROM grants WHERE grant_id=?',
                (derived['grant_id'],)).fetchone() == ('revoked',)
        # Revoking the restored copy must not alter the original or backup source.
        assert credentials.load_grant('a',derived['grant_id']) == before
        assert credential_check(tmp_path/'backup/identity.db',key) == 'verified'
