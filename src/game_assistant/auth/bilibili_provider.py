"""Small, isolated adapters for Bilibili's undocumented web login protocol."""
from __future__ import annotations

import base64
import io
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
import qrcode
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

BASE = 'https://passport.bilibili.com'
QR_GENERATE = BASE + '/x/passport-login/web/qrcode/generate?source=main-fe-header'
QR_POLL = BASE + '/x/passport-login/web/qrcode/poll'
NAV = 'https://api.bilibili.com/x/web-interface/nav'
FIELDS = {'SESSDATA': 'sessdata', 'bili_jct': 'bili_jct', 'DedeUserID': 'dedeuserid',
          'buvid3': 'buvid3', 'buvid4': 'buvid4'}
LIMITS = {'sessdata': 4096, 'bili_jct': 128, 'dedeuserid': 20,
          'buvid3': 256, 'buvid4': 256, 'ac_time_value': 4096}
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
           'Referer': BASE + '/login'}

# HTTPX INFO logs include the URL query (QR key/exchange ticket); httpcore DEBUG
# logs may include Set-Cookie. Suppress only this task's login request records,
# leaving concurrent collectors and other applications' logging unchanged.
_private_request = ContextVar('bilibili_private_request', default=False)
class _PrivateRequestFilter(logging.Filter):
    def filter(self, record): return not _private_request.get()
for _logger_name in ('httpx','httpcore.connection','httpcore.http11','httpcore.http2','httpcore.proxy','httpcore.socks'):
    logging.getLogger(_logger_name).addFilter(_PrivateRequestFilter())


class BilibiliProtocolError(Exception):
    def __init__(self, error_code: str, status: int = 502, retry_after: int | None = None):
        self.error_code, self.status, self.retry_after = error_code, status, retry_after
        super().__init__(error_code)


@dataclass(frozen=True)
class QrChallenge:
    polling_key: str = field(repr=False)
    image_data_url: str = field(repr=False)
    display_for: int = 180


@dataclass(frozen=True)
class QrResult:
    state: str
    credentials: dict[str, str] | None = field(default=None, repr=False)


@dataclass(frozen=True)
class VerifiedBilibiliAccount:
    credentials: dict[str, str] = field(repr=False)
    uid: str
    nickname: str
    validated_at: float


def _values(values: dict, *, complete=False) -> dict[str, str]:
    if not isinstance(values, dict):
        raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
    result = {}
    for key, limit in LIMITS.items():
        value = values.get(key)
        if value in (None, ''):
            continue
        if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 or c == ';' for c in value):
            raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
        result[key] = value
    if not result.get('sessdata') or (complete and any(not result.get(k) for k in ('bili_jct', 'dedeuserid'))):
        raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
    return result


def normalize_cookie_input(values: dict[str, str]) -> dict[str, str]:
    if not isinstance(values, dict) or any(not isinstance(v, str) for v in values.values()):
        raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
    return _values({k: unquote(v.strip()) for k, v in values.items()})


def _trusted(url: str, *, exchange=False, final=False) -> bool:
    try:
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.username is not None or parts.password is not None or parts.port not in (None, 443) or parts.fragment:
            return False
        if final and parts.hostname == 'www.bilibili.com' and parts.path in ('', '/') and not parts.query:
            return True
        return (parts.hostname in ('passport.bilibili.com', 'passport.biligame.com')
                and (not exchange or parts.path == '/x/passport-login/web/crossDomain'))
    except (ValueError, TypeError):
        return False


