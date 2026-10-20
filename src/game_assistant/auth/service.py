"""Bounded login sessions and one-account-per-game credential lifecycle."""
import asyncio
import hashlib
import logging
import re
import secrets
import time
import uuid
from copy import deepcopy

from game_assistant.adapters.wuthering_waves.kuro_client import AUTH_EXPIRED_CODES, KuroClient
from game_assistant.auth.providers import AuthError, EndfieldLoginProvider, NteLoginProvider, WuwaLoginProvider, PUBLIC_IP_LOOKUP_ERROR
from game_assistant.auth.store import CredentialStoreError
from game_assistant.models import Capability, FetchResult

logger = logging.getLogger(__name__)

GAMES = ('wuthering_waves', 'nte', 'endfield')
FIELDS = {
    'wuthering_waves': {'token': 'wuwa_token', 'user_id': 'wuwa_user_id',
        'token_source': 'wuwa_token_source',
        'b_at': 'wuwa_b_at', 'did': 'wuwa_did', 'dev_code': 'wuwa_dev_code',
        'role_id': 'wuwa_role_id', 'server_id': 'wuwa_server_id'},
    'nte': {'access_token': 'nte_access_token', 'refresh_token': 'nte_refresh_token',
        'device_id': 'nte_device_id', 'role_id': 'nte_role_id'},
    'endfield': {'hg_token': 'endfield_hg_token', 'uid': 'endfield_uid',
        'role_id': 'endfield_role_id', 'server_id': 'endfield_server_id', 'channel': 'endfield_channel'},
}
# Public feeds remain available without a community session.
PUBLIC_CAPABILITIES = {
    'wuthering_waves': (Capability.ANNOUNCEMENT, Capability.EVENTS),
    'nte': (Capability.ANNOUNCEMENT, Capability.EVENTS, Capability.TEAMS),
    'endfield': (Capability.ANNOUNCEMENT, Capability.NEWS, Capability.EVENTS),
}


