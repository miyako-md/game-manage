"""Local, account-scoped NTE pull ledger. Imported evidence is never a live API."""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

MAX_RECORDS = 50_000
MAX_EXPORT_BYTES = 8 * 1024 * 1024 - 4096  # Leave room for import request envelope.
POOLS = {'Lottery_Permanent', 'Lottery_LimitedCharacter', 'Arc_MiracleBox', 'Gashapon_MysteryBox'}
OWN_FORMAT = 'game-assistant-nte-gacha'


class GachaError(ValueError):
    def __init__(self, message='抽卡文件格式不正确', status=422):
        super().__init__(message)
        self.status = status


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _text(value, maximum=200, required=False):
    if value is None and not required:
        return ''
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise GachaError()
    return value.strip()


def _integer(value, maximum=1_000_000):
    if type(value) is not int or not 0 <= value <= maximum:
        raise GachaError()
    return value


def _warnings(scan):
    if not isinstance(scan, dict) or not isinstance(scan.get('warnings', []), list):
        raise GachaError()
    result = []
    for warning in scan.get('warnings', []):
        # Retain diagnostic codes; arbitrary upstream text may contain paths/credentials.
        if isinstance(warning, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,99}', warning):
            result.append(warning)
        else:
            result.append('SOURCE_WARNING')
    if _integer(scan.get('skipped_records', 0), MAX_RECORDS):
        result.append('SKIPPED_RECORDS')
    if 'pages_seen' in scan:
        pages = scan['pages_seen']
        if not isinstance(pages, list) or len(pages) > MAX_RECORDS:
            raise GachaError()
        pages = sorted({_integer(page, MAX_RECORDS) for page in pages})
        if not pages or pages != list(range(1, len(pages)+1)):
            result.append('SOURCE_PAGE_GAP')
    return sorted(set(result))


def _row(raw, default_pool=None):
    if not isinstance(raw, dict):
        raise GachaError()
    pool = raw.get('pool_group_id', default_pool)
    if pool not in POOLS:
        raise GachaError('尚不支持此卡池格式')
    timestamp = _text(raw.get('timestamp'), 19, True)
    try:
        parsed = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        if parsed.strftime('%Y-%m-%d %H:%M:%S') != timestamp:
            raise ValueError()
    except ValueError:
        raise GachaError('记录时间格式不正确') from None
    roll = raw.get('roll_result')
    if roll is not None and (type(roll) is not int or not -4 <= roll <= 6):
        raise GachaError('骰子结果格式不正确')
    return dict(uid=_text(raw.get('uid'), 128, True), pool_group_id=pool,
                timestamp=timestamp, timestamp_group_ordinal=_integer(raw.get('timestamp_group_ordinal')),
                reward_id=_text(raw.get('reward_id'), 128, True),
                reward_name=_text(raw.get('reward_name', ''), 200),
                reward_type=_text(raw.get('reward_type', ''), 40),
                reward_rank=_text(raw.get('reward_rank', ''), 20),
                result_type=_text(raw.get('result_type', ''), 40),
                quantity=None if raw.get('quantity') is None else _integer(raw['quantity']),
                roll_result=roll,
                source_type=_text(raw.get('source_type', ''), 40))


def _ordered(rows):
    # Descending timestamp, ascending ordinal (ordinal zero is newest).
    return sorted(sorted(rows, key=lambda r: r['timestamp_group_ordinal']),
                  key=lambda r: r['timestamp'], reverse=True)


def _segment_warnings(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row['timestamp'], []).append(row['timestamp_group_ordinal'])
    return ['ORDINAL_GAP'] if any(sorted(v) != list(range(len(v))) for v in groups.values()) else []


def _metadata(document):
    return {key: _text(document[key], 40, True) for key in ('server_id', 'account_region') if key in document}


