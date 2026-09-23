"""Small community authentication clients; no SMS retries or credential logging.

Protocol references: WutheringWavesUID 1d693a2 and NTEUID ba7790e.
Only human supplied Geetest proofs are accepted. SDK application constants below
are public protocol identifiers, not user credentials.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import time
import uuid
from typing import Any

import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from game_assistant.adapters.neverness.endpoints import GAME_ID as NTE_GAME_ID
from game_assistant.adapters.neverness.tajiduo_client import make_ds_header
from game_assistant.adapters.wuthering_waves.rolebox_client import USER_AGENT

WUWA_CAPTCHA_ID = "ec4aa4174277d822d73f2442a165a2cd"
LAOHU_APP_KEY = "89155cc4e8634ec5b1b6364013b23e3e"
_KURO = "https://api.kurobbs.com"
_LAOHU = "https://user.laohu.com"
_TAJIDUO = "https://bbs-api.tajiduo.com"
_INVALID_SESSION = "登录已过期，请重新登录"
_BAD_RESPONSE = "登录服务返回异常，请稍后重试"


class AuthError(Exception):
    def __init__(self, message: str, code: int | None = None):
        self.message = message
        self.code = code
        super().__init__(message)


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, (str, int)) and not isinstance(value, bool) else ""


def _required(data: Any, field: str) -> str:
    value = _text(data.get(field)) if isinstance(data, dict) else ""
    if not value:
        raise AuthError(_BAD_RESPONSE)
    return value


def _error(code: int | None, fallback: str) -> AuthError:
    messages = {
        130: "短信验证码错误，请重新输入",
        132: "短信验证码已过期，请重新获取",
        220: _INVALID_SESSION,
        401: _INVALID_SESSION,
        402: _INVALID_SESSION,
        403: _INVALID_SESSION,
        10903: _INVALID_SESSION,
        270: "登录环境验证未通过，请切换网络后重试",
        429: "请求过于频繁，请稍后重试",
    }
    return AuthError(messages.get(code, fallback), code)


async def _request(url: str, *, headers: dict, data: dict | None = None,
                   params: dict | None = None, method: str = "POST",
                   result_key: str = "data", success_codes: tuple = (0,),
                   failure: str = "登录服务请求失败，请稍后重试") -> Any:
    try:
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            response = await client.request(method, url, headers=headers, data=data, params=params)
        if response.status_code != 200:
            raise _error(response.status_code, failure)
        payload = response.json()
    except httpx.HTTPError:
        raise AuthError("无法连接登录服务，请检查网络后重试") from None
    except ValueError:
        raise AuthError(_BAD_RESPONSE) from None
    if not isinstance(payload, dict):
        raise AuthError(_BAD_RESPONSE)
    code = payload.get("code")
    if isinstance(code, str) and len(code) <= 12 and code.lstrip("-").isascii() and code.lstrip("-").isdigit():
        code = int(code)
    if not isinstance(code, int) or isinstance(code, bool):
        raise AuthError(_BAD_RESPONSE)
    if code not in success_codes:
        raise _error(code, failure)
    result = payload.get(result_key)
    if isinstance(result, str):
        try:
            return json.loads(result)
        except ValueError:
            raise AuthError(_BAD_RESPONSE) from None
    return result


class WuwaLoginProvider:
    captcha_id = WUWA_CAPTCHA_ID

    async def start_context(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                response = await client.get("https://api.ipify.org")
            response.raise_for_status()
            address = ipaddress.ip_address(response.text.strip())
            if not address.is_global:
                raise ValueError
        except (httpx.HTTPError, ValueError):
            raise AuthError("无法获取有效公网地址，请检查网络后重试") from None
        return {"did": str(uuid.uuid4()), "dev_code": f"{address}, {USER_AGENT}"}

    def _headers(self, context: dict) -> dict:
        return {"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded",
                "source": "ios", "Origin": "https://web-static.kurobbs.com",
                "devCode": _required(context, "dev_code"), "did": _required(context, "did")}

    async def send_sms(self, context: dict, mobile: str, captcha: dict | None = None) -> None:
        fields = ("captcha_id", "lot_number", "captcha_output", "pass_token", "gen_time")
        if not isinstance(captcha, dict) or any(
            not isinstance(captcha.get(key), str) or not captcha[key].strip() or len(captcha[key]) > 8192
            for key in fields
        ) or captcha["captcha_id"] != self.captcha_id:
            raise AuthError("请先完成人机验证")
        proof = {key: captcha[key] for key in fields}
        headers = self._headers(context)
        headers.update({"source": "h5", "devCode": context["did"]})
        await _request(_KURO + "/user/getSmsCodeForH5", headers=headers,
                       data={"mobile": mobile, "geeTestData": json.dumps(proof, separators=(",", ":"))},
                       success_codes=(0, 200), failure="短信发送失败，请重新完成人机验证后重试")

    async def login(self, context: dict, mobile: str, code: str) -> dict:
        headers = self._headers(context)
        account = await _request(_KURO + "/user/sdkLogin", headers=headers,
                                 data={"mobile": mobile, "code": code, "devCode": context["did"]},
                                 success_codes=(0, 200), failure="登录失败，请检查短信验证码后重试")
        token = _required(account, "token")
        headers.update({"token": token, "devCode": context["did"]})
        roles = await _request(_KURO + "/gamer/role/list", headers=headers,
                               data={"gameId": "3"}, success_codes=(0, 200))
        selected = next((role for role in roles if isinstance(role, dict)
                         and _text(role.get("gameId", 3)) == "3"
                         and _text(role.get("roleId")) not in ("", "0")
                         and _text(role.get("serverId"))), None) if isinstance(roles, list) else None
        if not selected:
            raise AuthError("该账号未绑定鸣潮角色，请先在库街区绑定角色")
        credentials = {"token": token, "token_source": "ios", "did": context["did"], "dev_code": context["dev_code"],
                       "role_id": _required(selected, "roleId"), "server_id": _required(selected, "serverId"),
                       "user_id": _text(account.get("userId")) or _text(selected.get("userId")) or _required(selected, "roleId"),
                       "nickname": _text(selected.get("roleName"))}
        return await self.renew(credentials)

    async def renew(self, credentials: dict) -> dict:
        headers = self._headers(credentials)
        headers.update({"token": _required(credentials, "token"), "b-at": ""})
        ticket = await _request(_KURO + "/aki/roleBox/requestToken", headers=headers,
                                data={"roleId": _required(credentials, "role_id"),
                                      "serverId": _required(credentials, "server_id")},
                                success_codes=(0, 200), failure="登录续期失败，请稍后重试或重新登录")
        return {**credentials, "b_at": _required(ticket, "accessToken")}


class NteLoginProvider:
    async def start_context(self) -> dict:
        return {"device_id": "HT" + uuid.uuid4().hex[:14].upper()}

    def _laohu_fields(self, context: dict, *, millis: bool = False) -> dict:
        device = _required(context, "device_id")
        fields = {"appId": "10550", "channelId": "1", "deviceId": device,
                  "deviceType": "Pixel 6", "deviceModel": "Pixel 6", "deviceName": "Pixel 6",
                  "deviceSys": "Android 14", "adm": device, "idfa": "", "sdkVersion": "4.273.0",
                  "bid": "com.pwrd.htassistant", "t": str(int(time.time() * (1000 if millis else 1)))}
        fields.update({"version": "12", "mac": ""} if millis else {"versionCode": "12", "imei": ""})
        return fields

    async def _laohu(self, path: str, fields: dict, *, keep_empty: bool = False) -> Any:
        raw = "".join(fields[key] for key in sorted(fields)) + LAOHU_APP_KEY
        signed = {**fields, "sign": hashlib.md5(raw.encode()).hexdigest()}
        signed = {key: value for key, value in signed.items() if keep_empty or value != ""}
        return await _request(_LAOHU + path, headers={"User-Agent": "okhttp/4.9.0"},
                              data=signed, result_key="result", failure="老虎登录验证失败，请检查短信验证码或稍后重试")

    def _tajiduo_headers(self, context: dict, token: str = "") -> dict:
        return {"User-Agent": "okhttp/4.12.0", "platform": "android",
                "deviceid": _required(context, "device_id"), "appversion": "1.2.4", "uid": "0",
                "authorization": token, "ds": make_ds_header()}

    async def send_sms(self, context: dict, mobile: str, captcha: dict | None = None) -> None:
        fields = self._laohu_fields(context)
        fields.update({"cellphone": mobile, "areaCodeId": "1", "type": "16"})
        await self._laohu("/m/newApi/sendPhoneCaptchaWithOutLogin", fields)

    async def login(self, context: dict, mobile: str, code: str) -> dict:
        check = self._laohu_fields(context)
        check.update({"cellphone": mobile, "captcha": code})
        await self._laohu("/m/newApi/checkPhoneCaptchaWithOutLogin", check)
        fields = self._laohu_fields(context, millis=True)
        cipher = AES.new(LAOHU_APP_KEY[-16:].encode(), AES.MODE_ECB)
        fields.update({"cellphone": base64.b64encode(cipher.encrypt(pad(mobile.encode(), 16))).decode(),
                       "captcha": base64.b64encode(cipher.encrypt(pad(code.encode(), 16))).decode(),
                       "areaCodeId": "1", "type": "16"})
        account = await self._laohu("/openApi/sms/new/login", fields, keep_empty=True)
        identity = _required(account, "userId")
        if not identity.isascii() or not identity.isdigit() or len(identity) > 20 or int(identity) <= 0:
            raise AuthError(_BAD_RESPONSE)
        session = await _request(_TAJIDUO + "/usercenter/api/login", headers=self._tajiduo_headers(context),
                                 data={"appId": "10551", "token": _required(account, "token"),
                                       "userIdentity": identity})
        credentials = {"device_id": context["device_id"], "access_token": _required(session, "accessToken"),
                       "refresh_token": _required(session, "refreshToken"), "center_uid": _required(session, "uid")}
        payload = await _request(_TAJIDUO + "/usercenter/api/v2/getGameRoles", method="GET",
                                 headers=self._tajiduo_headers(context, credentials["access_token"]),
                                 params={"gameId": NTE_GAME_ID})
        roles = payload.get("roles", []) if isinstance(payload, dict) else payload
        # Only this endpoint's documented roles container is eligible. Do not
        # recursively search unrelated community/game objects for a roleId.
        selected = next((role for role in roles if isinstance(role, dict)
                         and _text(role.get("gameId", NTE_GAME_ID)) == NTE_GAME_ID
                         and _text(role.get("roleId")).isdigit() and int(role["roleId"]) > 0), None) if isinstance(roles, list) else None
        if not selected:
            raise AuthError("该账号未绑定异环角色，请先在塔吉多绑定角色")
        credentials.update({"role_id": _required(selected, "roleId"), "nickname": _text(selected.get("roleName"))})
        return credentials

    async def renew(self, credentials: dict) -> dict:
        session = await _request(_TAJIDUO + "/usercenter/api/refreshToken",
                                 headers=self._tajiduo_headers(credentials, _required(credentials, "refresh_token")),
                                 failure="登录续期失败，请稍后重试或重新登录")
        return {**credentials, "access_token": _required(session, "accessToken"),
                "refresh_token": _required(session, "refreshToken")}
