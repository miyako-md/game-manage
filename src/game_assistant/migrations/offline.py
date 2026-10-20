"""Auditable offline dataset planning; never imports a credential or guesses owner.

Inputs must be quiescent SQLite backups, not live database directories. Opening
immutable/read-only prevents even WAL/SHM creation. Each input is then snapshotted
with SQLite backup. Reports contain counts/digests, never record values.
"""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from game_assistant.accounts.models import AccountScope
from game_assistant.accounts.store import AccountStore
from game_assistant.identity.models import Principal
from game_assistant.private_data import validate_scope


class MigrationError(ValueError):
    def __init__(self, code, report=None):
        self.code, self.report = code, report
        super().__init__(code)


TABLES = {
    'wuwa_history': {'wuwa_history': (('id','account','server','kind','subject','season','content_hash','payload','source','source_at','observed_at','archived_at'), ('id',))},
    'wuwa_gacha': {
        'wuwa_gacha': (('account','server','pool','draw_id','payload','time','rarity'), ('account','server','pool','draw_id')),
        'wuwa_gacha_imports': (('account','server','imported_at','source','failed_pools'), ('account','server')),
        # Archive additions retain the same explicit account/server ownership;
        # exact columns and primary keys still reject unknown schema changes.
        'wuwa_gacha_batches': (('account','server','key','payload'), ('account','server','key')),
        'wuwa_gacha_aggregates': (('account','server','key','payload'), ('account','server','key')),
        'wuwa_gacha_rules': (('account','server','key','payload'), ('account','server','key'))},
    'nte': {
        'records': (('role','pool','uid','payload'), ('role','pool','uid')),
        'batches': (('role','digest','payload'), ('role','digest')),
        'rules': (('role','pool','payload'), ('role','pool')),
        'accounts': (('role','metadata'), ('role',))},
    'endfield_gacha': {
        'records': (('role','pool_key','seq_id','payload'), ('role','pool_key','seq_id')),
        'pools': (('role','pool_key','kind','label','last_sync_at'), ('role','pool_key')),
        'breaks': (('role','pool_key','seq_id','permanent'), ('role','pool_key','seq_id'))},
    'blueprints': {'blueprints': (('id','name','code','notes','created_at','updated_at'), ('id',))},
    'snapshots': {
        'snapshots': (('game_id','capability','payload','fetched_at'), ('game_id','capability')),
        'poll_status': (('game_id','capability','state','last_attempt_at','last_success_at','consecutive_failures','error','error_kind'), ('game_id','capability'))},
}
SOURCES = {'wuwa_history': ('wuthering_waves','kuro'), 'wuwa_gacha': ('wuthering_waves','kuro'),
           'nte': ('nte','tajiduo'), 'endfield_gacha': ('endfield','hypergryph'),
           'blueprints': ('endfield',None)}
# Known public caches / features intentionally out of the initial cloud scope.
# Arbitrary unknown tables cannot be made "public" by an exclusion declaration.
EXCLUDABLE = {'cache','guide_posts','guide_active','guide_checks','bili_posts','bili_state',
              'notified','lol_accounts','lol_matches'}
PUBLIC_CAPS = {'announcement','events','news','teams','esports'}
IDENTITY_TABLES = {'schema_migrations','users','accounts','roles','grants','sessions','invites',
                   'preauth_sessions','recoveries','identity_rate_limits'}
INVALIDATE_IDENTITY_TABLES = ('sessions','invites','preauth_sessions','recoveries','identity_rate_limits')
QQ_TABLES = {'qq_link_codes','qq_link_attempts','qq_links','qq_rate_limits'}
# Delete in FK dependency order; confirmed links are capabilities too and the
# new instance must acquire an explicit fresh binding, never inherit one.
INVALIDATE_QQ_TABLES = ('qq_links','qq_link_attempts','qq_link_codes','qq_rate_limits')
KNOWN_IDENTITY_SCHEMAS = {2: IDENTITY_TABLES, 3: IDENTITY_TABLES | QQ_TABLES,
                          4: IDENTITY_TABLES | QQ_TABLES | {'qq_link_redemptions'}}


def encode(value):
    def binary(item):
        if isinstance(item, bytes):
            return {'sqlite_blob_hex': item.hex()}
        raise TypeError('Unsupported SQLite value')
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'), default=binary)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def content_digest(rows):
    return digest(sorted(encode(row) for row in rows))


def file_digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def quote(name):
    return '"' + name.replace('"','""') + '"'


def overlap(a, b):
    a, b = Path(a).resolve(), Path(b).resolve()
    return a.is_relative_to(b) or b.is_relative_to(a)