class LoginError(Exception):
    def __init__(self, message, status=400, error_kind=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.error_kind = error_kind


class LoginService:
    def __init__(self, settings, store, providers=None, clock=time.time):
        self.settings, self.store, self.clock = settings, store, clock
        if providers is None:
            providers = {'wuthering_waves': WuwaLoginProvider(public_ip_url=settings.wuwa_login_public_ip_url), 'nte': NteLoginProvider(),
                         'endfield': EndfieldLoginProvider()}
        self.providers = providers
        self._locks = {g: asyncio.Lock() for g in GAMES}
        self._sessions = {}
        self._sms_times = {}
        self._sms_attempts = []
        self._start_times = []
        self._versions = {g: 0 for g in GAMES}
        self._account_generations = {g: 0 for g in GAMES}
        self._errors = {}
        self._account_listeners = []
        self.registry = self.snapshots = None
        try:
            self._saved = self.store.load()
        except CredentialStoreError as error:
            # Fail closed; never silently revive legacy credentials after corruption.
            self._saved = {g: {'logged_out': True} for g in GAMES}
            self._errors = {g: error.args[0] for g in GAMES}
        self._accounts = {}
        for game in GAMES:
            self._accounts[game] = deepcopy(self._saved.get(game, {
                key: getattr(settings, field, '') for key, field in FIELDS[game].items()}))
            if game == 'wuthering_waves' and game in self._saved:
                # Credentials written by the first SMS-login release had no source.
                # sdkLogin returns an APP token; sending it as h5 yields code 220.
                self._accounts[game].setdefault('token_source', 'ios')
            if game == 'endfield':
                self._accounts[game].setdefault('channel', 'official')
            if game == 'nte' and not self._accounts[game].get('device_id') and any(
                    self._accounts[game].get(k) for k in ('access_token', 'refresh_token')):
                self._accounts[game]['device_id'] = 'HT' + uuid.uuid4().hex[:14].upper()
            self._apply(game)

    def attach(self, registry, snapshots):
        self.registry, self.snapshots = registry, snapshots
        for adapter in registry.all():
            if adapter.game_id in GAMES:
                adapter._auth = self
                self._apply(adapter.game_id)

    def add_account_listener(self, callback):
        """Awaited as callback(game) after a login or logout replaces the account (not on renewal)."""
        self._account_listeners.append(callback)

    async def _notify_account_change(self, game):
        for callback in self._account_listeners:
            try:
                await callback(game)
            except Exception as exc:
                logger.warning("账号变更通知失败 (%s)", type(exc).__name__, extra={'game': game})

    def _game(self, game):
        if game not in GAMES:
            raise LoginError('该游戏不支持社区登录', 404)

    def version(self, game):
        return self._versions.get(game, 0)

    def account_generation(self, game):
        """Account replacement/logout epoch, unchanged by same-account renewal."""
        return self._account_generations.get(game, 0)

    def _apply(self, game):
        account = self._accounts[game]
        for key, field in FIELDS[game].items():
            setattr(self.settings, field, '' if account.get('logged_out') else str(account.get(key) or ''))
        if self.registry:
            for adapter in self.registry.all():
                if adapter.game_id == game:
                    adapter.credentials_configured = self._configured(game)
                    if game == 'wuthering_waves':
                        adapter._client = (KuroClient(self.settings.wuwa_token,
                                                      did=self.settings.wuwa_did,
                                                      source=self.settings.wuwa_token_source)
                                           if adapter.credentials_configured else None)

    def _configured(self, game):
        account = self._accounts[game]
        if account.get('logged_out'):
            return False
        if game == 'wuthering_waves':
            return bool(account.get('token') and account.get('user_id'))
        if game == 'nte':
            return bool(account.get('access_token') or account.get('refresh_token'))
        return bool(account.get('hg_token') and account.get('role_id'))

    def status(self):
        accounts = {}
        for game in GAMES:
            configured = self._configured(game)
            account = self._accounts[game]
            source = 'saved' if game in self._saved and configured else 'config' if configured else 'none'
            state = ('expired' if self._errors.get(game) else
                     'connected' if source == 'saved' else 'configured' if configured else 'unconfigured')
            accounts[game] = {'configured': configured, 'source': source, 'state': state,
                              'nickname': account.get('nickname', ''),
                              'message': self._errors.get(game, '')}
            if game == 'endfield':
                channel = account.get('channel') or 'official'
                accounts[game].update(channel=channel,
                    channel_name={'official': '官服', 'bilibili': 'B服'}.get(channel, '渠道未提供'))
        return {'accounts': accounts}

    async def start(self, game, *, channel='official'):
        self._game(game)
        if channel not in ('official', 'bilibili') or (game != 'endfield' and channel != 'official'):
            raise LoginError('该游戏不支持所选登录渠道')
        async with self._locks[game]:
            now = self.clock()
            self._start_times = [t for t in self._start_times if now - t < 60]
            if len(self._start_times) >= 10:
                raise LoginError('操作过于频繁，请一分钟后重试', 429)
            self._start_times.append(now)
            # One live session per game; invalidating it does not log out an existing account.
            self._sessions = {sid: s for sid, s in self._sessions.items()
                              if s['game'] != game and s['expires'] > now}
            try:
                context = await self.providers[game].start_context()
            except Exception as exc:
                logger.warning("无法初始化登录 (%s)", type(exc).__name__, extra={'game': game})
                # Only this project-generated fixed error is exposed, never arbitrary provider text.
                message = (PUBLIC_IP_LOOKUP_ERROR if isinstance(exc, AuthError) and exc.message == PUBLIC_IP_LOOKUP_ERROR
                           else '无法初始化登录，请检查网络后重试')
                raise LoginError(message, 502) from None
            sid = secrets.token_urlsafe(32)
            if game == 'endfield':
                context = {**context, 'channel': channel}
            self._sessions[sid] = {'game': game, 'context': context,
                'expires': self.clock() + 600, 'attempts': 0, 'mobile': None, 'sent': False}
            return {'session_id': sid, 'expires_in': 600,
                    'captcha_id': WuwaLoginProvider.captcha_id if game == 'wuthering_waves' else None}

    def _session(self, game, sid):
        session = self._sessions.get(sid)
        if not session or session['game'] != game or session['expires'] <= self.clock() or session['attempts'] >= 5:
            raise LoginError('登录会话已过期，请重新开始登录', 410)
        return session

    @staticmethod
    def _mobile(mobile):
        if not re.fullmatch(r'1[3-9]\d{9}', mobile):
            raise LoginError('请输入正确的 11 位手机号')

    async def sms(self, game, sid, mobile, captcha=None):
        self._game(game)
        self._mobile(mobile)
        async with self._locks[game]:
            session = self._session(game, sid)
            if session['mobile'] and session['mobile'] != mobile:
                raise LoginError('手机号已改变，请重新开始登录')
            now = self.clock()
            key = (game, hashlib.sha256(mobile.encode()).hexdigest())
            self._sms_times = {k: t for k, t in self._sms_times.items() if now - t < 60}
            self._sms_attempts = [t for t in self._sms_attempts if now - t < 600]
            if key in self._sms_times or len(self._sms_attempts) >= 5:
                raise LoginError('短信发送过于频繁，请稍后重试', 429)
            # Reserve before the network request; a timeout may still deliver an SMS.
            self._sms_times[key] = now
            self._sms_attempts.append(now)
            session['mobile'] = mobile
            try:
                await self.providers[game].send_sms(session['context'], mobile, captcha)
            except AuthError as error:
                raise LoginError(error.message, 429 if error.code == 429 else 400) from None
            except Exception as exc:
                logger.warning("短信发送失败 (%s)", type(exc).__name__, extra={'game': game})
                raise LoginError('短信发送失败，请稍后重试', 502) from None
            session['sent'] = True
            return {'ok': True, 'retry_after': 60}

    def _persist(self, game, account, clear_snapshots=False):
        accounts = deepcopy(self._saved)
        accounts[game] = account
        backup = None
        if clear_snapshots and self.snapshots:
            try:
                backup = self.snapshots.export_private(game)
                self.snapshots.clear_private(game)
            except Exception as error:
                logger.warning("旧账号快照清理失败 (%s)", type(error).__name__)
                raise LoginError('旧账号快照清理失败，原登录状态已保留，请稍后重试', 500) from None
        try:
            self.store.save(accounts)
        except CredentialStoreError as error:
            if backup is not None:
                try:
                    self.snapshots.restore_private(game, backup)
                except Exception as restore_error:
                    logger.warning("旧账号快照恢复失败 (%s)", type(restore_error).__name__)
                    raise LoginError(f'{error}；旧账号快照未能恢复，请重新刷新数据', 500) from None
            raise LoginError(str(error), 500) from None
        self._saved = accounts
        self._accounts[game] = account
        self._errors.pop(game, None)
        self._versions[game] += 1
        if clear_snapshots:
            self._account_generations[game] += 1
        self._apply(game)

    async def login(self, game, sid, mobile, code):
        self._game(game)
        self._mobile(mobile)
        if not re.fullmatch(r'\d{4,8}', code):
            raise LoginError('请输入 4 至 8 位短信验证码')
        async with self._locks[game]:
            session = self._session(game, sid)
            if not session['sent'] or session['mobile'] != mobile:
                raise LoginError('请先向该手机号发送验证码')
            session['attempts'] += 1
            try:
                account = await self.providers[game].login(session['context'], mobile, code)
            except AuthError as error:
                raise LoginError(error.message, 429 if error.code == 429 else 400) from None
            except Exception as exc:
                logger.warning("登录失败 (%s)", type(exc).__name__, extra={'game': game})
                raise LoginError('登录失败，请检查网络后重试', 502) from None
            if session['expires'] <= self.clock():
                raise LoginError('登录会话已过期，请重新开始登录', 410)
            account['_updated_at'] = self.clock()
            self._persist(game, account, clear_snapshots=True)
            self._sessions.pop(sid, None)
            result = {'ok': True, 'account': self.status()['accounts'][game]}
        # Outside the game lock: a listener may wait for its own in-flight requests.
        await self._notify_account_change(game)
        return result

    async def logout(self, game):
        self._game(game)
        async with self._locks[game]:
            self._persist(game, {'logged_out': True}, clear_snapshots=True)
            self._sessions = {sid: s for sid, s in self._sessions.items() if s['game'] != game}
            result = {'ok': True, 'account': self.status()['accounts'][game]}
        await self._notify_account_change(game)
        return result

    async def _renew(self, game):
        try:
            updated = await self.providers[game].renew(deepcopy(self._accounts[game]))
            updated['_updated_at'] = self.clock()
            self._persist(game, updated)
        except AuthError as error:
            if error.code in AUTH_EXPIRED_CODES:
                self._errors[game] = '登录已失效，请重新登录'
            kind = ('auth_expired' if error.code in AUTH_EXPIRED_CODES
                    else 'source_error')
            raise LoginError(error.message, error_kind=kind) from None
        except LoginError:
            raise
        except Exception as exc:
            logger.warning("登录状态刷新失败 (%s)", type(exc).__name__, extra={'game': game})
            raise LoginError('登录状态刷新失败，请稍后重试', 502) from None

    async def fetch(self, game, capability, action):
        if capability in PUBLIC_CAPABILITIES.get(game, ()):
            return await action()
        if game == 'endfield':
            return await self._fetch_without_renewal(game, action)
        async with self._locks[game]:
            account = self._accounts[game]
            renewed = False
            try:
                if game == 'nte' and account.get('refresh_token') and (
                    not account.get('access_token') or
                    self.clock() - account.get('_updated_at', self.clock()) >= 3600):
                    await self._renew(game)
                    renewed = True
                result = await action()
                if game == 'wuthering_waves':
                    # RoleBox uses a renewable b-at ticket. Base account/widget
                    # HTTP auth errors concern the login token and require login.
                    rolebox = capability in (Capability.ROLES, Capability.EXPLORATION, Capability.CALABASH,
                                             Capability.STAMINA, Capability.PROGRESS,
                                             Capability.COMBAT, Capability.ACTIVITIES, Capability.RESOURCES) or result.error_source == 'rolebox'
                    invalid = result.error_code in (10900, 10901, 10903) or (
                        rolebox and result.error_code in (401, 403))
                else:
                    invalid = result.error_code in (401, 402, 403)
                can_renew = bool(account.get('token') and account.get('role_id')) if game == 'wuthering_waves' else bool(account.get('refresh_token'))
                if not result.ok and invalid and can_renew and not renewed:
                    await self._renew(game)
                    result = await action()
                if not result.ok and result.error_code in AUTH_EXPIRED_CODES:
                    self._errors[game] = '登录已失效，请重新登录'
                    result.error_kind = 'auth_expired'
                elif result.ok:
                    self._errors.pop(game, None)
                result.credential_version = self.version(game)
                return result
            except LoginError as error:
                return FetchResult(ok=False, error=error.message, error_kind=error.error_kind or 'source_error',
                                   credential_version=self.version(game))

    async def _fetch_without_renewal(self, game, action):
        # 终末地通行证 token 没有续期接口，无需持锁轮换凭据；寻访同步翻页较久也不会阻塞登录和退出。
        # 期间若换了账号，调度器按 credential_version 与 account_generation 丢弃这次结果。
        version = self.version(game)
        result = await action()
        if version != self.version(game):
            pass  # 旧账号的结果不能改写新账号的登录状态
        elif result.error_kind == 'auth_expired':
            self._errors[game] = '登录已失效，请重新登录'
        elif result.ok:
            self._errors.pop(game, None)
        result.credential_version = version
        return result


class _EphemeralStore:
    """Explicit empty context; never falls back to a local credential file."""
    def load(self):
        return {game: {'logged_out': True} for game in GAMES}

    def save(self, accounts):
        pass


class ScopedLoginService:
    """Cloud website-owned login sessions and versioned grant renewal.

    Protocol and input validation reuse the local login service. Mutable account
    state lives in a separate context for each website user and provider.
    """
    provider_games = {'kuro': 'wuthering_waves', 'tajiduo': 'nte', 'hypergryph': 'endfield'}
    aliases = {'wuthering_waves': 'kuro', 'nte': 'tajiduo', 'endfield': 'hypergryph'}

    def __init__(self, accounts, *, providers=None, clock=time.time, public_ip_url='https://api.ipify.org'):
        self.accounts, self.clock = accounts, clock
        accounts.login = self
        self.providers = providers if providers is not None else {
            'kuro': WuwaLoginProvider(include_roles=True, public_ip_url=public_ip_url), 'tajiduo': NteLoginProvider(include_roles=True), 'hypergryph': EndfieldLoginProvider()}
        self._contexts, self._sessions, self._grant_locks = {}, {}, {}
        self._skland_attempts = {}
        accounts._listeners.append(self._invalidate)

    def provider(self, value):
        provider = self.aliases.get(value,value)
        if provider not in self.provider_games or provider not in self.providers:
            raise LoginError('该社区不支持短信登录',404)
        return provider

    def _context(self, principal, provider):
        self.accounts._user(principal)
        key = (principal.user_id,provider)
        if key not in self._contexts:
            from game_assistant.config import Settings
            self._contexts[key] = LoginService(Settings.model_construct(), _EphemeralStore(),
                providers={self.provider_games[provider]: self.providers[provider]}, clock=self.clock)
        return self._contexts[key]

    def _owned(self, principal, provider, sid):
        self.accounts._user(principal)
        record = self._sessions.get(sid)
        if not record or record[:2] != (principal.user_id,provider):
            raise LoginError('登录会话不存在',404)
        context = self._context(principal,provider)
        context._session(self.provider_games[provider],sid)
        return context

    async def start(self, principal, provider, *, channel='official'):
        provider = self.provider(provider)
        context = self._context(principal,provider)
        result = await context.start(self.provider_games[provider], channel=channel)
        # Drop expired and superseded ownership entries with their contexts.
        self._sessions = {sid: owner for sid,owner in self._sessions.items()
                          if sid in self._contexts[owner[:2]]._sessions}
        self._sessions[result['session_id']] = (principal.user_id,provider)
        return result

    async def sms(self, principal, provider, sid, mobile, captcha=None):
        provider = self.provider(provider)
        context = self._owned(principal,provider,sid)
        return await context.sms(self.provider_games[provider],sid,mobile,captcha)

    async def login(self, principal, provider, sid, mobile, code):
        provider = self.provider(provider)
        context = self._owned(principal,provider,sid)
        game = self.provider_games[provider]
        await context.login(game,sid,mobile,code)
        try:
            # A revoke while awaiting the upstream must also cancel this login.
            if self._sessions.get(sid) != (principal.user_id,provider):
                raise LoginError('登录会话已失效',410)
            self._sessions.pop(sid,None)
            credentials = deepcopy(context._accounts[game])
            return self.accounts.save_verified(principal,provider,credentials)
        except CredentialStoreError:
            raise LoginError('授权凭据保存失败，原授权已保留',500) from None
        finally:
            # The completed protocol context is never the grant credential cache.
            context._accounts[game] = {'logged_out': True}
            context._saved = _EphemeralStore().load()
            context._apply(game)

    def _invalidate(self, user_id, grant_id):
        row = self.accounts.connection.execute('SELECT provider FROM grants WHERE user_id=? AND grant_id=?',
                                                (user_id,grant_id)).fetchone()
        if row:
            key = (user_id,row[0])
            for sid,owner in list(self._sessions.items()):
                if owner == key:
                    self._sessions.pop(sid,None)
            context = self._contexts.get(key)
            if context:
                context._sessions.clear()

    async def renew(self, principal, grant_id, *, role_id=None, server_id=None):
        from game_assistant.accounts.service import transaction
        self.accounts._user(principal)
        lock = self._grant_locks.setdefault((principal.user_id,grant_id),asyncio.Lock())
        async with lock:
            row = self.accounts.connection.execute("SELECT provider,version FROM grants WHERE user_id=? AND grant_id=? AND state='active'",
                                                    (principal.user_id,grant_id)).fetchone()
            if row is None:
                raise LoginError('授权已失效，请重新授权',404,'auth_expired')
            provider,version = row
            if provider not in self.providers:
                raise LoginError('该社区不支持续期',400,'auth_expired')
            try:
                credentials = self.accounts.credentials.load_grant(principal.user_id,grant_id)
                previous = deepcopy(credentials)
                if role_id is not None:
                    if not any(str(role.get('role_id'))==role_id and str(role.get('server_id'))==server_id
                               for role in credentials.get('_verified_roles',[])):
                        raise LoginError('该角色不在授权绑定列表中',404,'auth_expired')
                    credentials.update(role_id=role_id,server_id=server_id)
                updated = await self.providers[provider].renew(deepcopy(credentials))
                if provider == 'hypergryph':
                    if str(updated.get('uid')) != str(credentials.get('uid')):
                        raise LoginError('来源账号已改变，请重新登录',409,'auth_expired')
                    updated['_verified_roles'] = credentials['_verified_roles']
                    if credentials.get('_authorization_id'):
                        updated['_authorization_id'] = credentials['_authorization_id']
                updated['_updated_at'] = self.clock()
                from game_assistant.accounts.identities import renewed_snapshot_generation
                updated['_snapshot_generation'] = renewed_snapshot_generation(previous, updated, version)
                sealed = self.accounts.credentials.seal_grant(principal.user_id,grant_id,updated,version+1)
                with transaction(self.accounts.connection):
                    cursor = self.accounts.connection.execute(
                        "UPDATE grants SET version=version+1,encrypted_payload=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                        "WHERE user_id=? AND grant_id=? AND version=? AND state='active' "
                        'AND EXISTS(SELECT 1 FROM users WHERE user_id=? AND disabled_at IS NULL)',
                        (sealed,principal.user_id,grant_id,version,principal.user_id))
                    if cursor.rowcount != 1:
                        raise LoginError('授权已改变，旧续期已丢弃',409,'auth_expired')
                return updated,version+1
            except LoginError:
                raise
            except AuthError as error:
                raise LoginError(error.message,502,'auth_expired' if error.code in AUTH_EXPIRED_CODES else 'source_error') from None
            except CredentialStoreError:
                raise LoginError('授权凭据不可用，请重新授权',500,'auth_expired') from None
            except Exception:
                raise LoginError('授权续期失败，请稍后重试',502,'source_error') from None

    async def connect_skland(self, principal, cred, device_id=''):
        from game_assistant.adapters.endfield.skland_client import SklandClient, SklandError
        from game_assistant.adapters.endfield.skland_parse import parse_roles,parse_user_id
        self.accounts._user(principal)
        if not isinstance(cred,str) or not 1 <= len(cred.strip()) <= 4096 or any(ord(c)<32 for c in cred):
            raise LoginError('请输入有效的森空岛凭据')
        if not isinstance(device_id,str) or len(device_id)>512 or any(ord(c)<32 for c in device_id):
            raise LoginError('设备标识格式不正确')
        try:
            client = SklandClient()
            token = await client.refresh(cred.strip())
            roles = parse_roles(await client.binding(cred.strip(),token,device_id))
            user_id = parse_user_id(await client.user(cred.strip(),token,device_id))
            if not user_id or not roles:
                raise LoginError('森空岛未提供已验证的国服角色',502)
            role = roles[0]
            return self.accounts.save_verified(principal,'skland',{'cred':cred.strip(),'device_id':device_id,
                'user_id':user_id,'role_id':role['role_id'],'server_id':role['server_id'],
                'channel':role.get('channel', 'unknown'),
                'nickname':role.get('nickname',''),'roles':roles,'_updated_at':self.clock()})
        except LoginError:
            raise
        except (SklandError,CredentialStoreError,ValueError,TypeError,KeyError):
            raise LoginError('森空岛授权验证失败，原授权已保留',502) from None

    async def _exchange_skland(self, credentials, role_id, server_id):
        from game_assistant.adapters.endfield.hypergryph import HypergryphClient, EndfieldError
        from game_assistant.adapters.endfield.skland_client import SklandClient
        from game_assistant.adapters.endfield.skland_parse import parse_roles, parse_user_id
        try:
            async with HypergryphClient() as passport:
                code = await passport.skland_code(credentials['hg_token'])
            client = SklandClient()
            cred = await client.cred_by_code(code)
            token = await client.refresh(cred)
            roles = parse_roles(await client.binding(cred,token,''))
            user_id = parse_user_id(await client.user(cred,token,''))
            channel = credentials.get('channel') or 'official'
            candidates = [role for role in roles
                          if (role['role_id'],role['server_id']) == (role_id,server_id)
                          and role.get('channel', 'unknown') == channel
                          and (not role.get('uid') or str(role['uid']) == str(credentials.get('uid')))]
            selected = {**candidates[0], 'channel': channel} if len(candidates) == 1 else None
            if selected is None:
                raise LoginError('森空岛绑定角色与所选鹰角角色不匹配，请使用手动授权并确认角色',409,'skland_role_mismatch')
            if not user_id:
                raise ValueError('missing verified user')
            # A derived authorization covers only the verified parent role and server.
            return {'cred':cred,'user_id':user_id,'role_id':role_id,'server_id':server_id,
                    'channel':channel,
                    'device_id':'','roles':[selected],'_verified_roles':[selected],
                    'nickname':selected.get('nickname',''),'_updated_at':self.clock()}
        except LoginError:
            raise
        except EndfieldError as error:
            raise LoginError('鹰角授权已失效，请重新登录' if error.expired else '森空岛连接失败，原授权已保留',
                             401 if error.expired else 502,'auth_expired' if error.expired else 'source_error') from None
        except Exception:
            raise LoginError('森空岛连接失败，原授权已保留，请稍后重试或使用手动授权',502,'source_error') from None

    async def connect_skland_passport(self, principal, account_id, role_id):
        from game_assistant.accounts.store import AccountNotFoundError
        scope = self.accounts.require_scope(principal,account_id,role_id)
        info = self.accounts.describe(scope)
        if info['provider'] != 'hypergryph':
            raise AccountNotFoundError()
        key = (principal.user_id,'skland-passport:'+info['grant_id'])
        lock = self._grant_locks.setdefault(key,asyncio.Lock())
        if lock.locked():
            raise LoginError('正在连接森空岛，请稍后重试',429)
        try:
            async with lock:
                return await self._connect_skland_passport(principal,account_id,role_id)
        finally:
            self._grant_locks.pop(key,None)

    async def _connect_skland_passport(self, principal, account_id, role_id):
        from game_assistant.accounts.store import AccountNotFoundError
        scope = self.accounts.require_scope(principal,account_id,role_id)
        info = self.accounts.describe(scope)
        if info['provider'] != 'hypergryph':
            raise AccountNotFoundError()
        credentials = self.accounts.credentials.load_grant(principal.user_id,info['grant_id'])
        from game_assistant.accounts.identities import has_verified_role
        subject = str(credentials.get('uid') or '')
        if not subject or not credentials.get('hg_token') or not has_verified_role(
                credentials, info['game_uid'], info['server'], info['channel']):
            raise AccountNotFoundError()
        # Website-user budget is bounded and shared across source grants.
        now = self.clock()
        self._skland_attempts = {user:times for user,times in self._skland_attempts.items()
                                if times and now-times[-1] < 60}
        attempts = [t for t in self._skland_attempts.get(principal.user_id,[]) if now-t < 60]
        if len(attempts) >= 10:
            raise LoginError('操作过于频繁，请一分钟后重试',429)
        self._skland_attempts[principal.user_id] = [*attempts,now]
        parent = dict(grant_id=info['grant_id'],account_id=account_id,role_id=role_id,
                      subject=subject,game_uid=info['game_uid'],server=info['server'],
                      channel=info['channel'],
                      authorization_id=credentials.get('_authorization_id') or 'legacy:'+info['grant_id'])
        versions = self.accounts.grant_versions(principal,'skland')
        updated = await self._exchange_skland(credentials,info['game_uid'],info['server'])
        try:
            # Synchronous validation and save occur in one SQLite transaction; no await between them.
            self.accounts.credentials.validate_parent(principal.user_id,parent)
            return self.accounts.save_verified(principal,'skland',{**updated,'_parent':parent},expected_versions=versions)
        except CredentialStoreError:
            raise LoginError('来源授权已改变或不可用，请重新连接森空岛',409,'authorization_changed') from None

    async def renew_skland(self, principal, grant_id, *, expected_version, role_id, server_id):
        from game_assistant.accounts.service import transaction
        self.accounts._user(principal)
        lock = self._grant_locks.setdefault((principal.user_id,grant_id),asyncio.Lock())
        async with lock:
            row = self.accounts.connection.execute("SELECT provider,version FROM grants WHERE user_id=? AND grant_id=? AND state='active'",
                                                    (principal.user_id,grant_id)).fetchone()
            if row != ('skland',expected_version):
                raise LoginError('授权已改变，请重新连接森空岛',409,'auth_expired')
            try:
                saved = self.accounts.credentials.load_grant(principal.user_id,grant_id)
                parent = saved.get('_parent')
                if not parent or (parent['game_uid'],parent['server']) != (role_id,server_id):
                    raise LoginError('请使用手动凭据重新授权森空岛',401,'auth_expired')
                source = self.accounts.credentials.validate_parent(principal.user_id,parent)
                updated = await self._exchange_skland(source,role_id,server_id)
                if updated['user_id'] != saved['user_id']:
                    raise LoginError('森空岛账号已改变，请重新连接或使用手动授权',409,'auth_expired')
                updated['_parent'] = parent
                from game_assistant.accounts.identities import renewed_snapshot_generation
                updated['_snapshot_generation'] = renewed_snapshot_generation(saved, updated, expected_version)
                sealed = self.accounts.credentials.seal_grant(principal.user_id,grant_id,updated,expected_version+1)
                with transaction(self.accounts.connection):
                    self.accounts.credentials.validate_parent(principal.user_id,parent)
                    cursor = self.accounts.connection.execute(
                        "UPDATE grants SET version=version+1,encrypted_payload=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                        "WHERE user_id=? AND grant_id=? AND provider='skland' AND version=? AND state='active'",
                        (sealed,principal.user_id,grant_id,expected_version))
                    if cursor.rowcount != 1:
                        raise LoginError('授权已改变，旧续期已丢弃',409,'auth_expired')
                return updated,expected_version+1
            except CredentialStoreError:
                raise LoginError('来源授权已失效，请重新连接森空岛',409,'auth_expired') from None