def _rule(raw, archive=False):
    if not isinstance(raw, dict) or (raw.get('basis') != 'user_configured' if archive else raw.get('confirmed') is not True):
        raise GachaError('请明确确认这是用户设置的规则')
    pool = raw.get('pool_id')
    expected = 'arc' if pool == 'Arc_MiracleBox' else 'character'
    if pool not in POOLS or pool == 'Gashapon_MysteryBox' or raw.get('reset_reward_type') != expected:
        raise GachaError('卡池与重置奖励类型不匹配')
    threshold = _integer(raw.get('s_hard_pity'), 1000)
    if threshold < 1:
        raise GachaError()
    return dict(pool_id=pool, s_hard_pity=threshold, reset_reward_type=expected,
                source_note=_text(raw.get('source_note'), 200, True), basis='user_configured')


def _archive_rules(document):
    raw = document.get('rules', []) if document['format'] == OWN_FORMAT else []
    if not isinstance(raw, list) or len(raw) > len(POOLS):
        raise GachaError('归档规则格式不正确')
    result = [_rule(r, archive=True) for r in raw]
    if len({r['pool_id'] for r in result}) != len(result):
        raise GachaError('归档规则重复')
    return result


class GachaStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._preview_secret = secrets.token_bytes(32)
        with self._db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS records (
                  role TEXT NOT NULL, pool TEXT NOT NULL, uid TEXT NOT NULL, payload TEXT NOT NULL,
                  PRIMARY KEY(role,pool,uid));
                CREATE TABLE IF NOT EXISTS batches (
                  role TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL,
                  PRIMARY KEY(role,digest));
                CREATE TABLE IF NOT EXISTS rules (
                  role TEXT NOT NULL, pool TEXT NOT NULL, payload TEXT NOT NULL,
                  PRIMARY KEY(role,pool));
                CREATE TABLE IF NOT EXISTS accounts (
                  role TEXT PRIMARY KEY, metadata TEXT NOT NULL);
            ''')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(str(self.path), timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _normalize(self, role, document, latest_confirmed=False, continuity_confirmed=False):
        if not role:
            raise GachaError('请先登录并选择异环角色', 409)
        if not isinstance(document, dict) or document.get('format') not in ('nte-history-export', OWN_FORMAT):
            raise GachaError('仅支持逐抽导出 JSON；社区统计和截图识别文件需先转换')
        if type(document.get('format_version')) is not int or document['format_version'] != 1:
            raise GachaError('不支持此导出版本')
        _metadata(document)
        _archive_rules(document)
        identity = document.get('user_uid')
        if identity is not None and (not isinstance(identity, str) or identity != role):
            raise GachaError('文件角色身份与当前异环角色不一致', 409)
        missing_identity = identity is None
        raw_rows = document.get('records')
        if not isinstance(raw_rows, list) or not raw_rows or len(raw_rows) > MAX_RECORDS:
            raise GachaError('记录数量必须为 1 至 50000 条')
        own = document['format'] == OWN_FORMAT
        banner = document.get('banner', {})
        if not isinstance(banner, dict) or (not own and banner.get('id') not in POOLS):
            raise GachaError()
        rows = [_row(raw, banner.get('id')) for raw in raw_rows]
        if not own and any(r['pool_group_id'] != banner['id'] for r in rows):
            raise GachaError('文件卡池与记录卡池不一致')
        unique = {}
        for row in rows:
            key = row['pool_group_id'], row['uid']
            if key in unique and unique[key] != row:
                raise GachaError('文件存在冲突记录', 409)
            unique[key] = row
        rows = _ordered(list(unique.values()))
        warnings = _warnings(document.get('scan', {}))
        coverage = []
        if own:
            raw_coverage = document.get('coverage')
            if not isinstance(raw_coverage, list) or not raw_coverage or len(raw_coverage) > MAX_RECORDS:
                raise GachaError('归档缺少完整性边界')
            covered_keys = set()
            reference_count = 0
            for segment in raw_coverage:
                if not isinstance(segment, dict) or segment.get('pool_id') not in POOLS:
                    raise GachaError()
                ids = segment.get('record_uids')
                if not isinstance(ids, list) or not ids or len(ids) > MAX_RECORDS:
                    raise GachaError()
                for uid in ids:
                    if not isinstance(uid, str) or (segment['pool_id'], uid) not in unique:
                        raise GachaError('归档边界与记录不一致')
                    covered_keys.add((segment['pool_id'], uid))
                reference_count += len(ids)
                if reference_count > 200_000:
                    raise GachaError('归档完整性边界过多，请按池分别导出')
                cov_warnings = _warnings({'warnings': segment.get('warnings', [])})
                basis = segment.get('basis', 'unconfirmed')
                if basis not in ('user_confirmed', 'unconfirmed'):
                    raise GachaError()
                cov_time = _text(segment.get('latest_record_at', segment.get('as_of')), 40, True)
                confirmed_at = _text(segment.get('confirmed_at', ''), 40)
                imported_at = _text(segment.get('imported_at', ''), 40)
                coverage.append(dict(pool_id=segment['pool_id'], record_uids=list(dict.fromkeys(ids)),
                    latest_confirmed=segment.get('latest_confirmed') is True,
                    continuity_confirmed=segment.get('continuity_confirmed') is True,
                    basis=basis, as_of=cov_time, latest_record_at=cov_time,
                    confirmed_at=confirmed_at, imported_at=imported_at,
                    warnings=sorted(set(cov_warnings + warnings))))
            if covered_keys != set(unique):
                raise GachaError('归档存在无来源边界的记录')
            # Archive checkboxes never upgrade exported evidence.
        else:
            now = datetime.now(timezone.utc).isoformat()
            pool = banner['id']
            latest_record_at = rows[0]['timestamp']
            coverage.append(dict(pool_id=pool, record_uids=[r['uid'] for r in rows],
                latest_confirmed=latest_confirmed, continuity_confirmed=continuity_confirmed,
                basis='user_confirmed' if latest_confirmed and continuity_confirmed else 'unconfirmed',
                as_of=latest_record_at, latest_record_at=latest_record_at,
                confirmed_at=now if latest_confirmed or continuity_confirmed else '',
                imported_at=now, warnings=warnings + _segment_warnings(rows)))
        return rows, coverage, warnings, missing_identity

    def _ticket(self, role, doc, options):
        try:
            raw = _json([role, doc, options]).encode()
        except (ValueError, TypeError, RecursionError):
            raise GachaError() from None
        return hmac.new(self._preview_secret, raw, hashlib.sha256).hexdigest()

    def preview(self, role, document, *, latest_confirmed=False, continuity_confirmed=False,
                identity_confirmed=False):
        options = dict(latest_confirmed=latest_confirmed, continuity_confirmed=continuity_confirmed,
                       identity_confirmed=identity_confirmed)
        rows, coverage, warnings, missing_identity = self._normalize(
            role, document, latest_confirmed=latest_confirmed, continuity_confirmed=continuity_confirmed)
        duplicates = 0
        with self._db() as db:
            self._check_metadata(db, role, _metadata(document))
            self._check_rules(db, role, _archive_rules(document))
            for row in rows:
                existing = db.execute('SELECT payload FROM records WHERE role=? AND pool=? AND uid=?',
                                     (role, row['pool_group_id'], row['uid'])).fetchone()
                if existing:
                    if json.loads(existing[0]) != row:
                        raise GachaError('已有流水与导入记录冲突，整批未写入', 409)
                    duplicates += 1
        return dict(preview_id=self._ticket(role, document, options), role_id=role,
                    record_count=len(rows), new_records=len(rows)-duplicates, duplicates=duplicates,
                    pools=sorted({r['pool_group_id'] for r in rows}), warnings=warnings,
                    source_metadata=_metadata(document), imported_rules=_archive_rules(document),
                    identity_confirmation_required=missing_identity and not identity_confirmed,
                    missing_requirements=(['identity_confirmation'] if missing_identity and not identity_confirmed else []) +
                      ([] if all(c['latest_confirmed'] and c['continuity_confirmed'] for c in coverage)
                       else ['latest_and_continuity_confirmation']))

    def import_document(self, role, document, *, preview_id, latest_confirmed=False,
                        continuity_confirmed=False, identity_confirmed=False):
        options = dict(latest_confirmed=latest_confirmed, continuity_confirmed=continuity_confirmed,
                       identity_confirmed=identity_confirmed)
        if not isinstance(preview_id, str) or not hmac.compare_digest(preview_id, self._ticket(role, document, options)):
            raise GachaError('导入内容或确认选项已变化，请重新预览', 409)
        rows, coverage, warnings, missing_identity = self._normalize(
            role, document, latest_confirmed=latest_confirmed, continuity_confirmed=continuity_confirmed)
        if missing_identity and not identity_confirmed:
            raise GachaError('文件缺少角色身份，请明确确认归属后重新预览', 409)
        imported = 0
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            metadata = self._check_metadata(db, role, _metadata(document))
            archive_rules = _archive_rules(document)
            self._check_rules(db, role, archive_rules)
            for row in rows:
                old = db.execute('SELECT payload FROM records WHERE role=? AND pool=? AND uid=?',
                                 (role, row['pool_group_id'], row['uid'])).fetchone()
                if old and json.loads(old[0]) != row:
                    raise GachaError('已有流水与导入记录冲突，整批未写入', 409)
                if not old:
                    db.execute('INSERT INTO records VALUES(?,?,?,?)',
                               (role, row['pool_group_id'], row['uid'], _json(row)))
                    imported += 1
            batch = dict(coverage=coverage, warnings=warnings,
                         source_format=document['format'], source_metadata=_metadata(document),
                         imported_at=datetime.now(timezone.utc).isoformat(),
                         identity_basis='user_confirmed' if missing_identity else 'file_uid')
            digest = hashlib.sha256(_json([document, options]).encode()).hexdigest()
            db.execute('INSERT OR IGNORE INTO batches VALUES(?,?,?)', (role, digest, _json(batch)))
            db.execute('INSERT OR REPLACE INTO accounts VALUES(?,?)', (role, _json(metadata)))
            for rule in archive_rules:
                db.execute('INSERT OR IGNORE INTO rules VALUES(?,?,?)', (role, rule['pool_id'], _json(rule)))
        return dict(imported=imported, duplicates=len(rows)-imported, summary=self.summary(role))

    def records(self, role, pool_id=None, limit=100, offset=0):
        with self._db() as db:
            sql, args = 'SELECT payload FROM records WHERE role=?', [role]
            if pool_id:
                sql += ' AND pool=?'
                args.append(pool_id)
            rows = _ordered([json.loads(row[0]) for row in db.execute(sql, args)])
        return dict(role_id=role, total=len(rows), records=rows[offset:offset+limit])

    def rules(self, role):
        with self._db() as db:
            return {'rules': [json.loads(r[0]) for r in db.execute('SELECT payload FROM rules WHERE role=? ORDER BY pool', (role,))]}

    def _check_metadata(self, db, role, incoming):
        found = db.execute('SELECT metadata FROM accounts WHERE role=?', (role,)).fetchone()
        existing = json.loads(found[0]) if found else {}
        if any(key in existing and value != existing[key] for key, value in incoming.items()):
            raise GachaError('文件服务器或地区与当前账本不一致，整批未写入', 409)
        return {**existing, **incoming}

    def _check_rules(self, db, role, rules):
        for rule in rules:
            old = db.execute('SELECT payload FROM rules WHERE role=? AND pool=?', (role, rule['pool_id'])).fetchone()
            if old and json.loads(old[0]) != rule:
                raise GachaError('归档规则与已有用户设置冲突，整批未写入', 409)

    def set_rule(self, role, raw):
        rule = _rule(raw)
        with self._db() as db:
            db.execute('INSERT OR REPLACE INTO rules VALUES(?,?,?)', (role, rule['pool_id'], _json(rule)))
        return rule

    def _batches(self, role):
        with self._db() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM batches WHERE role=?', (role,))]

    def summary(self, role):
        all_rows = self.records(role, limit=2**31)['records']
        rules = {r['pool_id']: r for r in self.rules(role)['rules']}
        coverage = [c for b in self._batches(role) for c in b['coverage']]
        pools = []
        for pool in sorted({r['pool_group_id'] for r in all_rows}):
            rows = [r for r in all_rows if r['pool_group_id'] == pool]
            candidates = [c for c in coverage if c['pool_id'] == pool and rows[0]['uid'] in c['record_uids']]
            segment = max(candidates, key=lambda c: c.get('confirmed_at') or c.get('imported_at', '')) if candidates else None
            warnings = list(segment['warnings']) if segment else []
            requirements = []
            pity = dict(status='unknown', count=None, basis='unconfirmed', as_of=None,
                        latest_record_at=rows[0]['timestamp'], confirmed_at=None, imported_at=None,
                        hard_pity_remaining=None, rule_basis=rules.get(pool, {}).get('basis'), missing_requirements=requirements)
            if segment:
                pity.update(basis=segment['basis'], as_of=segment['as_of'],
                            confirmed_at=segment.get('confirmed_at'), imported_at=segment.get('imported_at'))
            if not segment or not segment['latest_confirmed']:
                requirements.append('latest_records_confirmation')
            if not segment or not segment['continuity_confirmed']:
                requirements.append('continuous_records_confirmation')
            if warnings:
                requirements.append('resolve_source_gaps')
            if pool == 'Gashapon_MysteryBox':
                requirements.append('rotation_and_reset_rules')
            segment_ids = set(segment['record_uids']) if segment else set()
            segment_rows = [r for r in rows if r['uid'] in segment_ids]
            if segment_rows:
                last_index = max(i for i, row in enumerate(rows) if row['uid'] in segment_ids)
                if any(row['uid'] not in segment_ids for row in rows[:last_index+1]):
                    requirements.append('known_records_missing_from_segment')
            if _segment_warnings(segment_rows):
                requirements.append('resolve_record_order')
            count, reset = 0, False
            target = 'arc' if pool == 'Arc_MiracleBox' else 'character'
            if not requirements:
                for row in segment_rows:
                    kind = row['result_type']
                    if kind in ('points_gift', 'chase_reward', 'sleeping_land'):
                        continue
                    valid_pull = kind == 'dice' if target == 'character' else (kind in ('', 'single_pull') and row['source_type'] == 'miracle_box')
                    if target == 'character' and row['roll_result'] is not None and row['roll_result'] not in range(1, 7):
                        valid_pull = False
                    if not valid_pull or row['reward_type'] not in ('character', 'arc', 'item') or row['reward_rank'] not in ('S', 'A', 'B'):
                        requirements.append('identify_pull_reward_semantics')
                        break
                    if row['reward_rank'] == 'S' and row['reward_type'] == target:
                        reset = True
                        break
                    count += 1
                if not requirements:
                    pity.update(status='exact' if reset else 'lower_bound', count=count)
            rule = rules.get(pool)
            if not rule:
                requirements.append('hard_pity_rule')
            elif pity['status'] == 'exact':
                if count >= rule['s_hard_pity']:
                    pity.update(status='unknown', count=None)
                    requirements.append('rule_record_conflict')
                else:
                    pity['hard_pity_remaining'] = rule['s_hard_pity'] - count
            if pool == 'Gashapon_MysteryBox':
                total_pulls = sum(r['source_type'] == 'mystery_box' and r['result_type'] == 'single_pull' for r in rows)
            elif target == 'arc':
                total_pulls = sum(r['source_type'] == 'miracle_box' and r['result_type'] in ('', 'single_pull') for r in rows)
            else:
                total_pulls = sum(r['result_type'] == 'dice' for r in rows)
            pools.append(dict(pool_id=pool, total_records=len(rows), total_pulls=total_pulls, pity=pity, warnings=warnings))
        return dict(role_id=role, total_records=len(all_rows), pools=pools,
                    missing_requirements=[] if all_rows else ['import_pull_history'])

    def export(self, role, pool_id=None, *, offset=None, limit=None):
        all_rows = self.records(role, pool_id, limit=2**31)['records']
        total = len(all_rows)
        if not total:
            raise GachaError('当前没有可导出的逐抽记录', 409)
        paged = offset is not None or limit is not None
        start = 0 if offset is None else _integer(offset, 2**31)
        count = (min(2000, MAX_RECORDS) if paged else total) if limit is None else _integer(limit, MAX_RECORDS)
        if not count or start >= total:
            raise GachaError('导出分段范围不正确')
        if not paged and total > MAX_RECORDS:
            raise GachaError('累计账本超过单文件记录上限，请使用 offset/limit 分段导出', 413)
        count = min(count, total-start)
        batches = self._batches(role)
        with self._db() as db:
            metadata = self._check_metadata(db, role, {})
        rules = [r for r in self.rules(role)['rules'] if not pool_id or r['pool_id'] == pool_id]
        while count:
            rows = all_rows[start:start+count]
            keys = {(r['pool_group_id'], r['uid']) for r in rows}
            partial = start != 0 or count != total
            coverage = []
            source_warnings = {}
            for batch in batches:
                for segment in batch['coverage']:
                    ids = [uid for uid in segment['record_uids'] if (segment['pool_id'], uid) in keys]
                    if not ids:
                        continue
                    if partial:
                        source_warnings.setdefault(segment['pool_id'], set()).update(segment['warnings'])
                    else:
                        coverage.append(dict(segment, record_uids=ids))
            if partial:
                # A page is a transport slice, not proof of a continuous source scan.
                # Compact overlapping provenance without inventing a joined boundary.
                for pool in sorted({r['pool_group_id'] for r in rows}):
                    pool_rows = [r for r in rows if r['pool_group_id'] == pool]
                    warnings = sorted(source_warnings.get(pool, set()))
                    if len(warnings) > 1000:
                        warnings = warnings[:1000] + ['SOURCE_WARNING_TRUNCATED']
                    coverage.append(dict(pool_id=pool, record_uids=[r['uid'] for r in pool_rows],
                        latest_confirmed=False, continuity_confirmed=False, basis='unconfirmed',
                        as_of=pool_rows[0]['timestamp'], latest_record_at=pool_rows[0]['timestamp'],
                        confirmed_at='', imported_at='', warnings=sorted(set(warnings + ['ARCHIVE_SEGMENTED']))))
            result = dict(format=OWN_FORMAT, format_version=1, user_uid=role, records=rows, **metadata,
                          rules=rules, coverage=coverage, scan={'warnings': []},
                          timestamp_basis='source_display_time; timezone_not_inferred')
            if paged:
                result['export_page'] = dict(offset=start, limit=count, total=total,
                                            next_offset=start+count if start+count < total else None)
            references = sum(len(c['record_uids']) for c in coverage)
            fits = len(coverage) <= MAX_RECORDS and references <= 200_000 and len(_json(result).encode('utf-8')) <= MAX_EXPORT_BYTES
            if fits:
                return result
            if not paged:
                raise GachaError('累计账本超过单文件大小或覆盖边界上限，请使用 offset/limit 分段导出', 413)
            if count == 1:
                raise GachaError('单条记录及其来源信息超过导出上限，无法生成可恢复分段', 413)
            count = max(1, count // 2)
