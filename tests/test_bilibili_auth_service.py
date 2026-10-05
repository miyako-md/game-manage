import asyncio
import copy
import importlib
import importlib.util
from types import SimpleNamespace

import pytest

from game_assistant.auth.bilibili_provider import QrChallenge, QrResult, VerifiedBilibiliAccount, BilibiliProtocolError

VALUES = {'sessdata': 'FAKE_SESS', 'bili_jct': 'FAKE_JCT', 'dedeuserid': '10001'}
PROOF = {'validate': 'FAKE_VALIDATE', 'seccode': 'FAKE_SECCODE'}


class Clock:
    def __init__(self): self.value = 1000.0
    def __call__(self): return self.value
    def advance(self, seconds): self.value += seconds


class Store:
    def __init__(self): self.values = {'bilibili': {'sessdata': 'OLD_FAKE'}}
    def load(self): return copy.deepcopy(self.values)


class Source:
    def __init__(self): self.credentials = Store(); self.busy = False; self.saved = []
    def commit_verified_account(self, account):
        from game_assistant.sources.bilibili_service import BilibiliSaveBusy
        if self.busy: raise BilibiliSaveBusy()
        self.saved.append(account)
        self.credentials.values = {'bilibili': account.credentials, 'bilibili_meta': {'uid': account.uid, 'nickname': account.nickname, 'validated_at': account.validated_at}}
        return {}


class Provider:
    def __init__(self, case): self.case = case
    async def start_qr(self): return QrChallenge('FAKE_KEY', 'data:image/png;base64,FAKE')
    async def poll_qr(self, key):
        self.case.calls['qr'] += 1
        if self.case.gate: await self.case.gate.wait()
        return QrResult(self.case.qr_state, VALUES if self.case.qr_state == 'credential_ready' else None)
    async def get_captcha(self): return {'gt': 'FAKE_GT', 'token': 'FAKE_TOKEN', 'challenge': 'FAKE_CHALLENGE'}
    async def send_sms(self, mobile, proof):
        self.case.calls['sms'] += 1
        if self.case.sms_error: raise BilibiliProtocolError('UPSTREAM_UNAVAILABLE')
        return 'FAKE_SMS_KEY'
    async def login_sms(self, mobile, code, key):
        self.case.last_sms = (mobile, code, key)
        if self.case.login_error: raise BilibiliProtocolError('UPSTREAM_REJECTED', 400)
        return VALUES
    async def login_password(self, username, password, proof):
        self.case.calls['password'] += 1
        if self.case.login_error: raise BilibiliProtocolError('UPSTREAM_REJECTED', 400)
        return VALUES
    async def validate_credentials(self, values):
        self.case.calls['validate'] += 1
        return VerifiedBilibiliAccount(values, '10001', 'Test', self.case.clock())
    async def aclose(self): self.case.calls['closed'] += 1


def make_case():
    assert importlib.util.find_spec('game_assistant.auth.bilibili_service'), 'Bilibili session service missing'
    module = importlib.import_module('game_assistant.auth.bilibili_service')
    case = SimpleNamespace(clock=Clock(), source=Source(), calls=dict(qr=0, sms=0, password=0, validate=0, closed=0),
        gate=None, sms_error=False, login_error=False, qr_state='credential_ready')
    case.error = module.BilibiliLoginError
    case.service = module.BilibiliLoginService(case.source, provider_factory=lambda: Provider(case), clock=case.clock, wall_clock=case.clock)
    return case


async def sid(case, mode): return (await case.service.start(mode))['session_id']


async def send(case, session):
    await case.service.captcha(session)
    return await case.service.sms_send(session, '13800000000', PROOF)


async def test_pending_save_does_not_reconsume_qr():
    c = make_case(); c.source.busy = True
    s = await sid(c, 'qr')
    with pytest.raises(c.error) as caught: await c.service.qr_poll(s)
    assert (caught.value.status, caught.value.state) == (409, 'pending_save')
    assert c.source.saved == [] and c.source.credentials.load()['bilibili']['sessdata'] == 'OLD_FAKE'
    c.source.busy = False
    assert (await c.service.commit(s))['state'] == 'complete'
    assert c.calls['qr'] == 1 and c.calls['validate'] == 2
    assert c.service.status()['state'] == 'validated'
    assert 'FAKE_' not in str(c.service.session_status(s))
    await c.service.aclose()


async def test_sms_timeout_cooldown_survives_new_session():
    c = make_case(); c.sms_error = True
    s = await sid(c, 'sms')
    with pytest.raises(c.error): await send(c, s)
    s = await sid(c, 'sms'); c.sms_error = False; c.clock.advance(59)
    with pytest.raises(c.error) as caught: await send(c, s)
    assert caught.value.status == 429 and c.calls['sms'] == 1
    c.clock.advance(1)
    assert (await send(c, s))['retry_after'] == 60
    assert c.calls['sms'] == 2
    await c.service.aclose()


