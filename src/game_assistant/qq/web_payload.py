"""Frozen, credential-free inputs for the real cloud Vue components.

Nothing in this module fetches game data. Missing detail caches remain missing;
the screenshot browser may only consume the exact responses assembled here.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import re
from urllib.parse import quote

from game_assistant.accounts.models import QueryResult
from .assets import safe_public_url
from . import presentation as view


SUPPORTED_COMMANDS = frozenset((
    'overview', 'summary', 'roles', 'stamina', 'exploration', 'combat', 'progress',
    'gacha', 'calendar', 'events', 'recent_events', 'news', 'calabash',
    'activities', 'resources', 'realestate', 'vehicles', 'teams', 'record',
))
DISPLAY_CAPABILITIES = frozenset((
    'account', 'stamina', 'roles', 'exploration', 'combat', 'progress', 'gacha',
    'calabash', 'activities', 'resources', 'realestate', 'vehicles', 'teams', 'record',
))
_SECRET_KEY = re.compile(r'token|cookie|password|secret|credential|authorization|session|device', re.I)
_PRIVATE_KEYS = frozenset(('uid', 'user_id', 'game_uid', 'phone', 'mobile', 'email', 'cred', 'auth', 'headers',
                           'grant_id', 'grant_version',
                           'raw', 'raw_data', 'raw_response', 'debug', 'error', 'error_message'))
_IDENTITY_KEYS = frozenset(('id', 'role_id', 'server_id', 'character_id', 'account_role_id',
                            'account_id', 'item_id', 'pool_id', 'pool_key', 'key', 'subject'))


def display_data(value, key=''):
    """Drop transport secrets and raw diagnostics before a browser sees data."""
    if isinstance(value, dict):
        return {str(k): display_data(v, str(k)) for k, v in value.items()
                if str(k).lower() not in _PRIVATE_KEYS and not _SECRET_KEY.search(str(k))}
    if isinstance(value, (list, tuple)):
        return [display_data(item, key) for item in value if not _private_named_field(item)]
    if isinstance(value, str):
        public_image = safe_public_url(value)
        if public_image:
            return public_image
        value = re.sub(r'(?:https?://|www\.)[^\s<>]+', '[链接未启用]', value, flags=re.I)
        if key in _IDENTITY_KEYS:
            return value
        return re.sub(r'(?<!\d)\d{7,}(?!\d)', '***', value)
    return value


def _private_named_field(item):
    if not isinstance(item, dict) or not any(k in item for k in ('value', 'attribute_value')):
        return False
    label = item.get('name') or item.get('label') or item.get('attribute_name')
    return isinstance(label, str) and bool(re.search(
        r'token|cookie|secret|password|credential|authorization|session|uid|凭据|密码|令牌|密钥', label, re.I))


def _prefix(scope):
    return '/api/accounts/' + quote(scope.account_id, safe='') + '/roles/' + quote(scope.role_id, safe='')


def existing_ledger(private, scope, kind):
    """A screenshot never initializes a missing private database."""
    if private is None:
        return None
    root = getattr(private, 'private_root', None)
    if root is not None:
        from game_assistant.private_data import scope_directory
        if not (scope_directory(root, scope) / kind / 'ledger.sqlite3').is_file():
            return None
    return private.ledger(scope, kind)


class FrozenWebView:
    def __init__(self, service, context, command, game, role_name, now):
        self.service, self.context = service, context
        self.command, self.game, self.role_name = command, game, role_name
        self.now = now.replace(second=0, microsecond=0)
        self.responses = {}

    def respond(self, scope, path, body):
        self.responses[_prefix(scope) + path] = {'status': 200, 'body': body}
        self.service._capture_snapshot(self.context, scope, 'web:' + path,
                                       QueryResult(body, None, 'ok', None))

    def snapshot(self, row, scope, capability):
        cache = self.context['read_cache']
        key = (scope.account_id, scope.role_id, capability)
        if key not in cache:
            cache[key] = self.service.query_service.read(scope, capability)
        result = cache[key]
        self.service._capture_snapshot(self.context, scope, capability, result)
        status = self.service.query_service.status(scope, capability) if hasattr(self.service.query_service, 'status') else {'state': result.state}
        if 'observed_at' in status:
            status = {**status, 'observed_at': self.now.isoformat()}
        old = False
        if result.fetched_at:
            stamp = datetime.fromisoformat(result.fetched_at.replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            old = (self.now - stamp).total_seconds() > self.service.private_poll_seconds * 2
        return {**asdict(result), 'account_id': scope.account_id, 'role_id': scope.role_id,
                'game_id': row['game'], 'capability': capability,
                'stale': bool(result.payload is not None and (old or result.state in ('error', 'auth_expired'))),
                'poll_status': status}

    def capabilities(self, row):
        game, command = row['game'], self.command
        if command == 'overview':
            return {'account', 'stamina', 'gacha'}
        if command == 'summary':
            if game == 'wuthering_waves':
                return {'account', 'stamina', 'progress', 'exploration', 'calabash'}
            return {'account', 'stamina', 'progress', 'stats', 'record'}
        # The account identity is needed by the existing Wuwa detail transports.
        wanted = {'account', command}
        if command == 'teams':
            wanted.add('roles')
        return wanted

    def details(self, row, scope, snapshots):
        private = getattr(self.service.query_service, 'private', None)
        game, command = row['game'], self.command
        if game == 'wuthering_waves':
            if command == 'gacha':
                ledger = existing_ledger(private, scope, 'wuwa_gacha')
                if ledger is not None:
                    self.respond(scope, '/wuwa/gacha?limit=50&offset=0', ledger.read(scope, 50, 0))
            if command == 'roles' and self.role_name:
                entry = next((item for item in view.role_entries(game, view.obj(snapshots.get('roles')).get('payload'), row['provider'])
                              if item.get('name') == self.role_name), None)
                if entry is not None:
                    detail = self.service._role_detail_snapshot(scope, entry.get('role_id'), self.context['detail_cache'])
                    if detail is not None:
                        self.respond(scope, '/wuwa/roles/' + quote(str(entry['role_id']), safe=''),
                                     {'payload': {'character_id': entry['role_id'], 'data': detail.payload},
                                      'fetched_at': detail.fetched_at})
        elif game == 'nte' and command == 'gacha':
            ledger = existing_ledger(private, scope, 'nte')
            if ledger is not None:
                self.respond(scope, '/nte/gacha/summary', ledger.summary(scope))
                self.respond(scope, '/nte/gacha/rules', ledger.rules(scope))
                self.respond(scope, '/nte/gacha/records?pool_id=&offset=0&limit=100', ledger.records(scope, '', 100, 0))
        elif game == 'endfield' and row['provider'] == 'hypergryph' and command == 'gacha':
            ledger = existing_ledger(private, scope, 'endfield_gacha')
            if ledger is not None:
                summary = ledger.summary(scope)
                if hasattr(summary, 'model_dump'):
                    summary = summary.model_dump(mode='json')
                # EndfieldGachaPanel consumes the summary through its snap prop.
                snapshots['gacha'] = {**snapshots.get('gacha', {}), 'payload': summary}
                self.respond(scope, '/endfield/gacha/records?pool_key=&offset=0&limit=50', ledger.records(scope, '', 50, 0))
        elif game == 'endfield' and row['provider'] == 'skland':
            account = snapshots.get('account')
            if account is not None:
                self.respond(scope, '/endfield/skland/card', account)
            cached = private.cached_skland(scope) if private is not None and hasattr(private, 'cached_skland') else {}
            if command == 'summary' and cached.get('attendance') is not None:
                self.respond(scope, '/endfield/skland/attendance', cached['attendance'])
            if command == 'combat' and cached.get('challenge') is not None:
                self.respond(scope, '/endfield/skland/challenges?kind=war', cached['challenge'])
            if command == 'roles' and self.role_name:
                entries = view.rows(view.obj(view.obj(account).get('payload')).get('operators'))
                entry = next((item for item in entries if item.get('name') == self.role_name), None)
                if entry is not None:
                    identity = str(entry.get('id') or entry.get('char_id') or '')
                    detail = cached.get('operators', {}).get(identity)
                    if detail is not None:
                        self.respond(scope, '/endfield/skland/operators/' + quote(identity, safe=''), detail)

    def build(self):
        entries = []
        rows = self.context.get('account_rows', [])
        for scope, _ in self.context['grants']:
            row = next((item for item in rows if item['account_id'] == scope.account_id), None)
            if row is None or self.command in ('calendar', 'events', 'recent_events', 'news'):
                continue
            offered = self.service.query_service.capabilities(scope)
            wanted = self.capabilities(row)
            snapshots = {cap: self.snapshot(row, scope, cap) for cap in offered
                         if cap in wanted and cap in DISPLAY_CAPABILITIES}
            if self.command == 'roles' and self.role_name:
                source = snapshots.get('account') if row['provider'] == 'skland' else snapshots.get('roles')
                roles = view.role_entries(row['game'], view.obj(source).get('payload'), row['provider'])
                if sum(role.get('name') == self.role_name for role in roles) != 1:
                    return None
            self.details(row, scope, snapshots)
            account = {key: row[key] for key in ('account_id', 'game', 'provider', 'state', 'is_default') if key in row}
            account['capabilities'] = [cap for cap in offered if cap in DISPLAY_CAPABILITIES]
            account['roles'] = [{key: role[key] for key in ('role_id', 'display_name', 'is_default') if key in role}
                                for role in row['roles']]
            entries.append({'account': account, 'role': scope.role_id, 'snapshots': snapshots})
        public = deepcopy(self.context.get('public_snapshots', {}))
        if self.service.public is not None:
            for entry in entries:
                game = entry['account']['game']
                for cap in ('news', 'events'):
                    if cap not in public.get(game, {}):
                        from game_assistant.accounts.store import AccountNotFoundError
                        try:
                            snapshot = self.service.public.read(game, cap)
                        except (AccountNotFoundError, ValueError, RuntimeError, OSError):
                            snapshot = QueryResult(None, None, 'error', None)
                        self.service._capture_snapshot(self.context, None, game + ':' + cap, snapshot)
                        public.setdefault(game, {})[cap] = asdict(snapshot)
        if not entries and not public:
            return None
        for snapshots in public.values():
            for snapshot in snapshots.values():
                status = snapshot.get('poll_status')
                if isinstance(status, dict) and 'observed_at' in status:
                    status['observed_at'] = self.now.isoformat()
        payload = {'version': 1, 'command': self.command, 'game': self.game, 'roleName': self.role_name,
                   'now': int(self.now.timestamp() * 1000), 'entries': entries,
                   'publicSnapshots': public, 'responses': self.responses}
        return display_data(payload)


def build_web_payload(service, context, command, game, role_name):
    if command not in SUPPORTED_COMMANDS:
        return None
    return FrozenWebView(service, context, command, game, role_name, service.clock()).build()
