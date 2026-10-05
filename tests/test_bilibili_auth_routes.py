import importlib
import importlib.util
import pytest
from fastapi.testclient import TestClient
from game_assistant.api import create_app
from game_assistant.config import Settings
from game_assistant.auth.bilibili_service import BilibiliLoginError
from tests.test_api import FakeRegistry
from tests.test_registry import DummyAdapter

ROOT = '/api/auth/bilibili-source/login'
HEADERS = {'X-Game-Assistant': '1'}
PROOF = {'validate': 'FAKE_VALIDATE', 'seccode': 'FAKE_SECCODE'}

class Fake:
    def __init__(self): self.calls = []; self.error = None; self.closed = False
    def status(self): return {'configured': False, 'state': 'unconfigured'}
    def session_status(self, sid): self.calls.append(('status', sid)); return {'state': 'ready'}
    async def aclose(self): self.closed = True
    def __getattr__(self, name):
        async def action(*args, **kwargs):
            self.calls.append((name, *args))
            if self.error: raise self.error
            if 'is_disconnected' in kwargs: assert not await kwargs['is_disconnected']()
            return {'state': 'ready'}
        return action

@pytest.fixture
def client(tmp_path):
    fake = Fake()
    settings = Settings(db_path=str(tmp_path/'test.db'))
    app = create_app(registry=FakeRegistry(DummyAdapter()), settings=settings, start_scheduler=False, bilibili_login_service=fake)
    with TestClient(app, base_url='http://127.0.0.1:8010') as c: yield c, fake
    assert fake.closed

@pytest.mark.parametrize('method,path,body,name', [
    ('GET', '/status', None, None), ('POST', '/sessions', {'mode':'qr'}, 'start'),
    ('GET', '/sessions/FAKE', None, 'status'), ('DELETE', '/sessions/FAKE', None, 'cancel'),
    ('POST', '/sessions/FAKE/captcha', None, 'captcha'),
    ('POST', '/sessions/FAKE/password', {'username':'fake','password':' FAKE_PASSWORD ','proof':PROOF}, 'password'),
    ('POST', '/sessions/FAKE/sms/send', {'mobile':'13800000000','proof':PROOF}, 'sms_send'),
    ('POST', '/sessions/FAKE/sms/submit', {'code':'012345'}, 'sms_submit'),
    ('POST', '/sessions/FAKE/qr/poll', None, 'qr_poll'),
    ('POST', '/sessions/FAKE/cookie', {'sessdata':'FAKE_SESS'}, 'cookie'),
    ('POST', '/sessions/FAKE/commit', None, 'commit'),
])
def test_route_dispatch(client, method, path, body, name):
    c, fake = client
    r = c.request(method, ROOT+path, json=body, headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.headers['cache-control'] == 'no-store'
    if name: assert fake.calls[-1][0] == name
    if name == 'password': assert fake.calls[-1][3] == ' FAKE_PASSWORD '
    if name == 'sms_submit': assert fake.calls[-1][2] == '012345'

def test_legacy_import_cannot_skip_validation(client):
    c, fake = client
    fake.error = BilibiliLoginError('登录未通过', 400, 'INVALID_CREDENTIALS')
    r = c.post('/api/auth/bilibili-source/credentials', json={'sessdata':'FAKE_SECRET'}, headers=HEADERS)
    assert r.status_code == 400 and fake.calls[-1][0] == 'import_legacy'
    assert 'FAKE_SECRET' not in r.text

@pytest.mark.parametrize('body', [{'username':'fake','password':'FAKE_SECRET','proof':PROOF,'extra':'FAKE_SECRET'},
    {'username':'fake','password':'FAKE_SECRET'}, {'username':'','password':'FAKE_SECRET','proof':PROOF}])
def test_validation_never_echoes_input(client, body):
    c, _ = client
    r = c.post(ROOT+'/sessions/FAKE/password', json=body, headers=HEADERS)
    assert r.status_code == 422 and 'FAKE_SECRET' not in r.text

def test_pending_save_and_security_boundary(client):
    c, fake = client
    assert c.post(ROOT+'/sessions', json={'mode':'sms'}).status_code == 403
    assert c.get(ROOT+'/status', headers={'Host':'attacker.example'}).status_code == 403
    assert c.post(ROOT+'/sessions', json={'mode':'sms'}, headers={**HEADERS,'Origin':'https://attacker.example'}).status_code == 403
    fake.error = BilibiliLoginError('稍后保存', 409, 'COLLECTION_BUSY', 'pending_save')
    r = c.post(ROOT+'/sessions/FAKE/commit', headers=HEADERS)
    assert r.status_code == 409 and r.json()['state'] == 'pending_save'
    fake.error = BilibiliLoginError('稍后再试', 429, 'RATE_LIMITED', retry_after=60)
    r = c.post(ROOT+'/sessions/FAKE/commit', headers=HEADERS)
    assert r.headers['retry-after'] == '60'


def test_malformed_json_unicode_code_and_oversized_body_are_safe(client):
    c, fake = client
    for path, body in [('/password', '{"password":"FAKE_SECRET",'), ('/sms/submit', '{"code":"１２３４５６"}')]:
        r = c.post(ROOT+'/sessions/FAKE'+path, content=body, headers={**HEADERS,'Content-Type':'application/json'})
        assert r.status_code == 422 and 'FAKE_SECRET' not in r.text
    r = c.post(ROOT+'/sessions/FAKE/cookie', content=b'x'*16385, headers=HEADERS)
    assert r.status_code == 413 and r.headers['referrer-policy'] == 'no-referrer'
    assert not fake.calls

async def test_stream_body_limit_without_content_length():
    assert importlib.util.find_spec('game_assistant.auth.bilibili_routes'), 'Bilibili router missing'
    middleware = importlib.import_module('game_assistant.auth.bilibili_routes').BilibiliBodyLimitMiddleware
    called = False; sent = []
    async def app(scope, receive, send):
        nonlocal called; called = True
    messages = iter([{'type':'http.request','body':b'x'*9000,'more_body':True}, {'type':'http.request','body':b'x'*9000,'more_body':False}])
    async def receive(): return next(messages)
    async def send(message): sent.append(message)
    await middleware(app)({'type':'http','path':ROOT+'/sessions','headers':[]}, receive, send)
    assert not called and sent[0]['status'] == 413
    assert (b'cache-control', b'no-store') in sent[0]['headers']
