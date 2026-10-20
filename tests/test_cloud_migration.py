"""Offline migration checks use synthetic databases only."""
import hashlib
import json
import sqlite3
import threading
from pathlib import Path

import pytest

from game_assistant.migrations import cli
from game_assistant.migrations.cloud_v2 import migrate_identity_schema
from game_assistant.accounts.models import AccountScope
from game_assistant.private_data import list_scope_files
from game_assistant.wuwa_history import WuwaHistory
from game_assistant.wuwa_gacha import GachaStore as WuwaGacha
from game_assistant.nte_gacha import GachaStore as NteGacha
from game_assistant.endfield_gacha import EndfieldGachaStore
from game_assistant.endfield_blueprints import BlueprintStore
from game_assistant.snapshots import SnapshotStore


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def case(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    identity = tmp_path / 'provisioned.db'
    with sqlite3.connect(identity) as db:
        migrate_identity_schema(db)
        db.execute("INSERT INTO users(user_id,username,password_hash) VALUES('u','synthetic','synthetic-hash')")
        for account, game, provider in [('w','wuthering_waves','kuro'),('n','nte','tajiduo'),('e','endfield','hypergryph')]:
            db.execute("INSERT INTO grants(grant_id,user_id,provider,state,encrypted_payload) VALUES(?,'u',?,'ok',?)", (account,provider,b'SYNTHETIC-CIPHERTEXT'))
            db.execute("INSERT INTO accounts(account_id,user_id,grant_id,game,channel,server,provider,account_uid) VALUES(?,'u',?,?, 'official','s',?,'uid')", (account,account,game,provider))
            db.execute("INSERT INTO roles(role_id,account_id,user_id,game,channel,server,provider,game_uid) VALUES(?,?,'u',?,'official','s',?,'uid')", (account,account,game,provider))
        db.execute("INSERT INTO sessions(session_id,user_id,token_hash,csrf_token_hash,expires_at) VALUES('session','u','t','c','2099-01-01')")
        db.execute("INSERT INTO invites(invite_id,token_hash,created_by,expires_at) VALUES('invite','i','u','2099-01-01')")
        db.execute("INSERT INTO preauth_sessions VALUES('p','c','2099-01-01')")
        db.execute("INSERT INTO recoveries VALUES('r','r','u','u','2026-01-01','2099-01-01',NULL,NULL)")
    with sqlite3.connect(source / 'legacy.db') as db:
        WuwaHistory(db, threading.Lock())
        db.execute("INSERT INTO wuwa_history VALUES(1,'uid','s','tower','','season','hash',?,NULL,NULL,'2026-01-01','2026-01-01')", ('{"missing":null,"complete":false}',))
    mapping = {'version': 1, 'identity_database': str(identity), 'datasets': [
        {'database':'legacy.db','kind':'wuwa_history','user_id':'u','account_id':'w','role_id':'w'}]}
    return source, identity, mapping, tmp_path / 'new'


def test_source_unchanged_after_migration(case):
    source, identity, mapping, destination = case
    before, before_identity = hashes(source), identity.read_bytes()
    report = cli.preview(source, mapping)
    assert report['ready'] and report['migrated'] == 1
    assert not destination.exists()
    cli.apply(source, mapping, destination)
    assert hashes(source) == before
    assert identity.read_bytes() == before_identity
    item, = list_scope_files(destination / 'private')
    assert item['scope'] == AccountScope('u','w','w')
    with sqlite3.connect(item['path']) as db:
        assert db.execute('SELECT payload FROM wuwa_history').fetchone()[0] == '{"missing":null,"complete":false}'


def test_unknown_owner_requires_mapping(case):
    source, _, mapping, destination = case
    mapping['datasets'] = []
    report = cli.preview(source, mapping)
    assert not report['ready'] and report['unassigned'] == 1
    with pytest.raises(cli.MigrationError):
        cli.apply(source, mapping, destination)
    assert not destination.exists()


def test_duplicate_import_is_idempotent(case):
    source, _, mapping, destination = case
    first = cli.apply(source, mapping, destination)
    before = hashes(destination)
    second = cli.apply(source, mapping, destination)
    assert second['already_applied'] and hashes(destination) == before
    assert first['checks']['reconciled']


def test_interrupted_migration_not_promoted(case, monkeypatch):
    source, _, mapping, destination = case
    def interrupted(*args):
        raise RuntimeError('synthetic interruption')
    monkeypatch.setattr(cli, '_promote', interrupted)
    with pytest.raises(RuntimeError, match='synthetic interruption'):
        cli.apply(source, mapping, destination)
    assert not destination.exists()
    assert list(destination.parent.glob('.new.migration-*'))
    monkeypatch.undo()
    assert cli.apply(source, mapping, destination)['checks']['reconciled']


def test_dpapi_not_copied_as_linux_grant(case):
    source, _, mapping, destination = case
    (source / 'assistant.credentials.json').write_text('{"dpapi":"SYNTHETIC-DPAPI"}')
    report = cli.apply(source, mapping, destination)
    assert report['reauthorization_required'] == 3
    assert 'SYNTHETIC-DPAPI' not in json.dumps(report)
    with sqlite3.connect(destination / 'cloud.db') as db:
        assert db.execute('SELECT state,version,encrypted_payload FROM grants').fetchall() == [('pending',2,None)] * 3
        for table in ('sessions','invites','preauth_sessions','recoveries'):
            assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
        assert db.execute('SELECT password_hash FROM users').fetchone()[0] == 'synthetic-hash'
    assert not list(destination.rglob('*.credentials.json'))


def test_unknown_private_table_not_silently_skipped(case):
    source, _, mapping, destination = case
    with sqlite3.connect(source / 'legacy.db') as db:
        db.execute('CREATE TABLE mystery_private(value TEXT)')
        db.execute("INSERT INTO mystery_private VALUES('SENSITIVE-SYNTHETIC')")
    report = cli.preview(source, mapping)
    assert not report['ready']
    assert any(t['table'] == 'mystery_private' and t['count'] == 1 for t in report['tables'])
    assert 'SENSITIVE-SYNTHETIC' not in json.dumps(report)
    mapping['exclude_tables'] = [{'database':'legacy.db','table':'mystery_private','reason':'public cache'}]
    with pytest.raises(cli.MigrationError):
        cli.apply(source, mapping, destination)


@pytest.mark.parametrize('field,value', [('user_id','other'),('account_id','n'),('role_id','n')])
def test_mapping_must_match_provisioned_scope(case, field, value):
    source, _, mapping, destination = case
    mapping['datasets'][0][field] = value
    assert not cli.preview(source, mapping)['ready']
    with pytest.raises(cli.MigrationError):
        cli.apply(source, mapping, destination)


def test_unmapped_foreign_role_blocks_apply(case):
    source, _, mapping, destination = case
    with sqlite3.connect(source / 'legacy.db') as db:
        db.execute("INSERT INTO wuwa_history VALUES(2,'foreign','s','tower','','season','h','{}',NULL,NULL,'date','date')")
    assert cli.preview(source, mapping)['unassigned'] == 1
    with pytest.raises(cli.MigrationError):
        cli.apply(source, mapping, destination)


@pytest.mark.parametrize('relative', ['.', 'nested', '..'])
def test_destination_overlap_rejected(case, relative):
    source, _, mapping, _ = case
    before = hashes(source)
    with pytest.raises(cli.MigrationError):
        cli.apply(source, mapping, source / relative)
    assert hashes(source) == before


def test_existing_destination_not_overwritten(case):
    source, _, mapping, destination = case
    destination.mkdir()
    (destination / 'important').write_text('keep')
    with pytest.raises(cli.MigrationError):
        cli.apply(source, mapping, destination)
    assert (destination / 'important').read_text() == 'keep'


def test_idempotence_verifies_destination_and_source(case):
    source, _, mapping, destination = case
    cli.apply(source, mapping, destination)
    item, = list_scope_files(destination / 'private')
    with sqlite3.connect(item['path']) as db:
        db.execute("UPDATE wuwa_history SET payload='{}'")
    with pytest.raises(cli.MigrationError):
        cli.apply(source, mapping, destination)


def test_conflicting_duplicates_rejected(case):
    source, _, mapping, destination = case
    with sqlite3.connect(source / 'legacy.db') as original, sqlite3.connect(source / 'copy.db') as copy:
        original.backup(copy)
        copy.execute("UPDATE wuwa_history SET payload='{}'")
    mapping['datasets'].append(dict(mapping['datasets'][0], database='copy.db'))
    report = cli.preview(source, mapping)
    assert not report['ready'] and report['conflicts'] == 1
    with pytest.raises(cli.MigrationError):
        cli.apply(source, mapping, destination)


def test_equal_duplicate_rows_counted(case):
    source, _, mapping, destination = case
    with sqlite3.connect(source / 'legacy.db') as original, sqlite3.connect(source / 'copy.db') as copy:
        original.backup(copy)
    mapping['datasets'].append(dict(mapping['datasets'][0], database='copy.db'))
    report = cli.apply(source, mapping, destination)
    assert report['duplicates'] == 1 and report['migrated'] == 1
    assert report['checks']['reconciled']


def test_live_wal_backup_required_without_side_effect(case):
    source, _, mapping, destination = case
    (source / 'legacy.db-wal').write_bytes(b'synthetic-wal')
    before = hashes(source)
    assert not cli.preview(source, mapping)['ready']
    with pytest.raises(cli.MigrationError):
        cli.apply(source, mapping, destination)
    assert hashes(source) == before


def test_public_cache_explicit_exclusion(case):
    source, _, mapping, destination = case
    with sqlite3.connect(source / 'public.db') as db:
        db.execute('CREATE TABLE cache(key TEXT PRIMARY KEY,value TEXT,fetched_at TEXT)')
        db.execute("INSERT INTO cache VALUES('k','{}','2026-01-01')")
    assert not cli.preview(source, mapping)['ready']
    mapping['exclude_tables'] = [{'database':'public.db','table':'cache','reason':'public Endfield feed reacquired centrally'}]
    report = cli.apply(source, mapping, destination)
    assert report['excluded'] == 1


@pytest.mark.parametrize('kind,account', [('nte','n'),('wuwa_gacha','w'),('endfield_gacha','e'),('blueprints','e')])
def test_exact_scoped_legacy_layout(case, kind, account):
    source, _, mapping, destination = case
    path = source / f'{kind}.sqlite3'
    if kind == 'nte':
        NteGacha(path)
        table, values = 'records', ('uid','pool','id','{"complete":false}')
    elif kind == 'endfield_gacha':
        EndfieldGachaStore(path)
        table, values = 'records', ('uid','pool',42,'{"null":null}')
    elif kind == 'wuwa_gacha':
        with sqlite3.connect(path) as db:
            WuwaGacha(db, threading.Lock())
        table, values = 'wuwa_gacha', ('uid','s','pool','id','{}','date','5')
    else:
        store = BlueprintStore(source / 'blueprint.db')
        path = store.path
        table, values = 'blueprints', ('id','name','code','notes','date','date')
    with sqlite3.connect(path) as db:
        db.execute(f'INSERT INTO {table} VALUES ({",".join("?" for _ in values)})', values)
    mapping['datasets'].append({'database':path.name,'kind':kind,'user_id':'u','account_id':account,'role_id':account})
    report = cli.apply(source, mapping, destination)
    item = next(i for i in list_scope_files(destination / 'private') if i['kind'] == kind)
    with sqlite3.connect(item['path']) as db:
        assert db.execute(f'SELECT * FROM {table}').fetchall() == [values]
    assert report['checks']['reconciled']


def test_current_wuwa_archive_tables_preserve_scoped_source_coverage_and_rules(case):
    source,identity,mapping,destination=case
    path=source/'current-wuwa.sqlite3'
    connection=sqlite3.connect(path)
    store=WuwaGacha(connection,threading.Lock())
    store.import_records({'info':{'uid':'uid','server_id':'s'},'list':[
        dict(id='real',pool='1',resource_id='r',rarity=5,time='2026-01-01T12:00:00',history_gap_before=True)]},'uid','s')
    p=store.preview({'data':{'uid':'uid','card_analysis_json':{'pool':{'five_cards':[
        dict(cardPoolType=99,name='未知五星',time='2025-12-01',draw_total=120)]}}}},'uid','s',source='mcgf')
    store.commit_preview(p['preview_id'],'uid','s')
    store.set_rule('uid','s',dict(pool='1',hard_pity=70,reset_rarity='5',version='synthetic-user',sharing='independent',basis='user_configured'))
    tables=('wuwa_gacha','wuwa_gacha_imports','wuwa_gacha_batches','wuwa_gacha_aggregates','wuwa_gacha_rules')
    expected={name:connection.execute('SELECT * FROM '+name).fetchall() for name in tables}
    connection.close()
    mapping['datasets'].append(dict(database=path.name,kind='wuwa_gacha',user_id='u',account_id='w',role_id='w'))
    before,before_identity=hashes(source),identity.read_bytes()
    report=cli.apply(source,mapping,destination)
    item=next(i for i in list_scope_files(destination/'private') if i['kind']=='wuwa_gacha')
    with sqlite3.connect(item['path']) as db:
        for name in tables:
            assert db.execute('SELECT * FROM '+name).fetchall()==expected[name]
    assert report['checks']['reconciled'] and hashes(source)==before and identity.read_bytes()==before_identity
    restored=WuwaGacha.for_scope(AccountScope('u','w','w'),destination/'private',role_uid='uid',server_id='s')
    try:
        data=restored.read(AccountScope('u','w','w'))
        assert data['total']==1 and data['aggregates']['total']==1
        assert data['aggregates']['items'][0]['period_count']==120
        assert data['coverage']['segments'][0]['warnings']==['SOURCE_GAP']
        assert data['rules'][0]['basis']=='user_configured'
    finally:restored.close()
    assert cli.apply(source,mapping,destination)['already_applied']


@pytest.mark.parametrize('table',['wuwa_gacha_batches','wuwa_gacha_aggregates','wuwa_gacha_rules'])
def test_new_wuwa_table_foreign_owner_and_schema_drift_still_block(case,table):
    source,_,mapping,destination=case
    path=source/'current-wuwa.sqlite3'
    connection=sqlite3.connect(path)
    WuwaGacha(connection,threading.Lock())
    connection.execute('INSERT INTO '+table+' VALUES(?,?,?,?)',('foreign','s','k','{}'));connection.commit()
    mapping['datasets'].append(dict(database=path.name,kind='wuwa_gacha',user_id='u',account_id='w',role_id='w'))
    report=cli.preview(source,mapping)
    assert not report['ready'] and report['unassigned']==1
    assert any(i['code']=='unmapped_owner' for i in report['issues'])
    connection.execute('DELETE FROM '+table)
    connection.execute('ALTER TABLE '+table+' ADD COLUMN unsupported TEXT');connection.commit();connection.close()
    report=cli.preview(source,mapping)
    assert not report['ready'] and any(i['code']=='legacy_schema_mismatch' for i in report['issues'])
    with pytest.raises(cli.MigrationError):cli.apply(source,mapping,destination)
    assert not destination.exists()


def test_pre_archive_wuwa_two_table_layout_remains_migratable(case):
    source,_,mapping,destination=case
    path=source/'old-wuwa.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE wuwa_gacha (account TEXT,server TEXT,pool TEXT,draw_id TEXT,payload TEXT,time TEXT,rarity TEXT,PRIMARY KEY(account,server,pool,draw_id))')
        db.execute('CREATE TABLE wuwa_gacha_imports (account TEXT,server TEXT,imported_at TEXT,source TEXT,failed_pools TEXT,PRIMARY KEY(account,server))')
        db.execute('INSERT INTO wuwa_gacha_imports VALUES(?,?,?,?,?)',('uid','s','2026-01-01','json_import','["2"]'))
    mapping['datasets'].append(dict(database=path.name,kind='wuwa_gacha',user_id='u',account_id='w',role_id='w'))
    assert cli.apply(source,mapping,destination)['checks']['reconciled']
    item=next(i for i in list_scope_files(destination/'private') if i['kind']=='wuwa_gacha')
    with sqlite3.connect(item['path']) as db:
        assert db.execute('SELECT source,failed_pools FROM wuwa_gacha_imports').fetchone()==('json_import','["2"]')
        assert db.execute('SELECT COUNT(*) FROM wuwa_gacha_aggregates').fetchone()==(0,)


