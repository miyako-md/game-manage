import importlib
import importlib.util
from urllib.parse import quote

import httpx
import pytest
import respx
import base64
from urllib.parse import parse_qs
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

BASE = 'https://passport.bilibili.com'
GENERATE = BASE + '/x/passport-login/web/qrcode/generate?source=main-fe-header'
POLL = BASE + '/x/passport-login/web/qrcode/poll'
NAV = 'https://api.bilibili.com/x/web-interface/nav'
VALUES = {'sessdata': 'FAKE_SESS', 'bili_jct': 'FAKE_JCT', 'dedeuserid': '10001'}


def provider():
    assert importlib.util.find_spec('game_assistant.auth.bilibili_provider'), 'Bilibili login provider missing'
    return importlib.import_module('game_assistant.auth.bilibili_provider').BilibiliLoginProvider()


def legacy_url(values=VALUES):
    names = {'sessdata': 'SESSDATA', 'bili_jct': 'bili_jct', 'dedeuserid': 'DedeUserID'}
    return BASE + '/login?' + '&'.join(names[k] + '=' + quote(v, safe='') for k, v in values.items())


def poll_result(data):
    return respx.get(POLL).respond(200, json={'code': 0, 'data': data})


@respx.mock
async def test_qr_generation_stays_in_memory(tmp_path, monkeypatch):
    p = provider()
    monkeypatch.chdir(tmp_path)
    respx.get(GENERATE).respond(200, json={'code': 0, 'data': {'url': BASE + '/login?test_only=FAKE', 'qrcode_key': 'FAKE_KEY'}})
    qr = await p.start_qr()
    assert qr.polling_key == 'FAKE_KEY'
    assert qr.image_data_url.startswith('data:image/png;base64,')
    assert qr.display_for == 180
    assert list(tmp_path.iterdir()) == []
    await p.aclose()


@pytest.mark.parametrize('code,state', [(86101, 'waiting_scan'), (86090, 'waiting_confirm'), (86038, 'expired')])
@respx.mock
async def test_qr_waiting_states(code, state):
    p = provider()
    poll_result({'code': code})
    result = await p.poll_qr('FAKE_KEY')
    assert result.state == state and result.credentials is None
    await p.aclose()


@respx.mock
async def test_qr_old_response_decodes_once_and_captures_refresh():
    p = provider()
    poll_result({'code': 0, 'url': legacy_url({**VALUES, 'sessdata': 'FAKE%2CSESS'}), 'refresh_token': 'FAKE_REFRESH'})
    result = await p.poll_qr('FAKE_KEY')
    assert result.state == 'credential_ready'
    assert result.credentials == {**VALUES, 'sessdata': 'FAKE%2CSESS', 'ac_time_value': 'FAKE_REFRESH'}
    await p.aclose()


@respx.mock
async def test_qr_cross_domain_captures_cookies_in_same_response():
    p = provider()
    url = 'https://passport.biligame.com/x/passport-login/web/crossDomain?ticket=FAKE_TICKET'
    route = poll_result({'code': 0, 'url': url, 'refresh_token': 'FAKE_REFRESH'})
    respx.get(url).respond(302, headers=[('location', 'https://www.bilibili.com/'),
        ('set-cookie', 'SESSDATA=FAKE_SESS; Path=/'), ('set-cookie', 'bili_jct=FAKE_JCT; Path=/'),
        ('set-cookie', 'DedeUserID=10001; Path=/')])
    result = await p.poll_qr('FAKE_KEY')
    assert result.credentials == {**VALUES, 'ac_time_value': 'FAKE_REFRESH'}
    assert route.call_count == 1
    await p.aclose()


@pytest.mark.parametrize('second,valid', [('FAKE_SESS', True), ('OTHER_SESS', False)])
@respx.mock
async def test_qr_duplicate_cookie_values(second, valid):
    p = provider()
    url = BASE + '/x/passport-login/web/crossDomain?ticket=FAKE'
    poll_result({'code': 0, 'url': url})
    respx.get(url).respond(200, headers=[('set-cookie', 'SESSDATA=FAKE_SESS'),
        ('set-cookie', 'SESSDATA=' + second), ('set-cookie', 'bili_jct=FAKE_JCT'), ('set-cookie', 'DedeUserID=10001')])
    if valid:
        assert (await p.poll_qr('FAKE')).credentials == VALUES
    else:
        with pytest.raises(Exception) as caught: await p.poll_qr('FAKE')
        assert caught.value.error_code == 'UNSUPPORTED_RESPONSE'
    await p.aclose()


@pytest.mark.parametrize('url', ['http://passport.bilibili.com/x/passport-login/web/crossDomain',
    'https://127.0.0.1/x/passport-login/web/crossDomain', 'https://passport.bilibili.com.evil.example/login',
    'https://passport.bilibili.com:8443/x/passport-login/web/crossDomain',
    'https://user:pass@passport.bilibili.com/x/passport-login/web/crossDomain',
    BASE + '/unknown?ticket=FAKE'])
