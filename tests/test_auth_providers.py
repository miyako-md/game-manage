import base64
import hashlib
import json
from urllib.parse import parse_qs
from uuid import UUID

import httpx
import pytest
import respx
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from game_assistant.adapters.wuthering_waves.rolebox_client import USER_AGENT
from game_assistant.auth.providers import AuthError, EndfieldLoginProvider, NteLoginProvider, WuwaLoginProvider

KURO = "https://api.kurobbs.com"
LAOHU = "https://user.laohu.com"
TAJI = "https://bbs-api.tajiduo.com"
HG = "https://as.hypergryph.com"
HG_BINDING = "https://binding-api-account-prod.hypergryph.com/account/binding/v1/binding_list"
APP_KEY = "89155cc4e8634ec5b1b6364013b23e3e"  # Public SDK application constant.
CONTEXT = {"did": "12345678-1234-4234-8234-123456789abc", "dev_code": f"8.8.8.8, {USER_AGENT}"}
CAPTCHA = {"captcha_id": "ec4aa4174277d822d73f2442a165a2cd", "lot_number": "lot", "captcha_output": "human-proof", "pass_token": "pass", "gen_time": "123"}


def form(request):
    assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    return {k: v[0] for k, v in parse_qs(request.content.decode(), keep_blank_values=True).items()}


def mock_wuwa_login(roles=None):
    respx.post(KURO + "/user/sdkLogin").respond(200, json={"code": 200, "data": {"token": "kuro-secret", "userId": 12}})
    respx.post(KURO + "/gamer/role/list").respond(200, json={"code": 200, "data": roles if roles is not None else [{"roleId": "1001", "serverId": "server", "roleName": "漂泊者"}]})


def mock_nte_login(roles=None):
    respx.post(LAOHU + "/m/newApi/checkPhoneCaptchaWithOutLogin").respond(200, json={"code": 0, "result": {}})
    respx.post(LAOHU + "/openApi/sms/new/login").respond(200, json={"code": 0, "result": {"userId": 56, "token": "laohu-secret"}})
    respx.post(TAJI + "/usercenter/api/login").respond(200, json={"code": 0, "data": {"accessToken": "access", "refreshToken": "refresh", "uid": 78}})
    respx.get(TAJI + "/usercenter/api/v2/getGameRoles", params={"gameId": "1289"}).respond(200, json={"code": 0, "data": roles if roles is not None else {"bindRole": 9001, "roles": [{"roleId": 9001, "roleName": "鉴定师"}]}})


@respx.mock
async def test_wuwa_context_uses_validated_public_ip_and_matching_user_agent():
    respx.get("https://api.ipify.org").respond(200, text="8.8.8.8\n")
    context = await WuwaLoginProvider().start_context()
    UUID(context["did"])
    assert context["dev_code"] == f"8.8.8.8, {USER_AGENT}"


@pytest.mark.parametrize("bad_ip", ["not-an-ip", "127.0.0.1", "192.168.1.1", "8.8.8.8\r\nx-secret: leak"])
@respx.mock
async def test_wuwa_context_rejects_untrusted_ip_lookup(bad_ip):
    respx.get("https://api.ipify.org").respond(200, text=bad_ip)
    with pytest.raises(AuthError):
        await WuwaLoginProvider().start_context()


@respx.mock
async def test_wuwa_sms_submits_only_validated_human_captcha():
    route = respx.post(KURO + "/user/getSmsCodeForH5").respond(200, json={"code": 200})
    provider = WuwaLoginProvider()
    with pytest.raises(AuthError):
        await provider.send_sms(CONTEXT, "13800000000")
    await provider.send_sms(CONTEXT, "13800000000", CAPTCHA)
    request = route.calls.last.request
    assert form(request) == {"mobile": "13800000000", "geeTestData": json.dumps(CAPTCHA, separators=(",", ":"))}
    assert request.headers["devcode"] == CONTEXT["did"]
    assert request.headers["source"] == "h5"


