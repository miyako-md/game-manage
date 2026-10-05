"""Ephemeral Bilibili login sessions; existing accounts survive unsuccessful work."""
from __future__ import annotations

import asyncio
import hashlib
import math
import re
import secrets
import time
from dataclasses import dataclass, field

from .bilibili_provider import BilibiliLoginProvider, BilibiliProtocolError, VerifiedBilibiliAccount, normalize_cookie_input
from .store import CredentialStoreError
from game_assistant.sources.bilibili_service import BilibiliSaveBusy

SESSION_TTL, QR_TTL, CAPTCHA_TTL, CANDIDATE_TTL = 600, 180, 120, 120
TERMINAL_TTL, MAX_RECORDS, MAX_ATTEMPTS, START_LIMIT = 60, 16, 5, 10
SMS_COOLDOWN, SMS_WINDOW, SMS_LIMIT, POLL_INTERVAL, ACTION_TIMEOUT = 60, 600, 5, 3, 60
MESSAGES = {
    'SESSION_EXPIRED': '登录会话已失效，请重新开始', 'BUSY': '登录请求正在处理，请稍后重试',
    'MODE_MISMATCH': '登录方式不匹配，请重新开始', 'ACCOUNT_CHANGED': '账号状态已改变，请重新开始',
    'CAPTCHA_REQUIRED': '请先完成人工验证', 'INVALID_INPUT': '登录参数不正确，请检查输入',
    'RATE_LIMITED': '请求过于频繁，请稍后重试', 'UPSTREAM_RESTRICTED': 'B站限制了本次访问，请稍后重试',
    'UPSTREAM_UNAVAILABLE': '无法连接B站登录服务，请稍后重试', 'UPSTREAM_REJECTED': '登录未通过，请检查输入并重新验证',
    'UNSUPPORTED_RESPONSE': 'B站登录响应暂不兼容，请使用其他方式或稍后重试',
    'SECURITY_VERIFICATION_REQUIRED': 'B站要求额外安全验证，请自行在官方登录页完成后重新登录',
    'INVALID_CREDENTIALS': '未取得有效的B站登录状态，原账号已保留',
    'SOURCE_UNCONFIGURED': '尚未配置B站资讯来源', 'STORAGE_ERROR': '登录状态保存失败，原账号已保留',
    'COLLECTION_BUSY': '资讯采集正在运行，请稍后重试保存', 'SMS_REQUIRED': '请先向当前手机号发送验证码',
}


class BilibiliLoginError(Exception):
    def __init__(self, detail, status=400, error_code='INVALID_INPUT', state=None, retry_after=None):
        self.detail, self.message, self.status = detail, detail, status
        self.error_code, self.state, self.retry_after = error_code, state, retry_after
        super().__init__(detail)


def fail(code, status=400, **kwargs):
    return BilibiliLoginError(MESSAGES.get(code, 'B站登录失败，原账号已保留'), status, code, **kwargs)


@dataclass(repr=False)
class Session:
    sid: str
    mode: str
    expires: float
    revision: int
    provider: object
    state: str = 'ready'
    busy: bool = False
    generation: int = 0
    captcha: dict | None = None
    captcha_expires: float = 0
    mobile: str | None = None
    username: str | None = None
    sms_key: str | None = None
    attempts: int = 0
    qr_key: str | None = None
    qr_image: str | None = None
    qr_expires: float = 0
    qr_consumed: bool = False
    next_poll: float = 0
    candidate: VerifiedBilibiliAccount | None = None
    candidate_expires: float = 0