@respx.mock
async def test_qr_rejects_untrusted_exchange_without_request(url):
    p = provider()
    poll_result({'code': 0, 'url': url})
    with pytest.raises(Exception) as caught: await p.poll_qr('FAKE')
    assert caught.value.error_code == 'UNSUPPORTED_RESPONSE'
    assert len(respx.calls) == 1
    await p.aclose()


@respx.mock
async def test_qr_redirect_bound():
    p = provider()
    url = BASE + '/x/passport-login/web/crossDomain?ticket=FAKE'
    poll_result({'code': 0, 'url': url})
    exchange = respx.get(url).respond(302, headers={'location': url})
    with pytest.raises(Exception): await p.poll_qr('FAKE')
    assert exchange.call_count <= 4
    await p.aclose()


@pytest.mark.parametrize('data', [{'code': 999}, {'code': 0, 'url': legacy_url({'sessdata': 'FAKE'})}, {'code': 0}, []])
@respx.mock
async def test_unknown_or_incomplete_qr_is_not_success(data):
    p = provider()
    poll_result(data)
    with pytest.raises(Exception) as caught: await p.poll_qr('FAKE')
    assert caught.value.error_code == 'UNSUPPORTED_RESPONSE'
    await p.aclose()


@respx.mock
async def test_verified_account_and_legacy_sessdata_import():
    p = provider()
    nav = respx.get(NAV).respond(200, json={'code': 0, 'data': {'isLogin': True, 'mid': 10001, 'uname': 'Test'}})
    account = await p.validate_credentials({'sessdata': 'FAKE_SESS'})
    assert account.uid == '10001' and account.credentials == {'sessdata': 'FAKE_SESS', 'dedeuserid': '10001'}
    assert 'FAKE_SESS' in nav.calls.last.request.headers['cookie']
    assert account.nickname == 'Test'
    await p.aclose()


@pytest.mark.parametrize('data', [{'isLogin': False, 'mid': 10001}, {'isLogin': True, 'mid': 0},
    {'isLogin': True, 'mid': True}, {'isLogin': True, 'mid': 999}, {'isLogin': True, 'mid': 'bad'}, []])
@respx.mock
async def test_nav_rejects_anonymous_malformed_or_wrong_identity(data):
    p = provider()
    respx.get(NAV).respond(200, json={'code': 0, 'data': data})
    with pytest.raises(Exception) as caught: await p.validate_credentials(VALUES)
    assert caught.value.error_code == 'INVALID_CREDENTIALS'
    await p.aclose()


@pytest.mark.parametrize('status,code', [(412, 'UPSTREAM_RESTRICTED'), (429, 'RATE_LIMITED')])
@respx.mock
async def test_http_errors_are_sanitized(status, code, caplog):
    p = provider()
    respx.get(NAV).respond(status, text='FAKE_SESS FAKE_TICKET', headers={'Retry-After': '37'})
    with pytest.raises(Exception) as caught: await p.validate_credentials(VALUES)
    assert caught.value.error_code == code
    assert 'FAKE_' not in str(caught.value) + caplog.text
    await p.aclose()


PROOF = {'token': 'FAKE_TOKEN', 'challenge': 'FAKE_CHALLENGE', 'validate': 'FAKE_VALIDATE', 'seccode': 'FAKE_SECCODE'}


@respx.mock
async def test_password_exact_bytes_and_rsa_limit():
    p = provider()
    key = RSA.generate(1024)
    respx.get(BASE + '/x/passport-login/web/key').respond(200, json={'code': 0, 'data': {'hash': 'fake-salt-', 'key': key.public_key().export_key().decode()}})
    login = respx.post(BASE + '/x/passport-login/web/login').respond(200, json={'code': 0, 'data': {'status': 0, 'url': legacy_url()}})
    assert await p.login_password('fake@example.test', ' 密码123 ', PROOF) == VALUES
    fields = parse_qs(login.calls.last.request.content.decode())
    raw = PKCS1_v1_5.new(key).decrypt(base64.b64decode(fields['password'][0]), None)
    assert raw == ('fake-salt-' + ' 密码123 ').encode()
    with pytest.raises(Exception) as caught: await p.login_password('fake@example.test', 'x' * 512, PROOF)
    assert caught.value.error_code == 'INVALID_INPUT'
    assert login.call_count == 1
    await p.aclose()


@respx.mock
async def test_captcha_initialization_and_proof_required():
    p = provider()
    respx.get(BASE + '/x/passport-login/captcha').respond(200, json={'code': 0, 'data': {
        'token': 'FAKE_TOKEN', 'geetest': {'gt': 'FAKE_GT', 'challenge': 'FAKE_CHALLENGE'}}})
    assert await p.get_captcha() == {'gt': 'FAKE_GT', 'challenge': 'FAKE_CHALLENGE', 'token': 'FAKE_TOKEN'}
    with pytest.raises(Exception) as caught: await p.send_sms('13800000000', {})
    assert caught.value.error_code == 'CAPTCHA_REQUIRED'
    assert len(respx.calls) == 1
    await p.aclose()


