"""Bounded login sessions and one-account-per-game credential lifecycle."""
import asyncio
import hashlib
import logging
import re
import secrets
import time
import uuid
from copy import deepcopy

logger = logging.getLogger(__name__)

from game_assistant.adapters.wuthering_waves.kuro_client import AUTH_EXPIRED_CODES
from game_assistant.auth.providers import WuwaLoginProvider
from game_assistant.auth.store import CredentialStoreError
from game_assistant.models import Capability, FetchResult

GAMES = ('wuthering_waves', 'nte')
FIELDS = {
    'wuthering_waves': {'token': 'wuwa_token', 'user_id': 'wuwa_user_id',
        'token_source': 'wuwa_token_source',
        'b_at': 'wuwa_b_at', 'did': 'wuwa_did', 'dev_code': 'wuwa_dev_code',
        'role_id': 'wuwa_role_id', 'server_id': 'wuwa_server_id'},
    'nte': {'access_token': 'nte_access_token', 'refresh_token': 'nte_refresh_token',
        'device_id': 'nte_device_id', 'role_id': 'nte_role_id'},
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
            from .providers import WuwaLoginProvider, NteLoginProvider
            providers = {'wuthering_waves': WuwaLoginProvider(), 'nte': NteLoginProvider()}
        self.providers = providers
        self._locks = {g: asyncio.Lock() for g in GAMES}
        self._sessions = {}
        self._sms_times = {}
        self._sms_attempts = []
        self._start_times = []
        self._versions = {g: 0 for g in GAMES}
        self._account_generations = {g: 0 for g in GAMES}
        self._errors = {}
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
            if game == 'nte' and not self._accounts[game].get('device_id') and any(
                    self._accounts[game].get(k) for k in ('access_token', 'refresh_token')):
                self._accounts[game]['device_id'] = 'HT' + uuid.uuid4().hex[:14].upper()
                # A record already on disk keeps this id. Tokens that exist only
                # in config.toml stay there until a successful login writes them.
                if game in self._saved:
                    self._saved[game] = deepcopy(self._accounts[game])
                    try:
                        self.store.save(self._saved)
                    except CredentialStoreError:
                        logger.warning("异环设备号未能写入凭据文件")
            self._apply(game)

    def attach(self, registry, snapshots):
        self.registry, self.snapshots = registry, snapshots
        for adapter in registry.all():
            if adapter.game_id in GAMES:
                adapter._auth = self
                self._apply(adapter.game_id)

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
                        from game_assistant.adapters.wuthering_waves.kuro_client import KuroClient
                        adapter._client = (KuroClient(self.settings.wuwa_token,
                                                      did=self.settings.wuwa_did,
                                                      source=self.settings.wuwa_token_source)
                                           if adapter.credentials_configured else None)

    def _configured(self, game):
        account = self._accounts[game]
        if account.get('logged_out'):
            return False
        return bool(account.get('token') and account.get('user_id')) if game == GAMES[0] else bool(
            account.get('access_token') or account.get('refresh_token'))

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
        return {'accounts': accounts}

    async def start(self, game):
        self._game(game)
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
            except Exception:
                logger.warning("无法初始化登录", extra={'game': game}, exc_info=True)
                raise LoginError('无法初始化登录，请检查网络后重试', 502) from None
            sid = secrets.token_urlsafe(32)
            self._sessions[sid] = {'game': game, 'context': context,
                'expires': self.clock() + 600, 'attempts': 0, 'mobile': None, 'sent': False}
            return {'session_id': sid, 'expires_in': 600,
                    'captcha_id': WuwaLoginProvider.captcha_id if game == GAMES[0] else None}

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
        from .providers import AuthError
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
                raise LoginError(error.message) from None
            except Exception:
                logger.warning("短信发送失败", extra={'game': game}, exc_info=True)
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
                self.snapshots.restore_private(game, backup)
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
        from .providers import AuthError
        async with self._locks[game]:
            session = self._session(game, sid)
            if not session['sent'] or session['mobile'] != mobile:
                raise LoginError('请先向该手机号发送验证码')
            session['attempts'] += 1
            try:
                account = await self.providers[game].login(session['context'], mobile, code)
            except AuthError as error:
                raise LoginError(error.message) from None
            except Exception:
                logger.warning("登录失败", extra={'game': game}, exc_info=True)
                raise LoginError('登录失败，请检查网络后重试', 502) from None
            if session['expires'] <= self.clock():
                raise LoginError('登录会话已过期，请重新开始登录', 410)
            account['_updated_at'] = self.clock()
            self._persist(game, account, clear_snapshots=True)
            self._sessions.pop(sid, None)
            return {'ok': True, 'account': self.status()['accounts'][game]}

    async def logout(self, game):
        self._game(game)
        async with self._locks[game]:
            self._persist(game, {'logged_out': True}, clear_snapshots=True)
            self._sessions = {sid: s for sid, s in self._sessions.items() if s['game'] != game}
            return {'ok': True, 'account': self.status()['accounts'][game]}

    async def _renew(self, game):
        from .providers import AuthError
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
        except Exception:
            logger.warning("登录状态刷新失败", extra={'game': game}, exc_info=True)
            raise LoginError('登录状态刷新失败，请稍后重试', 502) from None

    async def fetch(self, game, capability, action):
        # Public NTE feeds remain available without a community session.
        if game == 'nte' and capability in (Capability.ANNOUNCEMENT, Capability.EVENTS, Capability.TEAMS):
            return await action()
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
                if game == GAMES[0]:
                    # RoleBox uses a renewable b-at ticket. Base account/widget
                    # HTTP auth errors concern the login token and require login.
                    rolebox = capability in (Capability.ROLES, Capability.EXPLORATION, Capability.CALABASH,
                                             Capability.STAMINA, Capability.PROGRESS,
                                             Capability.COMBAT, Capability.ACTIVITIES, Capability.RESOURCES) or result.error_source == 'rolebox'
                    invalid = result.error_code in (10900, 10901, 10903) or (
                        rolebox and result.error_code in (401, 403))
                else:
                    invalid = result.error_code in (401, 402, 403)
                can_renew = bool(account.get('token') and account.get('role_id')) if game == GAMES[0] else bool(account.get('refresh_token'))
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