def safe_relative(root, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise MigrationError('invalid_dataset_path')
    path = (root / value).resolve()
    if not path.is_relative_to(root) or path == root or path.is_symlink():
        raise MigrationError('dataset_path_escape')
    return path.relative_to(root).as_posix()


def validate_backup(path):
    if not path.is_file() or path.is_symlink():
        raise MigrationError('backup_file_required')
    if any(Path(str(path) + suffix).exists() for suffix in ('-wal','-shm','-journal')):
        raise MigrationError('quiescent_sqlite_backup_required')


def identity_schema_valid(db, version):
    from .cloud_v2 import migrate_identity_schema
    from .cloud_v3 import migrate_qq_schema
    from .cloud_v4 import migrate_qq_redemption_schema
    initializers={2:migrate_identity_schema,3:migrate_qq_schema,4:migrate_qq_redemption_schema}
    if version not in initializers:return False
    expected = sqlite3.connect(':memory:')
    try:
        initializers[version](expected)
        query = "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
        return db.execute(query).fetchall() == expected.execute(query).fetchall()
    finally:
        expected.close()


@contextmanager
def snapshot(path):
    validate_backup(path)
    db = sqlite3.connect(':memory:')
    try:
        original = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            original.backup(db)
        finally:
            original.close()
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise MigrationError('sqlite_integrity_failed')
        yield db
    finally:
        db.close()


def load_mapping(value):
    if isinstance(value, dict):
        mapping = json.loads(encode(value))
    else:
        path = Path(value).resolve()
        mapping = json.loads(path.read_text(encoding='utf-8-sig'))
        if isinstance(mapping, dict) and isinstance(mapping.get('identity_database'), str):
            mapping['identity_database'] = str((path.parent / mapping['identity_database']).resolve())
    if not isinstance(mapping, dict) or mapping.get('version') != 1 or not isinstance(mapping.get('datasets'),list):
        raise MigrationError('invalid_mapping')
    if not isinstance(mapping.get('identity_database'), str) or not mapping['identity_database']:
        raise MigrationError('provisioned_identity_required')
    return mapping


def build_plan(source, mapping):
    if Path(source).is_symlink(): raise MigrationError('source_symlink_rejected')
    root = Path(source).resolve()
    if not root.is_dir():
        raise MigrationError('source_directory_required')
    mapping = load_mapping(mapping)
    identity_path = Path(mapping['identity_database']).resolve()
    if overlap(root, identity_path):
        raise MigrationError('identity_must_be_separate_from_legacy_source')
    report = dict(version=1, ready=False, migrated=0, duplicates=0, conflicts=0,
                  unassigned=0, excluded=0, databases=[], tables=[], files=[], issues=[],
                  reauthorization_required=0, qq_rebinding_required=True, qq_bindings_removed=0,
                  identity_schema_version=None, checks={'source_unchanged':False,'reconciled':False},
                  credential_policy='skip_all_game_credentials_and_invalidate_all_destination_grants',
                  activation_ready=False, key_readability='requires_new_key_and_reauthorization_before_activation')
    def issue(code, database=None, table=None):
        item = {'code':code}
        if database is not None: item['database'] = database
        if table is not None: item['table'] = table
        if item not in report['issues']: report['issues'].append(item)
    datasets, collections, input_hashes = [], {}, {}
    with snapshot(identity_path) as identity:
        identity_hash = file_digest(identity_path)
        tables = {r[0] for r in identity.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        version = identity.execute('PRAGMA user_version').fetchone()[0]
        if version not in KNOWN_IDENTITY_SCHEMAS or tables != KNOWN_IDENTITY_SCHEMAS[version] or identity.execute('SELECT version FROM schema_migrations ORDER BY version').fetchall() != [(v,) for v in range(1,version+1)] or identity.execute('PRAGMA foreign_key_check').fetchall() or not identity_schema_valid(identity,version):
            raise MigrationError('provisioned_identity_schema_invalid')
        report['identity_schema_version'] = version
        qq_tables=(('qq_link_redemptions',) if version==4 else ()) + (INVALIDATE_QQ_TABLES if version>=3 else ())
        invalidated_tables = INVALIDATE_IDENTITY_TABLES + qq_tables
        report['identity_auth_artifacts_cleared'] = {
            table: identity.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
            for table in invalidated_tables}
        report['qq_bindings_removed'] = report['identity_auth_artifacts_cleared'].get('qq_links',0)
        report['reauthorization_required'] = identity.execute('SELECT COUNT(*) FROM grants').fetchone()[0]
        for item in mapping['datasets']:
            try:
                database = safe_relative(root,item['database'])
                kind = item['kind']
                if kind not in TABLES: raise MigrationError('unsupported_dataset_kind')
                scope = AccountScope(item['user_id'],item['account_id'],item['role_id'])
                validate_scope(scope)
                AccountStore(identity).resolve(Principal(scope.user_id,False),scope.account_id,scope.role_id)
                row = identity.execute('SELECT r.game,r.provider,r.game_uid,r.server,g.version FROM roles r JOIN accounts a ON a.account_id=r.account_id JOIN grants g ON g.grant_id=a.grant_id WHERE r.role_id=?', (scope.role_id,)).fetchone()
                game, provider, uid, server, version = row
                wanted_game, wanted_provider = SOURCES.get(kind,(game,provider))
                if game != wanted_game or wanted_provider is not None and provider != wanted_provider:
                    raise MigrationError('dataset_provider_mismatch')
                if kind == 'snapshots' and (game,provider) not in {('wuthering_waves','kuro'),('nte','tajiduo'),('endfield','hypergryph')}:
                    raise MigrationError('dataset_provider_mismatch')
                datasets.append(dict(database=database,kind=kind,scope=scope,game=game,provider=provider,uid=uid,server=server,version=version+1))
            except (KeyError,TypeError,ValueError,LookupError):
                issue('invalid_or_unowned_dataset_mapping')
    exclusions = {}
    for item in mapping.get('exclude_tables',[]):
        try:
            key = (safe_relative(root,item['database']),item['table'])
            if key[1] not in EXCLUDABLE or not isinstance(item['reason'],str) or not item['reason'].strip():
                raise MigrationError('unknown_private_table_cannot_be_excluded')
            if key in exclusions: raise MigrationError('duplicate_exclusion')
            exclusions[key] = item['reason']
        except (KeyError,TypeError,ValueError):
            issue('invalid_table_exclusion')
    seen_exclusions = set()
    seen_datasets = set()
    all_names = set().union(*(set(v) for v in TABLES.values())) | {'scoped_snapshots','scoped_poll_status'}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            issue('source_symlink_rejected',relative)
            continue
        if not path.is_file(): continue
        before = file_digest(path)
        input_hashes[relative] = before
        with path.open('rb') as stream:
            is_sqlite = stream.read(16) == b'SQLite format 3\x00'
        if not is_sqlite:
            if path.suffix.lower() in ('.db','.sqlite','.sqlite3'):
                report['databases'].append({'database':relative,'sha256':before,'valid':False})
                issue('invalid_sqlite_backup',relative)
            elif path.name.endswith(('.credentials.json','.key')):
                report['files'].append({'file':relative,'disposition':'skipped_credentials_reauthorize','sha256':before})
            elif path.name.endswith(('-wal','-shm','-journal')):
                issue('quiescent_sqlite_backup_required',relative)
            else:
                issue('unknown_source_file',relative)
            continue
        report['databases'].append({'database':relative,'sha256':before})
        try:
            with snapshot(path) as db:
                objects = db.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
                for name, objtype in objects:
                    if objtype in ('trigger','view'):
                        issue('unsupported_schema_object',relative,name)
                    if objtype != 'table': continue
                    rows = db.execute('SELECT * FROM ' + quote(name)).fetchall()
                    columns = tuple(r[1] for r in db.execute('PRAGMA table_info(' + quote(name) + ')'))
                    pk = tuple(r[1] for r in sorted(db.execute('PRAGMA table_info(' + quote(name) + ')'),key=lambda r:r[5]) if r[5])
                    summary = {'database':relative,'table':name,'count':len(rows),'content_sha256':content_digest(rows),'assigned':0,'excluded':0}
                    report['tables'].append(summary)
                    if (relative,name) in exclusions:
                        summary['excluded']=len(rows); summary['reason']=exclusions[(relative,name)]
                        report['excluded'] += len(rows)
                        seen_exclusions.add((relative,name))
                        continue
                    if name in EXCLUDABLE:
                        issue('explicit_public_or_unneeded_exclusion_required',relative,name)
                        continue
                    if name not in all_names:
                        issue('unknown_private_table',relative,name)
                        report['unassigned'] += len(rows)
                        continue
                    if name in ('scoped_snapshots','scoped_poll_status'):
                        if rows:
                            issue('already_scoped_source_not_legacy',relative,name)
                            report['unassigned'] += len(rows)
                        continue
                    matches = [d for d in datasets if d['database']==relative and name in TABLES[d['kind']]]
                    valid = []
                    for d in matches:
                        expected = TABLES[d['kind']][name]
                        accepted = {expected}
                        if d['kind'] == 'endfield_gacha' and name == 'pools':
                            accepted.add((expected[0] + ('scan_pending',), expected[1]))
                            accepted.add((expected[0] + ('scan_pending','last_error'), expected[1]))
                        if (columns,pk) not in accepted:
                            issue('legacy_schema_mismatch',relative,name)
                        else:
                            valid.append(d)
                            seen_datasets.add((d['database'],d['kind'],d['scope']))
                    for row in rows:
                        record = dict(zip(columns,row))
                        if name in ('snapshots','poll_status') and record['capability'] in PUBLIC_CAPS:
                            summary['excluded'] += 1; report['excluded'] += 1
                            continue
                        owners = [d for d in valid if belongs(record,d)]
                        if len(owners)!=1:
                            report['unassigned'] += 1
                            issue('ambiguous_owner' if owners else 'unmapped_owner',relative,name)
                            continue
                        d = owners[0]
                        summary['assigned'] += 1
                        try:
                            converted, target_table, target_columns, target_pk = convert(name,columns,pk,row,d)
                        except (ValueError,TypeError):
                            issue('invalid_legacy_payload',relative,name)
                            continue
                        key = (d['scope'],d['kind'],target_table)
                        group = collections.setdefault(key,dict(dataset=d,table=target_table,columns=target_columns,pk=target_pk,rows={},received=0,duplicates=0,origins=set()))
                        group['received'] += 1
                        group['origins'].add((relative,name))
                        row_key = tuple(converted[target_columns.index(c)] for c in target_pk)
                        if row_key in group['rows']:
                            if group['rows'][row_key] == converted:
                                group['duplicates'] += 1; report['duplicates'] += 1
                            else:
                                report['conflicts'] += 1; issue('duplicate_content_conflict',relative,name)
                        else:
                            group['rows'][row_key] = converted
                            report['migrated'] += 1
        except (MigrationError,sqlite3.Error):
            issue('sqlite_backup_or_integrity_failed',relative)
    for d in datasets:
        if (d['database'],d['kind'],d['scope']) not in seen_datasets:
            issue('dataset_file_or_tables_missing',d['database'])
    if seen_exclusions != set(exclusions): issue('excluded_table_missing')
    unchanged = identity_hash == file_digest(identity_path) and all(file_digest(root / p)==h for p,h in input_hashes.items())
    # Detect files created/deleted while scanning as well as byte changes.
    unchanged = unchanged and {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()} == set(input_hashes)
    report['checks']['source_unchanged'] = unchanged
    if not unchanged: issue('source_changed_during_backup')
    report['ready'] = not report['issues']
    return dict(root=root,mapping=mapping,identity=identity_path,identity_hash=identity_hash,input_hashes=input_hashes,
                invalidated_identity_tables=invalidated_tables,
                collections=collections,datasets=datasets,report=report,
                fingerprint=digest({'mapping':mapping,'identity':identity_hash,'files':input_hashes}))


def belongs(record, dataset):
    kind = dataset['kind']
    if kind == 'snapshots': return record['game_id'] == dataset['game']
    if kind == 'blueprints': return True
    if kind.startswith('wuwa_'):
        return record['account'] == dataset['uid'] and record['server'] == dataset['server']
    return record['role'] == dataset['uid']


def convert(name,columns,pk,row,d):
    record = dict(zip(columns,row))
    for column in ('payload','metadata','failed_pools'):
        if column in record and record[column] is not None: json.loads(record[column])
    if d['kind'] == 'endfield_gacha' and name == 'pools' and 'scan_pending' not in record:
        # Normalize legacy metadata without treating a missing successful scan
        # as proof of either an empty pool or a pending synchronization.
        return (*row, 0 if record['last_sync_at'] is not None else None), name, columns + ('scan_pending',), pk
    if name == 'snapshots':
        columns = ('user_id','account_id','role_id','capability','payload','fetched_at','grant_version')
        return (*validate_scope(d['scope']),record['capability'],record['payload'],record['fetched_at'],d['version']), 'scoped_snapshots', columns, columns[:4]
    if name == 'poll_status':
        status = {k:v for k,v in record.items() if k!='game_id'}
        columns = ('user_id','account_id','role_id','capability','status','grant_version')
        return (*validate_scope(d['scope']),record['capability'],json.dumps(status,ensure_ascii=False),d['version']), 'scoped_poll_status', columns, columns[:4]
    return tuple(row),name,columns,pk