@pytest.mark.parametrize('current,last_sync,scan_pending,expected', [
    (False, None, None, None), (False, '2026-10-15T00:00:00Z', None, 0),
    (True, None, None, None), (True, '2026-10-15T00:00:00Z', 1, 1),
    (True, '2026-10-15T00:00:00Z', 0, 0), ('errors', '2026-10-15T00:00:00Z', 1, 1),
])
def test_endfield_pool_scan_schema_migrates_without_losing_coverage_evidence(case, current, last_sync, scan_pending, expected):
    source, _, mapping, destination = case
    path = source / 'endfield.sqlite3'
    with sqlite3.connect(path) as db:
        # 'errors' is the layout that also keeps the last per-pool sync failure.
        extra = ',scan_pending INTEGER,last_error TEXT' if current == 'errors' else ',scan_pending INTEGER' if current else ''
        db.execute('CREATE TABLE pools(role TEXT NOT NULL,pool_key TEXT NOT NULL,kind TEXT NOT NULL,'
                   f'label TEXT NOT NULL,last_sync_at TEXT{extra},PRIMARY KEY(role,pool_key))')
        values = ('uid', 'pool', 'character', 'synthetic', last_sync) + ((scan_pending,) if current else ()) + (('接口错误',) if current == 'errors' else ())
        db.execute('INSERT INTO pools VALUES (' + ','.join('?' for _ in values) + ')', values)
    mapping['datasets'].append({'database':path.name,'kind':'endfield_gacha','user_id':'u','account_id':'e','role_id':'e'})
    before = hashes(source)
    plan = cli.build_plan(source, mapping)
    assert plan['report']['ready']
    # Validate the real staging and reconciliation path without the separate,
    # platform-specific atomic publication step (unsupported on macOS).
    destination.mkdir()
    cli._write_stage(destination, plan)
    ledger = next(item for item in list_scope_files(destination / 'private') if item['kind'] == 'endfield_gacha')
    with sqlite3.connect(ledger['path']) as db:
        assert db.execute('SELECT last_sync_at,scan_pending FROM pools').fetchone() == (last_sync, expected)
    assert hashes(source) == before