class BilibiliLoginProvider:
    def __init__(self, client_factory=None, wall_clock=time.time):
        self._factory = client_factory or (lambda: httpx.AsyncClient(timeout=10, trust_env=False,
            follow_redirects=False, headers=HEADERS))
        self._client = None
        self.wall_clock = wall_clock

    async def aclose(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, method, url, **kwargs):
        if self._client is None:
            self._client = self._factory()
        try:
            token = _private_request.set(True)
            try:
                response = await self._client.request(method, url, **kwargs)
            finally:
                _private_request.reset(token)
        except httpx.HTTPError:
            raise BilibiliProtocolError('UPSTREAM_UNAVAILABLE') from None
        if response.status_code == 412:
            raise BilibiliProtocolError('UPSTREAM_RESTRICTED')
        if response.status_code == 429:
            raw = response.headers.get('retry-after', '')
            retry = int(raw) if raw.isascii() and raw.isdigit() and len(raw) <= 4 else 60
            raise BilibiliProtocolError('RATE_LIMITED', 429, max(1, min(3600, retry)))
        if not 200 <= response.status_code < 400:
            raise BilibiliProtocolError('UPSTREAM_UNAVAILABLE')
        if len(response.content) > 65536:
            raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
        return response

    @staticmethod
    def _data(response):
        try:
            payload = response.json()
        except ValueError:
            raise BilibiliProtocolError('UNSUPPORTED_RESPONSE') from None
        if not isinstance(payload, dict) or type(payload.get('code')) is not int:
            raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
        if payload['code'] != 0:
            raise BilibiliProtocolError('UPSTREAM_REJECTED', 400)
        data = payload.get('data')
        if not isinstance(data, dict):
            raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
        return data

    async def start_qr(self) -> QrChallenge:
        data = self._data(await self._request('GET', QR_GENERATE))
        url, key = data.get('url'), data.get('qrcode_key')
        if not isinstance(url, str) or len(url) > 8192 or not _trusted(url) or not isinstance(key, str) or not key or len(key) > 512:
            raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
        buffer = io.BytesIO()
        qrcode.make(url).save(buffer, format='PNG')
        return QrChallenge(key, 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode())

    async def poll_qr(self, polling_key: str) -> QrResult:
        response = await self._request('GET', QR_POLL, params={'qrcode_key': polling_key, 'source': 'main-fe-header'})
        data = self._data(response)
        code = data.get('code')
        states = {86101: 'waiting_scan', 86090: 'waiting_confirm', 86038: 'expired'}
        if type(code) is not int:
            raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
        if code in states:
            return QrResult(states[code])
        if code != 0:
            raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
        return QrResult('credential_ready', await self._resolve_credentials(data, response))

    @staticmethod
    def _merge(target, values):
        for key, value in values.items():
            if key in target and target[key] != value:
                raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
            target[key] = value

    def _cookies(self, response):
        result = {}
        for raw in response.headers.get_list('set-cookie'):
            parsed = SimpleCookie()
            try:
                parsed.load(raw)
            except Exception:
                raise BilibiliProtocolError('UNSUPPORTED_RESPONSE') from None
            for name, field_name in FIELDS.items():
                if name in parsed:
                    domain = parsed[name]['domain'].lstrip('.')
                    if domain and domain not in ('bilibili.com', 'biligame.com', 'passport.bilibili.com', 'passport.biligame.com'):
                        raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
                    self._merge(result, {field_name: unquote(parsed[name].value)})
        return result

    async def _resolve_credentials(self, data, response):
        url = data.get('url')
        header_values = self._cookies(response)
        final_home = isinstance(url, str) and _trusted(url, final=True) and urlsplit(url).hostname == 'www.bilibili.com'
        if all(header_values.get(k) for k in ('sessdata', 'bili_jct', 'dedeuserid')) and (url in (None, '') or final_home):
            if data.get('refresh_token'):
                header_values['ac_time_value'] = data['refresh_token']
            return _values(header_values, complete=True)
        if not isinstance(url, str) or len(url) > 8192 or not _trusted(url):
            raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
        result = header_values
        query = parse_qs(urlsplit(url).query, keep_blank_values=True)
        found_query = any(name in query for name in FIELDS)
        if found_query:
            for name, key in FIELDS.items():
                if name in query:
                    if len(set(query[name])) != 1:
                        raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
                    self._merge(result, {key: query[name][0]})
        else:
            if not _trusted(url, exchange=True):
                raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
            for index in range(4):
                exchanged = await self._request('GET', url)
                self._merge(result, self._cookies(exchanged))
                if not 300 <= exchanged.status_code < 400:
                    break
                next_url = exchanged.headers.get('location', '')
                if _trusted(next_url, final=True) and urlsplit(next_url).hostname == 'www.bilibili.com':
                    break
                if index == 3 or not _trusted(next_url, exchange=True):
                    raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
                url = next_url
        if data.get('refresh_token'):
            result['ac_time_value'] = data['refresh_token']
        return _values(result, complete=True)

    async def validate_credentials(self, values) -> VerifiedBilibiliAccount:
        values = _values(values)
        cookies = {name: values[key] for name, key in FIELDS.items() if key in values}
        cookie_header = httpx.Request('GET', NAV, cookies=cookies).headers['cookie']
        response = await self._request('GET', NAV, headers={'Cookie': cookie_header})
        try:
            data = self._data(response)
        except BilibiliProtocolError:
            raise BilibiliProtocolError('INVALID_CREDENTIALS', 400) from None
        uid = data.get('mid')
        uid = str(uid) if isinstance(uid, (str, int)) and not isinstance(uid, bool) else ''
        if (data.get('isLogin') is not True or not uid.isascii() or not uid.isdigit() or len(uid) > 20 or int(uid) <= 0
                or (values.get('dedeuserid') and values['dedeuserid'] != uid)):
            raise BilibiliProtocolError('INVALID_CREDENTIALS', 400)
        values = {**values, 'dedeuserid': uid}
        nickname = data.get('uname')
        return VerifiedBilibiliAccount(values, uid, nickname[:128] if isinstance(nickname, str) else '', self.wall_clock())

    @staticmethod
    def _proof(captcha):
        fields = ('token', 'challenge', 'validate', 'seccode')
        if not isinstance(captcha, dict) or any(not isinstance(captcha.get(k), str) or not captcha[k] or len(captcha[k]) > 4096 for k in fields):
            raise BilibiliProtocolError('CAPTCHA_REQUIRED', 400)
        return {k: captcha[k] for k in fields}

    async def get_captcha(self):
        data = self._data(await self._request('GET', BASE + '/x/passport-login/captcha', params={'source': 'main_web'}))
        geetest = data.get('geetest')
        if not isinstance(geetest, dict):
            raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
        result = {'gt': geetest.get('gt'), 'challenge': geetest.get('challenge'), 'token': data.get('token')}
        if any(not isinstance(v, str) or not v or len(v) > 4096 for v in result.values()):
            raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
        return result

    async def login_password(self, username, password, captcha):
        proof = self._proof(captcha)
        if not isinstance(username, str) or not username.strip() or len(username) > 254 or not isinstance(password, str) or not password or len(password) > 512:
            raise BilibiliProtocolError('INVALID_INPUT', 422)
        key_data = self._data(await self._request('GET', BASE + '/x/passport-login/web/key'))
        try:
            salt, public = key_data['hash'], key_data['key']
            if not isinstance(salt, str) or len(salt) > 256 or not isinstance(public, str) or len(public) > 8192:
                raise ValueError
            key = RSA.import_key(public)
            if not 1024 <= key.size_in_bits() <= 4096:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise BilibiliProtocolError('UNSUPPORTED_RESPONSE') from None
        try:
            encrypted = base64.b64encode(PKCS1_v1_5.new(key).encrypt((salt + password).encode())).decode()
        except (ValueError, UnicodeError):
            raise BilibiliProtocolError('INVALID_INPUT', 422) from None
        response = await self._request('POST', BASE + '/x/passport-login/web/login',
            data={'username': username, 'password': encrypted, 'keep': 'true', **proof})
        return await self._login_result(response)

    async def send_sms(self, mobile, captcha):
        data = self._data(await self._request('POST', BASE + '/x/passport-login/web/sms/send',
            data={'tel': mobile, 'cid': '86', 'source': 'main-fe-header', **self._proof(captcha)}))
        key = data.get('captcha_key')
        if not isinstance(key, str) or not key or len(key) > 4096:
            raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
        return key

    async def login_sms(self, mobile, code, captcha_key):
        response = await self._request('POST', BASE + '/x/passport-login/web/login/sms',
            data={'tel': mobile, 'cid': '86', 'code': code, 'captcha_key': captcha_key,
                  'source': 'main_web', 'keep': 'true'})
        return await self._login_result(response)

    async def _login_result(self, response):
        data = self._data(response)
        status = data.get('status')
        if type(status) is int and status in (1, 2, 5):
            raise BilibiliProtocolError('SECURITY_VERIFICATION_REQUIRED', 409)
        if type(status) is not int or status != 0:
            raise BilibiliProtocolError('UNSUPPORTED_RESPONSE')
        return await self._resolve_credentials(data, response)