@respx.mock
async def test_wuwa_login_exchanges_token_for_selected_role_ticket():
    mock_wuwa_login()
    ticket = respx.post(KURO + "/aki/roleBox/requestToken").respond(200, json={"code": 200, "data": {"accessToken": "ticket"}})
    credentials = await WuwaLoginProvider().login(CONTEXT, "13800000000", "123456")
    assert credentials == {**CONTEXT, "token": "kuro-secret", "token_source": "ios", "b_at": "ticket", "role_id": "1001", "server_id": "server", "user_id": "12", "nickname": "漂泊者"}
    assert form(respx.calls[0].request) == {"mobile": "13800000000", "code": "123456", "devCode": CONTEXT["did"]}
    assert form(respx.calls[1].request) == {"gameId": "3"}
    assert form(ticket.calls.last.request) == {"roleId": "1001", "serverId": "server"}
    assert ticket.calls.last.request.headers["devcode"] == CONTEXT["dev_code"]
    assert ticket.calls.last.request.headers["did"] == CONTEXT["did"]
    assert ticket.calls.last.request.headers["token"] == "kuro-secret"


@respx.mock
async def test_wuwa_renew_preserves_account_and_only_requests_ticket():
    old = {**CONTEXT, "token": "token", "b_at": "old", "role_id": "1001", "server_id": "server", "user_id": "12", "nickname": "漂泊者"}
    respx.post(KURO + "/aki/roleBox/requestToken").respond(200, json={"code": 200, "data": {"accessToken": "new"}})
    assert await WuwaLoginProvider().renew(old) == {**old, "b_at": "new"}
    assert old["b_at"] == "old"
    assert len(respx.calls) == 1


@respx.mock
async def test_wuwa_no_role_is_not_a_successful_login():
    mock_wuwa_login([])
    with pytest.raises(AuthError, match="绑定"):
        await WuwaLoginProvider().login(CONTEXT, "13800000000", "123456")


@pytest.mark.parametrize("code", [130, 132, 220, 270, 999])
@respx.mock
async def test_wuwa_errors_preserve_code_without_returning_upstream_secrets(code):
    respx.post(KURO + "/user/sdkLogin").respond(200, json={"code": code, "msg": "secret-token 13800000000 123456", "data": {"token": "secret-token"}})
    with pytest.raises(AuthError) as caught:
        await WuwaLoginProvider().login(CONTEXT, "13800000000", "123456")
    assert caught.value.code == code
    assert caught.value.message == str(caught.value)
    assert "secret" not in str(caught.value)
    assert "13800000000" not in str(caught.value)
    assert caught.value.__cause__ is None


@respx.mock
async def test_nte_sms_signs_public_sdk_form_for_same_device():
    route = respx.post(LAOHU + "/m/newApi/sendPhoneCaptchaWithOutLogin").respond(200, json={"code": 0, "result": {}})
    provider = NteLoginProvider()
    context = await provider.start_context()
    assert len(context["device_id"]) == 16 and context["device_id"].startswith("HT")
    await provider.send_sms(context, "13800000000")
    fields = form(route.calls.last.request)
    signature = fields.pop("sign")
    assert signature == hashlib.md5(("".join(fields[k] for k in sorted(fields)) + APP_KEY).encode()).hexdigest()
    assert fields["appId"] == "10550" and fields["type"] == "16"
    assert fields["deviceId"] == fields["adm"] == context["device_id"]
    assert fields["cellphone"] == "13800000000"


@respx.mock
async def test_nte_login_encrypts_sms_and_exchanges_credentials_with_game_scoped_roles():
    mock_nte_login()
    credentials = await NteLoginProvider().login({"device_id": "HTDEVICE"}, "13800000000", "123456")
    assert credentials == {"access_token": "access", "refresh_token": "refresh", "device_id": "HTDEVICE", "role_id": "9001", "nickname": "鉴定师", "center_uid": "78"}
    encrypted = form(respx.calls[1].request)
    signature = encrypted.pop("sign")
    assert signature == hashlib.md5(("".join(encrypted[k] for k in sorted(encrypted)) + APP_KEY).encode()).hexdigest()
    cipher = AES.new(APP_KEY[-16:].encode(), AES.MODE_ECB)
    assert unpad(cipher.decrypt(base64.b64decode(encrypted["cellphone"])), 16).decode() == "13800000000"
    assert unpad(cipher.decrypt(base64.b64decode(encrypted["captcha"])), 16).decode() == "123456"
    assert form(respx.calls[2].request) == {"appId": "10551", "token": "laohu-secret", "userIdentity": "56"}
    assert respx.calls[3].request.headers["authorization"] == "access"
    stamp, nonce, digest = respx.calls[3].request.headers["ds"].split(",")
    assert digest == hashlib.md5(f"{stamp}{nonce}1.2.4pUds3dfMkl".encode()).hexdigest()