def test_endfield_pool_scan_schema_still_rejects_unrecognized_columns(case):
    source, _, mapping, _ = case
    path = source / 'endfield.sqlite3'
    EndfieldGachaStore(path)
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE pools ADD COLUMN unexpected TEXT')
    mapping['datasets'].append({'database':path.name,'kind':'endfield_gacha','user_id':'u','account_id':'e','role_id':'e'})
    report = cli.preview(source, mapping)
    assert not report['ready']
    assert any(item['code'] == 'legacy_schema_mismatch' for item in report['issues'])


def test_snapshots_preserve_dates_null_failure_and_provider(case):
    source, _, mapping, destination = case
    store = SnapshotStore(str(source / 'snapshots.db'))
    store._conn.execute("INSERT INTO snapshots VALUES('wuthering_waves','combat',?,'2026-01-02T00:00:00+00:00')", ('{"value":null,"complete":false}',))
    store._conn.execute("INSERT INTO poll_status VALUES('wuthering_waves','combat','error','2026-01-03','2026-01-02',2,NULL,'error')")
    store._conn.commit()
    store._conn.close()
    mapping['datasets'].append({'database':'snapshots.db','kind':'snapshots','user_id':'u','account_id':'w','role_id':'w'})
    report = cli.apply(source, mapping, destination)
    with sqlite3.connect(destination / 'snapshots.db') as db:
        row = db.execute('SELECT payload,fetched_at,grant_version FROM scoped_snapshots').fetchone()
        assert row == ('{"value":null,"complete":false}','2026-01-02T00:00:00+00:00',2)
        assert json.loads(db.execute('SELECT status FROM scoped_poll_status').fetchone()[0])['state'] == 'error'
    assert report['checks']['reconciled']