@respx.mock
async def test_password_success_uses_response_cookie_headers():
    p = provider()
    key = RSA.generate(1024)
    respx.get(BASE + '/x/passport-login/web/key').respond(200, json={'code': 0, 'data': {'hash': 'salt', 'key': key.public_key().export_key().decode()}})
    respx.post(BASE + '/x/passport-login/web/login').respond(200, json={'code': 0, 'data': {'status': 0}},
        headers=[('set-cookie', 'SESSDATA=FAKE_SESS'), ('set-cookie', 'bili_jct=FAKE_JCT'), ('set-cookie', 'DedeUserID=10001')])
    assert await p.login_password('fake@example.test', 'fake', PROOF) == VALUES
    await p.aclose()


@respx.mock
async def test_sms_ticket_and_country_binding():
    p = provider()
    send = respx.post(BASE + '/x/passport-login/web/sms/send').respond(200, json={'code': 0, 'data': {'captcha_key': 'FAKE_SMS_KEY'}})
    assert await p.send_sms('13800000000', PROOF) == 'FAKE_SMS_KEY'
    fields = parse_qs(send.calls.last.request.content.decode())
    assert fields['cid'] == ['86'] and fields['tel'] == ['13800000000']
    login = respx.post(BASE + '/x/passport-login/web/login/sms').respond(200, json={'code': 0, 'data': {'status': 0, 'url': legacy_url()}})
    assert await p.login_sms('13800000000', '012345', 'FAKE_SMS_KEY') == VALUES
    fields = parse_qs(login.calls.last.request.content.decode())
    assert fields['captcha_key'] == ['FAKE_SMS_KEY'] and fields['code'] == ['012345']
    await p.aclose()


@pytest.mark.parametrize('status', [1, 2, 5, 999, None])
@respx.mock
async def test_extra_verification_is_not_success(status):
    p = provider()
    respx.post(BASE + '/x/passport-login/web/login/sms').respond(200, json={'code': 0, 'data': {
        'status': status, 'url': BASE + '/safecenter?tmp_token=FAKE_SECRET'}})
    with pytest.raises(Exception) as caught: await p.login_sms('13800000000', '123456', 'FAKE_KEY')
    assert caught.value.error_code == ('SECURITY_VERIFICATION_REQUIRED' if status in (1, 2, 5) else 'UNSUPPORTED_RESPONSE')
    assert 'FAKE_SECRET' not in str(caught.value)
    await p.aclose()


@respx.mock
async def test_network_debug_logs_never_include_login_tickets(caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    p = provider(); url = BASE+'/x/passport-login/web/crossDomain?ticket=FAKE_SECRET_TICKET'
    poll_result({'code':0,'url':url})
    respx.get(url).respond(200, headers=[('set-cookie','SESSDATA=FAKE_SESS'), ('set-cookie','bili_jct=FAKE_JCT'), ('set-cookie','DedeUserID=10001')])
    assert (await p.poll_qr('FAKE_SECRET_KEY')).credentials == VALUES
    assert 'FAKE_SECRET' not in caplog.text and 'FAKE_SESS' not in caplog.text
    await p.aclose()


@pytest.mark.parametrize('query_sess,valid', [('HEADER_FAKE',True), ('CONFLICT_FAKE',False)])
@respx.mock
async def test_complete_header_and_legacy_query_must_agree(query_sess, valid):
    p = provider()
    respx.get(POLL).respond(200,json={'code':0,'data':{'code':0,'url':legacy_url({**VALUES,'sessdata':query_sess})}},
        headers=[('set-cookie','SESSDATA=HEADER_FAKE'),('set-cookie','bili_jct=FAKE_JCT'),('set-cookie','DedeUserID=10001')])
    if valid: assert (await p.poll_qr('FAKE')).credentials['sessdata'] == 'HEADER_FAKE'
    else:
        with pytest.raises(Exception) as caught: await p.poll_qr('FAKE')
        assert caught.value.error_code == 'UNSUPPORTED_RESPONSE'
    await p.aclose()


@respx.mock
async def test_empty_userinfo_is_rejected_without_exchange_request():
    p = provider()
    poll_result({'code':0,'url':'https://@passport.bilibili.com/x/passport-login/web/crossDomain?ticket=FAKE'})
    respx.get(BASE+'/x/passport-login/web/crossDomain?ticket=FAKE').respond(200,
        headers=[('set-cookie','SESSDATA=FAKE_SESS'),('set-cookie','bili_jct=FAKE_JCT'),('set-cookie','DedeUserID=10001')])
    with pytest.raises(Exception) as caught: await p.poll_qr('FAKE')
    assert caught.value.error_code == 'UNSUPPORTED_RESPONSE' and len(respx.calls) == 1
    await p.aclose()