async def test_stale_panel_cancel_and_result():
    c = make_case(); c.gate = asyncio.Event()
    old = await sid(c, 'qr'); pending = asyncio.create_task(c.service.qr_poll(old)); await asyncio.sleep(0)
    new = await sid(c, 'cookie'); await c.service.cancel(old); c.gate.set()
    with pytest.raises(c.error) as caught: await pending
    assert caught.value.status == 410 and not c.source.saved
    assert c.service.session_status(new)['mode'] == 'cookie'
    await c.service.aclose()


@pytest.mark.parametrize('mode,seconds', [('cookie', 600), ('qr', 180)])
async def test_session_and_qr_expire_at_boundary(mode, seconds):
    c = make_case(); s = await sid(c, mode); c.clock.advance(seconds)
    with pytest.raises(c.error) as caught: await c.service.cookie(s, VALUES) if mode == 'cookie' else await c.service.qr_poll(s)
    assert caught.value.status == 410 and not c.source.saved
    await c.service.aclose()


async def test_challenge_consumed_expired_and_phone_bound():
    c = make_case(); s = await sid(c, 'sms')
    await c.service.captcha(s); c.clock.advance(120)
    with pytest.raises(c.error): await c.service.sms_send(s, '13800000000', PROOF)
    await send(c, s)
    c.clock.advance(60); await c.service.captcha(s)
    with pytest.raises(c.error): await c.service.sms_send(s, '13900000000', PROOF)
    assert c.calls['sms'] == 1
    assert (await c.service.sms_submit(s, '012345'))['state'] == 'complete'
    assert c.last_sms == ('13800000000', '012345', 'FAKE_SMS_KEY')
    await c.service.aclose()


async def test_submission_start_and_sms_limits():
    c = make_case(); c.login_error = True; s = await sid(c, 'password')
    for _ in range(5):
        await c.service.captcha(s)
        with pytest.raises(c.error): await c.service.password(s, 'fake@example.test', 'FAKE_PASSWORD', PROOF)
    await c.service.captcha(s)
    with pytest.raises(c.error) as caught: await c.service.password(s, 'fake@example.test', 'FAKE_PASSWORD', PROOF)
    assert caught.value.status == 410 and c.calls['password'] == 5
    for _ in range(9): await sid(c, 'cookie')
    with pytest.raises(c.error) as caught: await sid(c, 'cookie')
    assert caught.value.status == 429
    await c.service.aclose()


async def test_global_sms_window_is_not_reset_by_new_sids():
    c = make_case()
    for index in range(5):
        s = await sid(c, 'sms'); await send(c, s); c.clock.advance(60)
    s = await sid(c, 'sms')
    with pytest.raises(c.error) as caught: await send(c, s)
    assert caught.value.status == 429 and c.calls['sms'] == 5
    c.clock.advance(300)
    s = await sid(c, 'sms'); await send(c, s)
    assert c.calls['sms'] == 6
    await c.service.aclose()


async def test_wrong_sms_code_can_be_corrected_without_resend():
    c = make_case(); s = await sid(c, 'sms'); await send(c, s); c.login_error = True
    with pytest.raises(c.error): await c.service.sms_submit(s, '000000')
    assert c.service.session_status(s)['state'] == 'sms_sent'
    c.login_error = False
    assert (await c.service.sms_submit(s, '012345'))['state'] == 'complete'
    assert c.calls['sms'] == 1
    await c.service.aclose()


async def test_idle_candidate_is_removed_and_provider_closed(monkeypatch):
    import time
    import game_assistant.auth.bilibili_service as module
    monkeypatch.setattr(module, 'CANDIDATE_TTL', .02)
    c = make_case(); c.service.clock = time.monotonic; c.source.busy = True
    s = await sid(c, 'qr')
    with pytest.raises(c.error): await c.service.qr_poll(s)
    await asyncio.sleep(.06)
    assert not c.service._sessions and c.calls['closed'] == 1
    await c.service.aclose()


async def test_idle_captcha_secrets_expire_without_next_request(monkeypatch):
    import time
    import game_assistant.auth.bilibili_service as module
    monkeypatch.setattr(module, 'CAPTCHA_TTL', .02)
    c = make_case(); c.service.clock = time.monotonic; s = await sid(c, 'password')
    await c.service.captcha(s); await asyncio.sleep(.06)
    assert c.service._sessions[s].captcha is None
    await c.service.aclose()


async def test_qr_poll_rate_and_single_inflight():
    c = make_case(); c.qr_state = 'waiting_scan'; s = await sid(c, 'qr')
    await c.service.qr_poll(s); c.clock.advance(2.999); await c.service.qr_poll(s)
    assert c.calls['qr'] == 1
    c.clock.advance(.001); c.gate = asyncio.Event()
    pending = asyncio.create_task(c.service.qr_poll(s)); await asyncio.sleep(0)
    with pytest.raises(c.error) as caught: await c.service.qr_poll(s)
    assert caught.value.status == 409
    c.gate.set(); await pending
    await c.service.aclose()