def test_cli_default_preview_and_report_no_record_details(case, tmp_path):
    source, _, mapping, _ = case
    mapping_file = tmp_path / 'mapping.json'
    mapping_file.write_text(json.dumps(mapping))
    report = tmp_path / 'report.json'
    before = hashes(source)
    assert cli.main(['--source',str(source),'--mapping',str(mapping_file),'--output',str(report)]) == 0
    assert json.loads(report.read_text())['ready']
    assert '"missing"' not in report.read_text()
    assert hashes(source) == before


def test_preview_output_cannot_overwrite_source(case):
    source, _, mapping, _ = case
    before = hashes(source)
    with pytest.raises(cli.MigrationError):
        cli.write_report(cli.preview(source,mapping), source / 'legacy.db', source=source,
                         protected_files=[Path(mapping['identity_database'])])
    assert hashes(source) == before


def test_schema_drift_rejected_even_with_version_two(case):
    source, identity, mapping, _ = case
    with sqlite3.connect(identity) as db:
        db.execute('ALTER TABLE grants ADD COLUMN unsupported TEXT')
    with pytest.raises(cli.MigrationError,match='schema'):
        cli.preview(source,mapping)


def test_changed_source_does_not_overwrite_completed_destination(case):
    source, _, mapping, destination = case
    cli.apply(source,mapping,destination)
    before = hashes(destination)
    with sqlite3.connect(source/'legacy.db') as db:
        db.execute("UPDATE wuwa_history SET payload='{}'")
    with pytest.raises(cli.MigrationError):
        cli.apply(source,mapping,destination)
    assert hashes(destination) == before


