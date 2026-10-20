"""Owned account management. Only validated provider responses create identities."""
from contextlib import contextmanager
import uuid

from game_assistant.identity.models import Principal
from .store import AccountNotFoundError, AccountStore
from .identities import CHANNELS, has_verified_role, role_channel


PROVIDER_GAMES = {'kuro': 'wuthering_waves', 'tajiduo': 'nte',
                  'hypergryph': 'endfield', 'skland': 'endfield'}


@contextmanager
def transaction(connection):
    nested = connection.in_transaction
    if nested:
        connection.execute('SAVEPOINT account_mutation')
    else:
        connection.execute('BEGIN IMMEDIATE')
    try:
        yield
        if nested:
            connection.execute('RELEASE SAVEPOINT account_mutation')
        else:
            connection.commit()
    except BaseException:
        if nested:
            connection.execute('ROLLBACK TO SAVEPOINT account_mutation')
            connection.execute('RELEASE SAVEPOINT account_mutation')
        else:
            connection.rollback()
        raise


def require_scope(principal, account_id, role_id, *, connection):
    return AccountStore(connection).resolve(principal, account_id, role_id)


class AccountService:
    def __init__(self, connection, credential_store, *, clear_private=None):
        self.connection, self.credentials = connection, credential_store
        self.clear_private = clear_private
        self._listeners = []

    def require_scope(self, principal, account_id, role_id):
        return require_scope(principal, account_id, role_id, connection=self.connection)

    def _user(self, principal):
        if not self.connection.execute('SELECT 1 FROM users WHERE user_id=? AND disabled_at IS NULL',
                                       (principal.user_id,)).fetchone():
            raise AccountNotFoundError()

    def list_accounts(self, principal):
        self._user(principal)
        rows = self.connection.execute(
            'SELECT a.account_id,a.grant_id,a.game,a.channel,a.server,a.provider,a.is_default,g.version,g.state '
            'FROM accounts a JOIN grants g ON g.grant_id=a.grant_id AND g.user_id=a.user_id '
            'WHERE a.user_id=? ORDER BY a.created_at,a.account_id', (principal.user_id,)).fetchall()
        result = []
        keys = ('account_id', 'grant_id', 'game', 'channel', 'server', 'provider', 'is_default', 'version', 'state')
        for row in rows:
            item = dict(zip(keys, row))
            role_fields = ('role_id', 'display_name', 'is_default', 'game_uid') if item['game'] == 'endfield' else ('role_id', 'display_name', 'is_default')
            item['roles'] = [dict(zip(role_fields, r))
                             for r in self.connection.execute(
                                 f"SELECT {','.join(role_fields)} FROM roles WHERE account_id=? AND user_id=?",
                                 (row[0], principal.user_id))]
            if item['state'] == 'active':
                from game_assistant.auth.store import CredentialStoreError
                try:
                    saved = self.credentials.load_grant(principal.user_id,item['grant_id'])
                except CredentialStoreError:
                    # Other providers report an unreadable grant per account query (query_state).
                    if item['provider'] == 'skland':
                        item['state'] = 'credential_unavailable'
                else:
                    # A later login may stop listing a role; the runtime refuses it, so it is not offered.
                    item['roles'] = [role for role in item['roles'] if has_verified_role(saved,
                        self.connection.execute('SELECT game_uid FROM roles WHERE role_id=?',(role['role_id'],)).fetchone()[0],
                        item['server'], item['channel'])]
                    if not item['roles']:
                        item['state'] = 'role_unavailable'
                    if item['provider'] == 'skland':
                        if 'channel' not in saved and not any('channel' in role for role in saved.get('_verified_roles', [])):
                            item['channel'] = 'unknown'
                        parent = saved.get('_parent')
                        item['authorization_source'] = 'passport' if parent else 'manual'
                        if parent:
                            item.update(parent_account_id=parent['account_id'],parent_role_id=parent['role_id'])
            result.append(item)
        return result

    def describe(self, scope, *, active=True):
        self.require_scope(Principal(scope.user_id, False), scope.account_id, scope.role_id)
        row = self.connection.execute(
            'SELECT a.game,a.provider,a.grant_id,g.version,g.state,r.game_uid,a.server,a.channel '
            'FROM accounts a JOIN grants g ON g.grant_id=a.grant_id JOIN roles r ON r.account_id=a.account_id '
            'WHERE a.account_id=? AND r.role_id=? AND a.user_id=?',
            (scope.account_id, scope.role_id, scope.user_id)).fetchone()
        if active and row[4] != 'active':
            raise AccountNotFoundError()
        if active and row[1] == 'skland':
            saved = self.credentials.load_grant(scope.user_id,row[2])
            if not has_verified_role(saved, row[5], row[6], row[7]):
                raise AccountNotFoundError()
        return dict(zip(('game','provider','grant_id','version','state','game_uid','server','channel'), row))

    def snapshot_generation(self, scope, version):
        from .identities import snapshot_generation
        info = self.describe(scope)
        if info['version'] != version:
            raise AccountNotFoundError()
        credentials = self.credentials.load_grant(scope.user_id, info['grant_id'])
        return snapshot_generation(credentials, version)

    def save_verified(self, principal, provider, credentials, *, expected_versions=None):
        """Internal-only: credentials are returned by a verified provider, never body UIDs."""
        self._user(principal)
        credentials = dict(credentials)
        # A fresh authorization never inherits the previous snapshot identity.
        credentials.pop('_snapshot_generation', None)
        game = PROVIDER_GAMES[provider]
        subject_key = {'kuro': 'user_id', 'tajiduo': 'center_uid', 'hypergryph': 'uid', 'skland': 'user_id'}[provider]
        subject = str(credentials.get(subject_key) or '')
        role = str(credentials.get('role_id') or '')
        server = str(credentials.get('server_id') or ('official' if provider == 'tajiduo' else ''))
        if not subject or not role or not server:
            from game_assistant.auth.service import LoginError
            raise LoginError('社区未提供已验证的账号和角色标识', 502)
        if self.connection.in_transaction:
            raise RuntimeError('Account mutations require a dedicated idle connection')
        verified = credentials.get('_verified_roles',credentials.get('roles')) or [
            {'role_id':role,'server_id':server,'nickname':credentials.get('nickname')}]
        if not isinstance(verified,list) or any(not isinstance(item,dict) or not str(item.get('role_id') or '') or
                not str(item.get('server_id') or '') for item in verified):
            from game_assistant.auth.service import LoginError
            raise LoginError('社区角色资料格式不正确',502)
        verified = [{**item, 'channel': role_channel(item, credentials) if game == 'endfield' else 'official'}
                    for item in verified]
        if any(item['channel'] not in CHANNELS or (provider == 'hypergryph' and item['channel'] == 'unknown')
               for item in verified):
            from game_assistant.auth.service import LoginError
            raise LoginError('社区未提供可信的登录渠道',502)
        selected_channels = {item['channel'] for item in verified
                             if str(item['role_id']) == role and str(item['server_id']) == server}
        channel = credentials.get('channel') if game == 'endfield' else 'official'
        if channel is None and len(selected_channels) == 1:
            channel = next(iter(selected_channels))
        if channel not in selected_channels:
            from game_assistant.auth.service import LoginError
            raise LoginError('默认角色的登录渠道不匹配',502)
        credentials = {**credentials, 'channel': channel, '_verified_roles':verified}
        if provider == 'hypergryph':
            credentials['_authorization_id'] = uuid.uuid4().hex
        if not any(str(item['role_id'])==role and str(item['server_id'])==server for item in verified):
            from game_assistant.auth.service import LoginError
            raise LoginError('默认角色不在社区绑定列表中',502)
        with transaction(self.connection):
            if credentials.get('_parent') is not None:
                self.credentials.validate_parent(principal.user_id,credentials['_parent'])
            if expected_versions is not None and self.grant_versions(principal,provider) != expected_versions:
                from game_assistant.auth.service import LoginError
                raise LoginError('授权已改变，请重新连接森空岛',409,'authorization_changed')
            old = self.connection.execute('SELECT grant_id FROM grants WHERE user_id=? AND provider=? AND provider_subject=? ORDER BY created_at LIMIT 1',
                                          (principal.user_id,provider,subject)).fetchone()
            if old:
                grant_id = old[0]
                derived = self._revoke_derived(principal,grant_id) if provider == 'hypergryph' else []
                self.connection.execute("UPDATE grants SET version=version+1,state='pending' WHERE grant_id=?", (grant_id,))
            else:
                derived = []
                grant_id = uuid.uuid4().hex
                self.connection.execute('INSERT INTO grants(grant_id,user_id,provider,provider_subject) VALUES(?,?,?,?)',
                                        (grant_id,principal.user_id,provider,subject))
            version = self.connection.execute('SELECT version FROM grants WHERE grant_id=?', (grant_id,)).fetchone()[0]
            self.credentials.save_grant(principal.user_id,grant_id,credentials,version)
            selected = None
            seen_servers = set()
            for item in verified:
                upstream_role,upstream_server = str(item['role_id']),str(item['server_id'])
                upstream_channel = item['channel']
                account = self.connection.execute('SELECT account_id FROM accounts WHERE user_id=? AND game=? AND channel=? AND server=? AND provider=? AND account_uid=?',
                                                  (principal.user_id,game,upstream_channel,upstream_server,provider,subject)).fetchone()
                account_id = account[0] if account else uuid.uuid4().hex
                if not account:
                    default = not self.connection.execute('SELECT 1 FROM accounts WHERE user_id=? AND game=? AND is_default=1',
                                                           (principal.user_id,game)).fetchone()
                    self.connection.execute('INSERT INTO accounts(account_id,user_id,grant_id,game,channel,server,provider,account_uid,is_default) VALUES(?,?,?,?,?,?,?,?,?)',
                                            (account_id,principal.user_id,grant_id,game,upstream_channel,upstream_server,provider,subject,int(default)))
                else:
                    self.connection.execute('UPDATE accounts SET grant_id=? WHERE account_id=?',(grant_id,account_id))
                role_row = self.connection.execute('SELECT role_id FROM roles WHERE account_id=? AND game_uid=?',(account_id,upstream_role)).fetchone()
                role_id = role_row[0] if role_row else uuid.uuid4().hex
                is_selected = upstream_role==role and upstream_server==server and upstream_channel==channel
                server_key = (upstream_channel, upstream_server)
                default = int(is_selected or server_key not in seen_servers)
                if default:
                    self.connection.execute('UPDATE roles SET is_default=0 WHERE account_id=?',(account_id,))
                if role_row:
                    self.connection.execute('UPDATE roles SET display_name=?,is_default=? WHERE role_id=?',(item.get('nickname'),default,role_id))
                else:
                    self.connection.execute('INSERT INTO roles(role_id,account_id,user_id,game,channel,server,provider,game_uid,display_name,is_default) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                            (role_id,account_id,principal.user_id,game,upstream_channel,upstream_server,provider,upstream_role,item.get('nickname'),default))
                seen_servers.add(server_key)
                if is_selected:
                    selected = account_id,role_id
        self._changed(principal.user_id,grant_id)
        for child in derived:
            self._changed(principal.user_id,child)
            self._cleanup_after_commit(principal,child)
        cleanup_pending = self._cleanup_after_commit(principal,grant_id) if old else False
        account_id,role_id = selected
        return {'ok': True, 'account_id': account_id, 'role_id': role_id, 'grant_id': grant_id, 'version': version,
                'cleanup_pending':cleanup_pending}

    def select_role(self, principal, account_id, role_id):
        self.require_scope(principal,account_id,role_id)
        with transaction(self.connection):
            self.connection.execute('UPDATE roles SET is_default=0 WHERE account_id=? AND user_id=?', (account_id,principal.user_id))
            self.connection.execute('UPDATE roles SET is_default=1 WHERE role_id=? AND account_id=? AND user_id=?', (role_id,account_id,principal.user_id))
        return {'ok': True, 'role_id': role_id}

    def _clear_grant(self, principal, grant_id):
        if self.clear_private is not None:
            for row in self.connection.execute('SELECT a.account_id,r.role_id FROM accounts a JOIN roles r ON r.account_id=a.account_id WHERE a.user_id=? AND a.grant_id=?',
                                               (principal.user_id,grant_id)):
                self.clear_private(self.require_scope(principal,*row))

    def _changed(self, user_id, grant_id):
        for callback in self._listeners:
            callback(user_id,grant_id)

    def grant_versions(self, principal, provider):
        return dict(self.connection.execute('SELECT grant_id,version FROM grants WHERE user_id=? AND provider=?',
                                            (principal.user_id,provider)))

    def _revoke_derived(self, principal, parent_grant):
        from game_assistant.auth.store import CredentialStoreError
        children = []
        for (grant_id,) in self.connection.execute("SELECT grant_id FROM grants WHERE user_id=? AND provider='skland' AND state='active'",
                                                  (principal.user_id,)).fetchall():
            try:
                saved = self.credentials.load_grant(principal.user_id,grant_id)
            except CredentialStoreError:
                continue  # Undecryptable grants already fail closed on every read.
            if saved.get('_parent',{}).get('grant_id') == parent_grant:
                self.connection.execute("UPDATE grants SET version=version+1,state='revoked',encrypted_payload=NULL WHERE user_id=? AND grant_id=?",
                                        (principal.user_id,grant_id))
                children.append(grant_id)
        return children

    def _cleanup_after_commit(self,principal,grant_id):
        try:
            self._clear_grant(principal,grant_id)
            return False
        except Exception:
            # Independent private databases cannot share this SQLite transaction.
            # The grant remains unavailable even if cache cleanup needs a retry.
            with transaction(self.connection):
                self.connection.execute("UPDATE grants SET state=CASE WHEN state='revoked' THEN 'revoked_cleanup_pending' ELSE 'active_cleanup_pending' END WHERE user_id=? AND grant_id=?",
                                        (principal.user_id,grant_id))
            return True

    def revoke(self, principal, account_id):
        self._user(principal)
        row = self.connection.execute('SELECT grant_id FROM accounts WHERE user_id=? AND account_id=?',
                                      (principal.user_id,account_id)).fetchone()
        if row is None:
            raise AccountNotFoundError()
        grant_id = row[0]
        if self.connection.in_transaction:
            raise RuntimeError('Account mutations require a dedicated idle connection')
        with transaction(self.connection):
            derived = self._revoke_derived(principal,grant_id)
            self.connection.execute("UPDATE grants SET version=version+1,state='revoked',encrypted_payload=NULL,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE user_id=? AND grant_id=?",
                                    (principal.user_id,grant_id))
        self._changed(principal.user_id,grant_id)
        for child in derived:
            self._changed(principal.user_id,child)
            self._cleanup_after_commit(principal,child)
        return {'ok': True,'cleanup_pending':self._cleanup_after_commit(principal,grant_id)}