@pytest.mark.parametrize("roles", [[], {"bindRole": 0, "roles": []}, {"roles": [{"roleId": 0}]}, {"otherGame": {"roleId": 999}}, {"roles": [{"gameId": 1256, "roleId": 999}]}])
@respx.mock
async def test_nte_rejects_empty_roles_and_never_searches_other_games(roles):
    mock_nte_login(roles)
    with pytest.raises(AuthError, match="绑定"):
        await NteLoginProvider().login({"device_id": "HTDEVICE"}, "13800000000", "123456")


@respx.mock
async def test_nte_legacy_role_list_is_supported():
    mock_nte_login([{"roleId": 9002, "roleName": "旧格式"}])
    assert (await NteLoginProvider().login({"device_id": "HTDEVICE"}, "13800000000", "123456"))["role_id"] == "9002"


@respx.mock
async def test_nte_refresh_rotates_both_tokens_and_preserves_selected_role():
    old = {"access_token": "old-access", "refresh_token": "old-refresh", "device_id": "HTDEVICE", "role_id": "9001", "nickname": "鉴定师", "center_uid": "78"}
    route = respx.post(TAJI + "/usercenter/api/refreshToken").respond(200, json={"code": 0, "data": {"accessToken": "new-access", "refreshToken": "new-refresh"}})
    assert await NteLoginProvider().renew(old) == {**old, "access_token": "new-access", "refresh_token": "new-refresh"}
    assert route.calls.last.request.headers["authorization"] == "old-refresh"
    assert old["refresh_token"] == "old-refresh"
    assert len(respx.calls) == 1


@pytest.mark.parametrize("response", [httpx.Response(200, text="secret-token"), httpx.Response(200, json=["secret-token"]), httpx.Response(401, text="secret-token"), httpx.Response(200, json={"code": 402, "msg": "secret-token"})])
@respx.mock
async def test_nte_refresh_errors_are_sanitized(response):
    respx.post(TAJI + "/usercenter/api/refreshToken").mock(return_value=response)
    with pytest.raises(AuthError) as caught:
        await NteLoginProvider().renew({"device_id": "HTDEVICE", "refresh_token": "secret-token"})
    assert "secret-token" not in str(caught.value)


@pytest.mark.parametrize("user_id", [0, -1, "invalid", True])
@respx.mock
async def test_nte_rejects_invalid_laohu_identity_before_token_exchange(user_id):
    mock_nte_login()
    respx.post(LAOHU + "/openApi/sms/new/login").respond(200, json={"code": 0, "result": {"userId": user_id, "token": "laohu-secret"}})
    with pytest.raises(AuthError):
        await NteLoginProvider().login({"device_id": "HTDEVICE"}, "13800000000", "123456")


@pytest.mark.parametrize("malformed_code", ["9" * 5000, None, True, {"token": "secret"}], ids=["oversized", "null", "boolean", "object"])
@respx.mock
async def test_malformed_upstream_code_remains_a_sanitized_auth_error(malformed_code):
    respx.post(KURO + "/user/sdkLogin").respond(200, json={"code": malformed_code})
    with pytest.raises(AuthError):
        await WuwaLoginProvider().login(CONTEXT, "13800000000", "123456")


@respx.mock
async def test_wuwa_role_user_id_fallback_and_json_encoded_ticket():
    mock_wuwa_login([{"roleId": "1001", "serverId": "server", "roleName": "漂泊者", "userId": 34}])
    respx.post(KURO + "/user/sdkLogin").respond(200, json={"code": 200, "data": {"token": "kuro-secret"}})
    respx.post(KURO + "/aki/roleBox/requestToken").respond(200, json={"code": 200, "data": '{"accessToken":"ticket"}'})
    assert (await WuwaLoginProvider().login(CONTEXT, "13800000000", "123456"))["user_id"] == "34"


@respx.mock
async def test_renewal_missing_new_ticket_does_not_mutate_existing_credentials():
    old = {**CONTEXT, "token": "token", "b_at": "keep", "role_id": "1001", "server_id": "server"}
    respx.post(KURO + "/aki/roleBox/requestToken").respond(200, json={"code": 200, "data": {}})
    with pytest.raises(AuthError):
        await WuwaLoginProvider().renew(old)
    assert old["b_at"] == "keep"