def test_source_changes_during_apply_never_promoted(case,monkeypatch):
    source, _, mapping, destination = case
    original = cli._write_stage
    def changed(stage,plan):
        original(stage,plan)
        with sqlite3.connect(source/'legacy.db') as db:
            db.execute("UPDATE wuwa_history SET payload='{}'")
    monkeypatch.setattr(cli,'_write_stage',changed)
    with pytest.raises(cli.MigrationError,match='source_changed'):
        cli.apply(source,mapping,destination)
    assert not destination.exists()


def test_malformed_legacy_json_is_reported_without_payload(case):
    source, _, mapping, destination = case
    with sqlite3.connect(source/'legacy.db') as db:
        db.execute("UPDATE wuwa_history SET payload='SENSITIVE-BAD-JSON'")
    report = cli.preview(source,mapping)
    assert not report['ready']
    assert 'SENSITIVE-BAD-JSON' not in json.dumps(report)
    with pytest.raises(cli.MigrationError):
        cli.apply(source,mapping,destination)


def test_extra_manifest_named_file_breaks_idempotence(case):
    source, _, mapping, destination = case
    cli.apply(source,mapping,destination)
    (destination/'extra').mkdir()
    (destination/'extra'/'migration-manifest.json').write_text('untracked')
    with pytest.raises(cli.MigrationError):
        cli.apply(source,mapping,destination)


