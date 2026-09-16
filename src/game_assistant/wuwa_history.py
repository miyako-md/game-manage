"""Local observations, never reconstructed or inferred historical results."""
import hashlib
import json
from datetime import datetime, timezone


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def stable_data(value):
    if isinstance(value, dict):
        return {k: stable_data(v) for k, v in value.items()
                if k not in ('provenance', 'fetched_at', 'season_end_time', 'season_end_at')}
    if isinstance(value, list):
        return [stable_data(v) for v in value]
    return value


def changes(before, after, path=''):
    if isinstance(before, dict) and isinstance(after, dict):
        result = {}
        for key in sorted(before.keys() | after.keys()):
            result.update(changes(before.get(key), after.get(key), f'{path}.{key}' if path else key))
        return result
    if before == after:
        return {}
    numeric = lambda n: isinstance(n, (int, float)) and not isinstance(n, bool)
    return {path: {'before': before, 'after': after,
                   'delta': after - before if numeric(before) and numeric(after) else None}}


class WuwaHistory:
    def __init__(self, conn, lock):
        self.conn, self.lock = conn, lock
        with lock:
            conn.execute('CREATE TABLE IF NOT EXISTS wuwa_history ('
                         'id INTEGER PRIMARY KEY, account TEXT NOT NULL, server TEXT NOT NULL,'
                         'kind TEXT NOT NULL, subject TEXT NOT NULL, season TEXT NOT NULL,'
                         'content_hash TEXT NOT NULL, payload TEXT NOT NULL, source TEXT,'
                         'source_at TEXT, observed_at TEXT NOT NULL, archived_at TEXT NOT NULL)')
            conn.execute('CREATE INDEX IF NOT EXISTS wuwa_history_scope ON wuwa_history '
                         '(account,server,kind,subject,season,id)')
            conn.commit()

    def append(self, account, server, kind, payload, *, subject='', season='', source=None,
               source_at=None, observed_at=None):
        if not account or not server:
            return 0
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(json.dumps(stable_data(payload), sort_keys=True).encode()).hexdigest()
        scope = (str(account), str(server), kind, str(subject), season)
        with self.lock:
            previous = self.conn.execute('SELECT content_hash FROM wuwa_history WHERE '
                'account=? AND server=? AND kind=? AND subject=? AND season=? ORDER BY id DESC LIMIT 1', scope).fetchone()
            if previous and previous[0] == digest:
                return 0
            self.conn.execute('INSERT INTO wuwa_history '
                '(account,server,kind,subject,season,content_hash,payload,source,source_at,observed_at,archived_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?)', (*scope, digest, encoded, source, source_at, observed_at or now_iso(), now_iso()))
            self.conn.commit()
        return 1

    def capture(self, capability, payload, *, expected=None, observed_at=None):
        def allowed(account, server):
            return bool(account and server) and (expected is None or (str(account), str(server)) == expected)
        if capability == 'roles' and isinstance(payload, list):
            count = 0
            for role in payload:
                if not isinstance(role, dict):
                    continue
                extra = role.get('extra') or {}
                if not isinstance(extra, dict):
                    continue
                account, server = extra.get('account_role_id'), extra.get('server_id')
                if allowed(account, server) and role.get('role_id'):
                    provenance = extra.get('provenance') or {}
                    count += self.append(account, server, 'roles', role, subject=role['role_id'],
                        source=provenance.get('endpoint', 'roleData'), source_at=provenance.get('fetched_at'), observed_at=observed_at)
            return count
        if not isinstance(payload, dict):
            return 0
        account, server = payload.get('role_id'), payload.get('server_id')
        if not allowed(account, server):
            return 0
        if capability == 'role_detail' and payload.get('character_id'):
            provenance = payload.get('provenance') or {}
            return self.append(account, server, 'role_detail', payload, subject=payload['character_id'],
                source=provenance.get('endpoint', 'getRoleDetail'), source_at=provenance.get('fetched_at'), observed_at=observed_at)
        if capability == 'combat':
            tower = payload.get('tower') or {}
            if not isinstance(tower, dict):
                return 0
            data = tower.get('data')
            if tower.get('state') != 'ok' or not isinstance(data, dict):
                return 0
            try:
                end = datetime.fromisoformat(data['season_end_at'])
                source_time = datetime.fromisoformat(tower['fetched_at'])
                if end.tzinfo is None or source_time.tzinfo is None or end <= source_time:
                    return 0
                season = datetime.fromtimestamp(round(end.timestamp() / 60) * 60, timezone.utc).isoformat()
            except (KeyError, TypeError, ValueError, OverflowError):
                return 0
            return self.append(account, server, 'tower', data, season=season, source=tower.get('source'),
                source_at=tower.get('fetched_at'), observed_at=observed_at)
        return 0

    def read(self, account, server, kind, limit=100, offset=0):
        limit, offset = min(max(int(limit), 1), 500), max(int(offset), 0)
        scope = (account, server, kind)
        with self.lock:
            total, start = self.conn.execute('SELECT COUNT(*),MIN(archived_at) FROM wuwa_history '
                'WHERE account=? AND server=? AND kind=?', scope).fetchone()
            rows = self.conn.execute('SELECT id,subject,season,payload,source,source_at,observed_at,archived_at FROM wuwa_history '
                'WHERE account=? AND server=? AND kind=? ORDER BY id DESC LIMIT ? OFFSET ?', (*scope, limit, offset)).fetchall()
            items = []
            for row in rows:
                id_, subject, season, raw, source, source_at, observed, archived = row
                previous = self.conn.execute('SELECT payload FROM wuwa_history WHERE account=? AND server=? AND kind=? '
                    'AND subject=? AND season=? AND id<? ORDER BY id DESC LIMIT 1', (*scope, subject, season, id_)).fetchone()
                payload = json.loads(raw)
                items.append(dict(id=id_, subject=subject, season=season or None, payload=payload,
                    source=source, source_at=source_at, observed_at=observed, archived_at=archived,
                    delta=changes(stable_data(json.loads(previous[0])), stable_data(payload)) if previous else None))
        return dict(schema_version=1, role_id=account, server_id=server, kind=kind, items=items,
            total=total, limit=limit, offset=offset, archive_started_at=start, complete=False,
            coverage='仅保存成功观测；首条记录之前的成绩和练度未知')

    def backfill(self, store, account, server):
        count = 0
        for capability in ('combat', 'roles'):
            snap = store.get('wuthering_waves', capability)
            if snap:
                try:
                    count += self.capture(capability, json.loads(snap['payload']), expected=(account, server), observed_at=snap['fetched_at'])
                except (ValueError, TypeError):
                    continue
        return {'inserted': count, 'complete': False, 'sources': ['local_snapshot'],
                'message': '仅回补现存同账号快照；官方无已验证的历史成绩接口，未推测旧记录'}
