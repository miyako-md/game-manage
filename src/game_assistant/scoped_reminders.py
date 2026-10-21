"""Persistent isolated delivery claims and authenticated website inbox."""
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from .reminder_policy import ReminderRule, SHANGHAI, stamina_candidates
from .accounts.store import AccountNotFoundError


class ReminderStore:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS reminder_rules(
                user_id TEXT, account_id TEXT, role_id TEXT, body TEXT NOT NULL,
                PRIMARY KEY(user_id,account_id,role_id));
            CREATE TABLE IF NOT EXISTS reminder_delivery(
                user_id TEXT, account_id TEXT, role_id TEXT, rule TEXT, target TEXT,
                lease TEXT, lease_until REAL, attempted_at REAL, last_success REAL,
                success_day TEXT, success_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id,account_id,role_id,rule,target));
            CREATE TABLE IF NOT EXISTS reminder_inbox(
                id INTEGER PRIMARY KEY, user_id TEXT, account_id TEXT, role_id TEXT,
                grant_version INTEGER, title TEXT, body TEXT, source_read_at TEXT, delivered_at TEXT);
            CREATE TABLE IF NOT EXISTS qq_group_settings(
                app_id TEXT, group_openid TEXT, body TEXT NOT NULL,
                PRIMARY KEY(app_id,group_openid));
            CREATE TABLE IF NOT EXISTS qq_group_limits(
                app_id TEXT, group_openid TEXT, window INTEGER, count INTEGER,
                PRIMARY KEY(app_id,group_openid));
        ''')

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield self.db
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    @staticmethod
    def scope_key(scope):
        return scope.user_id, scope.account_id, scope.role_id

    def get_rule(self, scope):
        with self.lock:
            row = self.db.execute('SELECT body FROM reminder_rules WHERE user_id=? AND account_id=? AND role_id=?', self.scope_key(scope)).fetchone()
        return ReminderRule.model_validate_json(row[0]) if row else ReminderRule()

    def set_rule(self, scope, rule):
        with self.transaction() as db:
            db.execute('INSERT INTO reminder_rules VALUES(?,?,?,?) ON CONFLICT(user_id,account_id,role_id) DO UPDATE SET body=excluded.body',
                       (*self.scope_key(scope), rule.model_dump_json()))

    def claim(self, scope, rule_name, target, policy, now):
        timestamp, day = now.timestamp(), now.astimezone(SHANGHAI).date().isoformat()
        key = (*self.scope_key(scope), rule_name, target)
        with self.transaction() as db:
            row = db.execute('SELECT * FROM reminder_delivery WHERE user_id=? AND account_id=? AND role_id=? AND rule=? AND target=?', key).fetchone()
            if row:
                if row['lease_until'] is not None and row['lease_until'] > timestamp:
                    return None
                if row['attempted_at'] is not None and timestamp - row['attempted_at'] < policy.cooldown_seconds:
                    return None
                if row['success_day'] == day and row['success_count'] >= policy.daily_cap:
                    return None
            lease = uuid.uuid4().hex
            db.execute('INSERT INTO reminder_delivery(user_id,account_id,role_id,rule,target,lease,lease_until,attempted_at) VALUES(?,?,?,?,?,?,?,?) '
                       'ON CONFLICT(user_id,account_id,role_id,rule,target) DO UPDATE SET lease=excluded.lease,lease_until=excluded.lease_until,attempted_at=excluded.attempted_at',
                       (*key, lease, timestamp + 300, timestamp))
            return lease

    def finish(self, lease, *, success, now, message=None, version=None):
        with self.transaction() as db:
            row = db.execute('SELECT * FROM reminder_delivery WHERE lease=? AND lease_until>=?', (lease, now.timestamp())).fetchone()
            if row is None:
                return False
            day = now.astimezone(SHANGHAI).date().isoformat()
            if success:
                count = row['success_count'] + 1 if row['success_day'] == day else 1
                db.execute('UPDATE reminder_delivery SET last_success=?,success_day=?,success_count=? WHERE lease=?', (now.timestamp(), day, count, lease))
                if message:
                    db.execute('INSERT INTO reminder_inbox(user_id,account_id,role_id,grant_version,title,body,source_read_at,delivered_at) VALUES(?,?,?,?,?,?,?,?)',
                        (row['user_id'], row['account_id'], row['role_id'], version, message['title'], message['body'], message['source_read_at'], now.isoformat()))
                    # Bounded history per role, independent of success counters.
                    db.execute('DELETE FROM reminder_inbox WHERE user_id=? AND account_id=? AND role_id=? AND id NOT IN '
                               '(SELECT id FROM reminder_inbox WHERE user_id=? AND account_id=? AND role_id=? ORDER BY id DESC LIMIT 100)',
                               (row['user_id'], row['account_id'], row['role_id']) * 2)
            db.execute('UPDATE reminder_delivery SET lease=NULL,lease_until=NULL WHERE lease=?', (lease,))
            return True

    def inbox(self, scope, version, *, minimum_version=None):
        with self.lock:
            return [dict(row) for row in self.db.execute('SELECT id,title,body,source_read_at,delivered_at FROM reminder_inbox '
                'WHERE user_id=? AND account_id=? AND role_id=? AND grant_version BETWEEN ? AND ? ORDER BY id DESC LIMIT 100',
                (*self.scope_key(scope), minimum_version if minimum_version is not None else version, version))]

    def close(self):
        with self.lock:
            self.db.close()


class ScopedReminderService:
    def __init__(self, store, accounts, *, clock=None):
        self.store, self.accounts = store, accounts
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        accounts._listeners.append(self._grant_changed)

    def _grant_changed(self, user_id, grant_id):
        rows = self.accounts.connection.execute('SELECT a.account_id FROM accounts a JOIN grants g ON g.grant_id=a.grant_id '
            "WHERE a.user_id=? AND a.grant_id=? AND g.state LIKE 'revoked%'", (user_id, grant_id)).fetchall()
        for row in rows:
            with self.store.transaction() as db:
                for saved in db.execute('SELECT role_id,body FROM reminder_rules WHERE user_id=? AND account_id=?', (user_id,row[0])).fetchall():
                    rule = ReminderRule.model_validate_json(saved['body']).model_copy(update={'enabled':False})
                    db.execute('UPDATE reminder_rules SET body=? WHERE user_id=? AND account_id=? AND role_id=?',
                               (rule.model_dump_json(),user_id,row[0],saved['role_id']))
                db.execute('UPDATE reminder_delivery SET lease=NULL,lease_until=NULL WHERE user_id=? AND account_id=?', (user_id,row[0]))

    def close(self):
        if self._grant_changed in self.accounts._listeners:
            self.accounts._listeners.remove(self._grant_changed)
        self.store.close()

    def get_rule(self, scope):
        self.accounts.describe(scope, active=False)
        return self.store.get_rule(scope)

    def set_rule(self, scope, rule):
        info = self.accounts.describe(scope, active=False)
        if rule.enabled and info['state'] != 'active':
            raise AccountNotFoundError()
        if info['game'] != 'nte' and rule.city_threshold_percent is not None:
            raise ValueError('city stamina only available for NTE')
        self.store.set_rule(scope, rule)
        return rule

    def inbox(self, scope):
        version, generation = self.accounts.snapshot_bounds(scope)
        return self.store.inbox(scope, version, minimum_version=generation)

    def handle_poll(self, scope, capability, result, version):
        info = self.accounts.describe(scope)
        if info['version'] != version or not result.ok or capability != 'stamina':
            return
        now, policy = self.clock(), self.store.get_rule(scope)
        for message in stamina_candidates(result.payload, policy, now):
            lease = self.store.claim(scope, message['rule'], 'inbox', policy, now)
            if lease:
                # No await between latest grant check and local inbox transaction.
                if self.accounts.describe(scope)['version'] != version:
                    self.store.finish(lease, success=False, now=now)
                    return
                self.store.finish(lease, success=True, now=now, message=message, version=version)