def test_stale_lock_requires_operator_review(case):
    source, _, mapping, destination = case
    lock = destination.parent/'.new.migration.lock'
    lock.write_text('synthetic interrupted process')
    with pytest.raises(cli.MigrationError,match='locked'):
        cli.apply(source,mapping,destination)
    assert not destination.exists() and lock.exists()


def test_dataset_path_escape_never_read(case):
    source, _, mapping, destination = case
    mapping['datasets'][0]['database'] = '../provisioned.db'
    report = cli.preview(source,mapping)
    assert not report['ready']
    assert len(report['databases']) == 1


def test_duplicate_mapping_owner_is_ambiguous(case):
    source, _, mapping, destination = case
    mapping['datasets'].append(dict(mapping['datasets'][0]))
    report = cli.preview(source,mapping)
    assert not report['ready'] and report['unassigned'] == 1


def test_manifest_is_compatible_with_live_scoped_facade(case):
    source, _, mapping, destination = case
    cli.apply(source,mapping,destination)
    store = WuwaHistory.for_scope(AccountScope('u','w','w'),destination/'private',role_uid='uid',server_id='s')
    try:
        assert store.read(AccountScope('u','w','w'),'tower')
    finally:
        store.close()


def test_target_grants_contain_no_old_ciphertext_pages(case):
    source, _, mapping, destination = case
    cli.apply(source,mapping,destination)
    assert b'SYNTHETIC-CIPHERTEXT' not in (destination/'cloud.db').read_bytes()


def test_source_symlink_rejected(case,tmp_path):
    source, _, mapping, destination = case
    try:
        (source/'external.db').symlink_to(tmp_path/'provisioned.db')
    except OSError:
        pytest.skip('OS denied synthetic symlink creation')
    report = cli.preview(source,mapping)
    assert not report['ready']
    with pytest.raises(cli.MigrationError):
        cli.apply(source,mapping,destination)


def test_future_identity_ledger_rejected(case):
    source, identity, mapping, _ = case
    with sqlite3.connect(identity) as db:
        db.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(9,'synthetic')")
    with pytest.raises(cli.MigrationError,match='schema'):
        cli.preview(source,mapping)


def test_corrupt_sqlite_file_is_registered_in_database_inventory(case):
    source, _, mapping, _ = case
    (source/'corrupt.db').write_bytes(b'invalid SQLite synthetic backup')
    report = cli.preview(source,mapping)
    assert not report['ready']
    assert any(item['database']=='corrupt.db' for item in report['databases'])