async def test_candidate_expiry_and_disconnect_preserve_account():
    c = make_case(); c.source.busy = True; s = await sid(c, 'qr')
    with pytest.raises(c.error): await c.service.qr_poll(s)
    c.clock.advance(120)
    with pytest.raises(c.error): await c.service.commit(s)
    c.source.busy = False; s = await sid(c, 'cookie')
    async def disconnected(): return True
    with pytest.raises(c.error): await c.service.cookie(s, VALUES, is_disconnected=disconnected)
    assert not c.source.saved
    await c.service.aclose()


async def test_terminal_records_bounded_and_shutdown_clears():
    c = make_case()
    for _ in range(25):
        c.clock.advance(7); await c.service.cancel(await sid(c, 'cookie'))
    assert len(c.service._terminal) <= 16
    await c.service.aclose()
    assert not c.service._sessions and not c.service._terminal


async def test_consumed_qr_candidate_outlives_display_expiry():
    c = make_case(); c.source.busy = True; s = await sid(c, 'qr')
    c.clock.advance(179)
    with pytest.raises(c.error): await c.service.qr_poll(s)
    c.clock.advance(2); c.source.busy = False
    assert (await c.service.commit(s))['state'] == 'complete'
    await c.service.aclose()


async def test_successful_qr_not_repolled_after_nav_network_failure():
    c = make_case(); s = await sid(c, 'qr')
    original = c.service._sessions[s].provider.validate_credentials
    async def unavailable(values): raise BilibiliProtocolError('UPSTREAM_UNAVAILABLE')
    c.service._sessions[s].provider.validate_credentials = unavailable
    with pytest.raises(c.error): await c.service.qr_poll(s)
    c.clock.advance(3)
    c.service._sessions[s].provider.validate_credentials = original
    with pytest.raises(c.error): await c.service.qr_poll(s)
    assert c.calls['qr'] == 1 and not c.source.saved
    await c.service.aclose()


async def test_shutdown_cancels_and_closes_inflight_request():
    c = make_case(); c.gate = asyncio.Event(); s = await sid(c, 'qr')
    pending = asyncio.create_task(c.service.qr_poll(s)); await asyncio.sleep(0)
    await c.service.aclose()
    assert pending.done() and pending.cancelled()
    assert c.calls['closed'] == 1 and not c.source.saved


def test_retry_reset_failure_after_saved_account(tmp_path, monkeypatch):
    from game_assistant.config import Settings
    from game_assistant.sources.bilibili_service import BilibiliService
    source = BilibiliService(Settings(db_path=str(tmp_path/'test.db')), {'nte': '123'})
    assert hasattr(source, 'commit_verified_account'), 'verified commit missing'
    def fail(*args, **kwargs): raise RuntimeError('FAKE_SECRET')
    monkeypatch.setattr(source.store, 'set_state', fail)
    result = source.commit_verified_account(VerifiedBilibiliAccount(VALUES, '10001', 'Test', 1000))
    assert result.get('warning') and 'FAKE_SECRET' not in str(result)
    assert source.credentials.load()['bilibili'] == VALUES
    assert b'FAKE_SESS' not in source.credentials.path.read_bytes()
    source.store.close()


async def test_dpapi_legacy_restart_metadata_isolated_and_history_preserved(tmp_path):
    from game_assistant.config import Settings
    from game_assistant.sources.bilibili_service import BilibiliService
    from game_assistant.auth.bilibili_service import BilibiliLoginService
    seen = []
    class Client:
        def __init__(self, uid, values): seen.append(values)
        async def page(self, offset): return {'items':[], 'has_more':False}
    source = BilibiliService(Settings(db_path=str(tmp_path/'test.db')), {'nte':'123'}, client_factory=Client)
    source.credentials.save({'bilibili':{'sessdata':'OLD_FAKE'}, 'other':{'token':'OTHER_FAKE'}})
    source.commit_verified_account(VerifiedBilibiliAccount(VALUES, '10001', 'Test', 1000))
    login = BilibiliLoginService(source)
    assert login.status()['state'] == 'configured' and login.status()['uid'] == '10001'
    assert not login._sessions
    await source.run('nte')
    assert seen == [VALUES]
    assert source.credentials.load()['other'] == {'token':'OTHER_FAKE'}
    await login.aclose(); await source.close()


async def test_failed_save_and_corrupt_store_preserve_original_file(tmp_path):
    from game_assistant.config import Settings
    from game_assistant.sources.bilibili_service import BilibiliService
    from game_assistant.auth.bilibili_service import BilibiliLoginService
    from game_assistant.auth.store import CredentialStoreError
    source = BilibiliService(Settings(db_path=str(tmp_path/'test.db')), {'nte':'123'})
    source.credentials.path.write_bytes(b'CORRUPT_FAKE')
    before = source.credentials.path.read_bytes()
    with pytest.raises(CredentialStoreError): source.commit_verified_account(VerifiedBilibiliAccount(VALUES, '10001', 'Test', 1000))
    assert source.credentials.path.read_bytes() == before
    login = BilibiliLoginService(source)
    assert login.status()['state'] == 'storage_error'
    await login.aclose(); await source.close()