class BilibiliLoginService:
    def __init__(self, source, provider_factory=BilibiliLoginProvider, clock=time.monotonic, wall_clock=time.time):
        self.source, self.provider_factory, self.clock, self.wall_clock = source, provider_factory, clock, wall_clock
        self._sessions, self._terminal = {}, {}
        self._lock = asyncio.Lock()
        self._starts, self._sms_attempts, self._sms_times = [], [], {}
        self._revision, self._validated, self._closed = 0, False, False
        self._cleanup = set()
        self._inflight = set()
        self._expiry_task = None
        self._expiry_changed = asyncio.Event()

    async def _expire_idle(self):
        try:
            while not self._closed:
                async with self._lock:
                    self._prune()
                    deadlines = [record[0] for record in self._terminal.values()]
                    for s in self._sessions.values():
                        deadlines.append(s.expires)
                        if s.qr_expires and not s.qr_consumed: deadlines.append(s.qr_expires)
                        if s.candidate: deadlines.append(s.candidate_expires)
                        if s.captcha: deadlines.append(s.captcha_expires)
                    if not deadlines: return
                    delay = max(.001, min(deadlines)-self.clock())
                    self._expiry_changed.clear()
                try:
                    await asyncio.wait_for(self._expiry_changed.wait(), timeout=delay)
                except TimeoutError:
                    pass
        finally:
            self._expiry_task = None

    def _schedule_expiry(self):
        self._expiry_changed.set()
        if self._expiry_task is None or self._expiry_task.done():
            self._expiry_task = asyncio.create_task(self._expire_idle())

    def status(self):
        empty = {'configured': False, 'state': 'unconfigured', 'uid': '', 'nickname': '', 'validated_at': None, 'message': ''}
        if self.source is None:
            return empty
        try:
            saved = self.source.credentials.load()
        except CredentialStoreError:
            return {**empty, 'state': 'storage_error', 'message': MESSAGES['STORAGE_ERROR']}
        configured = bool(saved.get('bilibili', {}).get('sessdata'))
        meta = saved.get('bilibili_meta', {})
        return {**empty, 'configured': configured, 'state': 'validated' if configured and self._validated else 'configured' if configured else 'unconfigured',
            'uid': str(meta.get('uid', ''))[:20], 'nickname': str(meta.get('nickname', ''))[:128],
            'validated_at': meta.get('validated_at') if isinstance(meta.get('validated_at'), (int, float)) else None}

    async def _close_provider(self, provider):
        try:
            await provider.aclose()
        except Exception:
            pass

    def _retire(self, s, state):
        if self._sessions.get(s.sid) is not s:
            return
        self._sessions.pop(s.sid)
        self._expiry_changed.set()
        s.generation += 1
        s.state = state
        public = {'session_id': s.sid, 'mode': s.mode, 'state': state, 'expires_in': 0, 'can_commit': False}
        if state == 'complete':
            public['account'] = self.status()
        self._terminal[s.sid] = (self.clock() + TERMINAL_TTL, public)
        s.captcha = s.candidate = s.qr_image = s.qr_key = s.sms_key = None
        s.username = s.mobile = None
        while len(self._terminal) > MAX_RECORDS:
            self._terminal.pop(next(iter(self._terminal)))
        if not s.busy:
            task = asyncio.create_task(self._close_provider(s.provider))
            self._cleanup.add(task)
            task.add_done_callback(self._cleanup.discard)

    def _prune(self):
        now = self.clock()
        self._terminal = {sid: record for sid, record in self._terminal.items() if record[0] > now}
        for s in list(self._sessions.values()):
            if s.captcha and s.captcha_expires <= now:
                s.captcha = None
            if s.expires <= now or (s.mode == 'qr' and not s.qr_consumed and s.qr_expires and s.qr_expires <= now) or (s.candidate and s.candidate_expires <= now):
                self._retire(s, 'expired')

    def _get(self, sid, modes=None):
        self._prune()
        s = self._sessions.get(sid)
        if self._closed or not s:
            raise fail('SESSION_EXPIRED', 410)
        if modes and s.mode not in modes:
            raise fail('MODE_MISMATCH', 409)
        if s.revision != self._revision:
            raise fail('ACCOUNT_CHANGED', 409)
        return s

    def _public(self, s, image=False):
        result = {'session_id': s.sid, 'mode': s.mode, 'state': s.state,
            'expires_in': max(0, math.ceil(s.expires - self.clock())), 'can_commit': s.candidate is not None}
        if s.mode == 'qr':
            result['qr_expires_in'] = max(0, math.ceil(s.qr_expires - self.clock()))
            if image:
                result['qr_image'] = s.qr_image
        return result

    def session_status(self, sid):
        self._prune()
        if sid in self._terminal:
            return dict(self._terminal[sid][1])
        return self._public(self._get(sid))

    async def start(self, mode, *, is_disconnected=None):
        if self.source is None:
            raise fail('SOURCE_UNCONFIGURED', 404)
        if mode not in ('qr', 'password', 'sms', 'cookie'):
            raise fail('INVALID_INPUT', 422)
        async with self._lock:
            if self._closed:
                raise fail('SESSION_EXPIRED', 410)
            self._prune()
            now = self.clock()
            self._starts = [t for t in self._starts if now-t < 60]
            if len(self._starts) >= START_LIMIT:
                raise fail('RATE_LIMITED', 429, retry_after=60)
            self._starts.append(now)
            for old in list(self._sessions.values()):
                self._retire(old, 'cancelled')
            sid = secrets.token_urlsafe(32)
            s = Session(sid, mode, now+SESSION_TTL, self._revision, self.provider_factory())
            self._sessions[sid] = s
            self._schedule_expiry()
        if mode == 'qr':
            async def create(s):
                qr = await s.provider.start_qr()
                s.qr_key, s.qr_image = qr.polling_key, qr.image_data_url
                s.qr_expires = min(s.expires, self.clock()+min(QR_TTL, qr.display_for))
                s.state = 'waiting_scan'
            await self._run(sid, ('qr',), 'create', create, is_disconnected)
        return self._public(self._get(sid), image=True)

    async def cancel(self, sid):
        async with self._lock:
            self._prune()
            if sid in self._terminal:
                return dict(self._terminal[sid][1])
            s = self._sessions.get(sid)
            if s:
                self._retire(s, 'cancelled')
            return {'state': 'cancelled'}

    async def _run(self, sid, modes, operation, action, is_disconnected=None):
        async with self._lock:
            s = self._get(sid, modes)
            if s.busy:
                raise fail('BUSY', 409)
            if s.candidate and operation != 'commit':
                raise fail('COLLECTION_BUSY', 409, state='pending_save')
            if operation == 'poll' and self.clock() < s.next_poll:
                return self._public(s)
            s.busy = True
            generation = s.generation
            task = asyncio.current_task()
            self._inflight.add(task)
        try:
            async with asyncio.timeout(ACTION_TIMEOUT):
                result = await action(s)
                if is_disconnected and await is_disconnected():
                    await self.cancel(sid)
                    raise fail('SESSION_EXPIRED', 410)
            async with self._lock:
                current = self._get(sid, modes)
                if current is not s or s.generation != generation:
                    raise fail('SESSION_EXPIRED', 410)
                self._schedule_expiry()
                if isinstance(result, VerifiedBilibiliAccount):
                    return self._save(s, result)
                if s.state == 'expired':
                    self._retire(s, 'expired')
                    raise fail('SESSION_EXPIRED', 410)
                public = self._public(s)
                if operation == 'captcha':
                    public.update({'type': 'geetest3', 'gt': s.captcha['gt'], 'challenge': s.captcha['challenge']})
                if operation == 'sms':
                    public['retry_after'] = SMS_COOLDOWN
                return public
        except BilibiliProtocolError as error:
            if self._sessions.get(sid) is not s:
                raise fail('SESSION_EXPIRED', 410) from None
            if error.error_code in ('UPSTREAM_RESTRICTED', 'SECURITY_VERIFICATION_REQUIRED', 'UNSUPPORTED_RESPONSE'):
                self._retire(s, 'blocked')
            else:
                s.state = 'sms_sent' if operation == 'submit' and s.sms_key else 'failed'
            raise fail(error.error_code, error.status, state=s.state, retry_after=error.retry_after) from None
        except BilibiliLoginError:
            raise
        except (Exception, asyncio.CancelledError) as error:
            if isinstance(error, asyncio.CancelledError):
                self._retire(s, 'cancelled')
                raise
            if self._sessions.get(sid) is not s:
                raise fail('SESSION_EXPIRED', 410) from None
            s.state = 'failed'
            raise fail('UPSTREAM_UNAVAILABLE', 502) from None
        finally:
            self._inflight.discard(task)
            s.busy = False
            if self._sessions.get(sid) is not s:
                await self._close_provider(s.provider)

    def _save(self, s, account):
        s.candidate = account
        if not s.candidate_expires:
            s.candidate_expires = min(s.expires, self.clock()+CANDIDATE_TTL)
        self._schedule_expiry()
        try:
            extra = self.source.commit_verified_account(account)
        except BilibiliSaveBusy:
            s.state = 'pending_save'
            raise fail('COLLECTION_BUSY', 409, state='pending_save') from None
        except CredentialStoreError:
            s.state = 'pending_save'
            raise fail('STORAGE_ERROR', 500, state='pending_save') from None
        self._revision += 1
        self._validated = True
        self._retire(s, 'complete')
        return {'ok': True, 'state': 'complete', 'account': self.status(), **extra}

    async def captcha(self, sid, *, is_disconnected=None):
        async def action(s):
            s.captcha = await s.provider.get_captcha()
            s.captcha_expires = self.clock()+CAPTCHA_TTL
            s.state = 'sms_sent' if s.sms_key else 'ready'
        return await self._run(sid, ('password', 'sms'), 'captcha', action, is_disconnected)

    def _proof(self, s, proof):
        if (not s.captcha or self.clock() >= s.captcha_expires or not isinstance(proof, dict)
                or any(not isinstance(proof.get(k), str) or not proof[k] or len(proof[k]) > 4096 for k in ('validate', 'seccode'))):
            raise fail('CAPTCHA_REQUIRED')
        combined = {k: s.captcha[k] for k in ('token', 'challenge')}
        combined.update({k: proof[k] for k in ('validate', 'seccode')})
        s.captcha = None
        return combined

    def _attempt(self, s):
        if s.attempts >= MAX_ATTEMPTS:
            self._retire(s, 'expired')
            raise fail('SESSION_EXPIRED', 410)
        s.attempts += 1

    async def password(self, sid, username, password, proof, *, is_disconnected=None):
        async def login(s):
            if not isinstance(username, str) or not username.strip() or len(username) > 254:
                raise fail('INVALID_INPUT', 422)
            if s.username and username != s.username:
                raise fail('ACCOUNT_CHANGED', 409)
            self._attempt(s)
            challenge = self._proof(s, proof)
            s.username = username
            s.state = 'verifying'
            values = await s.provider.login_password(username, password, challenge)
            return await s.provider.validate_credentials(values)
        return await self._run(sid, ('password',), 'password', login, is_disconnected)

    async def sms_send(self, sid, mobile, proof, *, is_disconnected=None):
        async def send(s):
            if not isinstance(mobile, str) or not re.fullmatch(r'1[3-9][0-9]{9}', mobile):
                raise fail('INVALID_INPUT', 422)
            if s.mobile and mobile != s.mobile:
                raise fail('ACCOUNT_CHANGED', 409)
            now = self.clock()
            digest = hashlib.sha256(('86:'+mobile).encode()).hexdigest()
            self._sms_times = {k: t for k, t in self._sms_times.items() if now-t < SMS_COOLDOWN}
            self._sms_attempts = [t for t in self._sms_attempts if now-t < SMS_WINDOW]
            if digest in self._sms_times or len(self._sms_attempts) >= SMS_LIMIT:
                raise fail('RATE_LIMITED', 429, retry_after=SMS_COOLDOWN)
            challenge = self._proof(s, proof)
            self._sms_times[digest] = now
            self._sms_attempts.append(now)
            s.mobile = mobile
            s.sms_key = await s.provider.send_sms(mobile, challenge)
            s.state = 'sms_sent'
        return await self._run(sid, ('sms',), 'sms', send, is_disconnected)

    async def sms_submit(self, sid, code, *, is_disconnected=None):
        async def login(s):
            if not isinstance(code, str) or not re.fullmatch(r'[0-9]{4,8}', code):
                raise fail('INVALID_INPUT', 422)
            if not s.mobile or not s.sms_key:
                raise fail('SMS_REQUIRED')
            self._attempt(s)
            mobile, sms_key = s.mobile, s.sms_key
            s.state = 'verifying'
            values = await s.provider.login_sms(mobile, code, sms_key)
            return await s.provider.validate_credentials(values)
        return await self._run(sid, ('sms',), 'submit', login, is_disconnected)

    async def qr_poll(self, sid, *, is_disconnected=None):
        async def poll(s):
            if s.qr_consumed:
                raise fail('INVALID_CREDENTIALS', 409)
            s.next_poll = self.clock()+POLL_INTERVAL
            result = await s.provider.poll_qr(s.qr_key)
            if result.state == 'credential_ready':
                s.qr_consumed = True
                s.qr_key = s.qr_image = None
                s.state = 'verifying'
                return await s.provider.validate_credentials(result.credentials)
            s.state = result.state
        return await self._run(sid, ('qr',), 'poll', poll, is_disconnected)

    async def cookie(self, sid, values, *, is_disconnected=None):
        async def validate(s): return await s.provider.validate_credentials(normalize_cookie_input(values))
        return await self._run(sid, ('cookie',), 'cookie', validate, is_disconnected)

    async def commit(self, sid, *, is_disconnected=None):
        async def validate(s):
            if not s.candidate:
                raise fail('INVALID_INPUT', 409)
            return await s.provider.validate_credentials(s.candidate.credentials)
        return await self._run(sid, ('qr', 'password', 'sms', 'cookie'), 'commit', validate, is_disconnected)

    async def import_legacy(self, values, *, is_disconnected=None):
        s = await self.start('cookie', is_disconnected=is_disconnected)
        result = await self.cookie(s['session_id'], values, is_disconnected=is_disconnected)
        return {**result, **result['account']}

    async def aclose(self):
        self._closed = True
        expiry_task = self._expiry_task
        if expiry_task:
            expiry_task.cancel()
        for s in list(self._sessions.values()):
            self._retire(s, 'cancelled')
        tasks = [task for task in self._inflight if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if expiry_task:
            await asyncio.gather(expiry_task, return_exceptions=True)
        if self._cleanup:
            await asyncio.gather(*list(self._cleanup), return_exceptions=True)
        self._terminal.clear()