def test_promotion_race_does_not_replace_existing_directory(case,monkeypatch):
    source, _, mapping, destination = case
    original = cli._rename_noreplace
    def competing_writer(stage,target):
        target.mkdir()
        original(stage,target)
    monkeypatch.setattr(cli,'_rename_noreplace',competing_writer)
    with pytest.raises((OSError,cli.MigrationError)):
        cli.apply(source,mapping,destination)
    assert destination.is_dir() and not (destination/'cloud.db').exists()


def populate_v3(identity):
    from game_assistant.migrations.cloud_v3 import migrate_qq_schema
    with sqlite3.connect(identity) as db:
        migrate_qq_schema(db)
        for index, status in [(1,'confirmed'),(2,'pending')]:
            db.execute("INSERT INTO qq_link_codes VALUES(?,'u',?,'2026-01-01','2099-01-01',NULL,NULL)",
                       (f'code-{index}',f'synthetic-code-hash-{index}'))
            db.execute("INSERT INTO qq_link_attempts VALUES(?,?,'u','synthetic-app','group','synthetic-group',?,?, '2026-01-01','2099-01-01',?)",
                       (f'attempt-{index}',f'code-{index}',f'synthetic-sender-{index}',f'synthetic-challenge-{index}',status))
        db.execute("INSERT INTO qq_links VALUES('link','u','attempt-1','synthetic-app','group','synthetic-group','synthetic-sender-1','2026-01-01',NULL)")
        db.execute("INSERT INTO qq_rate_limits VALUES('synthetic-bucket',1,2)")


@pytest.mark.parametrize('version',[3,4])
def test_identity_migration_clears_qq_binding_capabilities(case,version):
    source, identity, mapping, destination = case
    populate_v3(identity)
    if version==4:
        from game_assistant.migrations.current import initialize_cloud_schema
        with sqlite3.connect(identity) as db:
            initialize_cloud_schema(db)
            db.execute("INSERT INTO qq_link_redemptions VALUES('message-hash','code-hash','link','2026-01-01')")
    before_source, before_identity = hashes(source), identity.read_bytes()
    preview = cli.preview(source,mapping)
    assert preview['ready'] and preview['identity_schema_version'] == version
    assert not destination.exists() and identity.read_bytes() == before_identity
    report = cli.apply(source,mapping,destination)
    assert report['qq_rebinding_required'] and report['qq_bindings_removed'] == 1
    with sqlite3.connect(destination/'cloud.db') as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == version
        if version==4:assert db.execute('SELECT COUNT(*) FROM qq_link_redemptions').fetchone()[0]==0
        for table in ('qq_links','qq_link_attempts','qq_link_codes','qq_rate_limits',
                      'sessions','invites','preauth_sessions','recoveries'):
            assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
        assert db.execute('SELECT state,version,encrypted_payload FROM grants').fetchall() == [('pending',2,None)] * 3
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    assert hashes(source) == before_source and identity.read_bytes() == before_identity
    assert b'synthetic-sender' not in (destination/'cloud.db').read_bytes()
    assert b'synthetic-code-hash' not in (destination/'cloud.db').read_bytes()
    assert cli.apply(source,mapping,destination)['already_applied']


def test_v3_unknown_private_identity_table_is_rejected(case):
    source, identity, mapping, _ = case
    populate_v3(identity)
    with sqlite3.connect(identity) as db:
        db.execute('CREATE TABLE qq_unknown_secret(payload TEXT)')
    with pytest.raises(cli.MigrationError,match='schema'):
        cli.preview(source,mapping)


def test_v3_identity_schema_drift_not_accepted(case):
    source, identity, mapping, _ = case
    populate_v3(identity)
    with sqlite3.connect(identity) as db:
        db.execute('DROP INDEX qq_active_identity')
    with pytest.raises(cli.MigrationError,match='schema'):
        cli.preview(source,mapping)


def test_v3_future_version_stays_fail_closed(case):
    source, identity, mapping, _ = case
    populate_v3(identity)
    with sqlite3.connect(identity) as db:
        db.execute('PRAGMA user_version=4')
    with pytest.raises(cli.MigrationError,match='schema'):
        cli.preview(source,mapping)