@respx.mock
async def test_network_exception_does_not_expose_request_details():
    respx.post(KURO + "/user/sdkLogin").mock(side_effect=httpx.ConnectError("secret 13800000000"))
    with pytest.raises(AuthError) as caught:
        await WuwaLoginProvider().login(CONTEXT, "13800000000", "123456")
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None


def endfield_binding(accounts):
    return {"status": 0, "msg": "OK", "data": {"list": [
        {"appCode": "arknights", "bindingList": [{"uid": "1", "isOfficial": True, "roles": [{"roleId": "9", "serverId": "1"}]}]},
        {"appCode": "endfield", "appName": "明日方舟：终末地", "bindingList": accounts},
    ]}}


OFFICIAL = {"uid": "hg-uid-1", "isOfficial": True, "channelName": "官服", "roles": [
    {"roleId": "31000001", "nickName": "管理员", "level": 52, "serverId": "1", "serverName": "China", "isDefault": True}]}
BILIBILI = {"uid": "hg-uid-2", "isOfficial": False, "channelName": "bilibili服", "roles": [
    {"roleId": "32000002", "nickName": "B服角色", "serverId": "1"}]}


def mock_endfield_login(accounts=None):
    respx.post(HG + "/user/auth/v1/token_by_phone_code").respond(200, json={"status": 0, "msg": "OK", "data": {"token": "hg-secret"}})
    grant = respx.post(HG + "/user/oauth2/v2/grant").respond(200, json={"status": 0, "msg": "OK", "data": {"token": "grant-secret"}})
    binding = respx.get(HG_BINDING).respond(200, json=endfield_binding(accounts if accounts is not None else [BILIBILI, OFFICIAL]))
    return grant, binding


@respx.mock
async def test_endfield_sms_login_selects_the_official_server_role():
    send = respx.post(HG + "/general/v1/send_phone_code").respond(200, json={"status": 0, "msg": "OK"})
    grant, binding = mock_endfield_login()
    provider = EndfieldLoginProvider()
    await provider.send_sms({}, "13800000000")
    credentials = await provider.login({}, "13800000000", "123456")
    assert json.loads(send.calls[0].request.content) == {"phone": "13800000000", "type": 1}
    assert json.loads(grant.calls[0].request.content) == {"token": "hg-secret", "appCode": "be36d44aa36bfb5b", "type": 1}
    assert binding.calls[0].request.url.params["appCode"] == "endfield"
    assert binding.calls[0].request.url.params["token"] == "grant-secret"
    assert credentials == {"hg_token": "hg-secret", "uid": "hg-uid-1", "role_id": "31000001",
                           "server_id": "1", "nickname": "管理员"}


@respx.mock
async def test_endfield_login_shows_the_server_hint_for_a_wrong_code():
    respx.post(HG + "/user/auth/v1/token_by_phone_code").respond(200, json={"status": 100, "msg": "验证码错误\n"})
    with pytest.raises(AuthError, match="^验证码错误$"):
        await EndfieldLoginProvider().login({}, "13800000000", "000000")


@respx.mock
@pytest.mark.parametrize("accounts", [[], [BILIBILI], [{**OFFICIAL, "isDeleted": True}],
                                      [{**OFFICIAL, "roles": [{**OFFICIAL["roles"][0], "serverId": "2"}]}]])
async def test_endfield_login_requires_an_official_server_role(accounts):
    mock_endfield_login(accounts)
    with pytest.raises(AuthError, match="官服角色"):
        await EndfieldLoginProvider().login({}, "13800000000", "123456")


@respx.mock
@pytest.mark.parametrize("response", [httpx.Response(401), httpx.Response(200, json={"status": 3, "msg": "登录已过期，请重新登录"})])
async def test_endfield_expired_token_is_reported_as_invalid_session(response):
    respx.post(HG + "/user/auth/v1/token_by_phone_code").respond(200, json={"status": 0, "data": {"token": "hg-secret"}})
    respx.post(HG + "/user/oauth2/v2/grant").mock(return_value=response)
    with pytest.raises(AuthError) as caught:
        await EndfieldLoginProvider().login({}, "13800000000", "123456")
    assert caught.value.code == 401 and "hg-secret" not in caught.value.message


@respx.mock
async def test_endfield_sms_rate_limit_is_not_retried():
    route = respx.post(HG + "/general/v1/send_phone_code").respond(429)
    with pytest.raises(AuthError, match="频繁"):
        await EndfieldLoginProvider().send_sms({}, "13800000000")
    assert route.call_count == 1
