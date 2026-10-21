from datetime import datetime, timedelta, timezone

import pytest

from game_assistant.qq.models import InboundMessage, QqIdentity
from game_assistant.qq.transport import BotDispatcher, BotState, EventGate

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


def message(content='/刷新 异环', deadline=None):
    return InboundMessage(QqIdentity('app', 'group', 'group', 'sender'), 'message', content,
                          NOW.isoformat(), (deadline or NOW + timedelta(minutes=5)).isoformat())


class Service:
    def __init__(self):
        self.calls = 0

    async def execute(self, message):
        self.calls += 1
        return '刷新已排队'


class Sender:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    async def send_text(self, message, text, sequence):
        self.calls.append((text, sequence))
        if self.fail:
            raise TimeoutError('sensitive remote response')
        return 'platform-id'


async def test_retry_does_not_repeat_refresh(tmp_path):
    service, sender = Service(), Sender()
    state = BotState(tmp_path / 'bot-state.db')
    dispatcher = BotDispatcher(service, sender, state, now=lambda: NOW)
    await dispatcher.handle_message(message())
    state.close()
    state = BotState(tmp_path / 'bot-state.db')
    await BotDispatcher(service, sender, state, now=lambda: NOW).handle_message(message())
    assert service.calls == 1
    assert sender.calls == [('刷新已排队', 1)]
    state.close()


async def test_uncertain_send_is_not_blindly_repeated(tmp_path, caplog):
    service, sender = Service(), Sender(fail=True)
    state = BotState(tmp_path / 'bot-state.db')
    dispatcher = BotDispatcher(service, sender, state, now=lambda: NOW)
    await dispatcher.handle_message(message())
    await dispatcher.handle_message(message())
    assert service.calls == 1 and sender.calls == [('刷新已排队', 1)]
    assert 'sensitive' not in caplog.text
    state.close()


async def test_reply_text_is_never_written_to_the_state_file(tmp_path):
    # The state file only needs the delivery outcome; a private reply must not reach disk,
    # not even while it is being sent (a crash then would leave it there).
    state = BotState(tmp_path / 'bot-state.db')
    seen = []
    class Watching(Sender):
        async def send_text(self, message, text, sequence):
            seen.extend(state.connection.execute('SELECT state, text FROM replies').fetchall())
            return await super().send_text(message, text, sequence)
    await BotDispatcher(Service(), Watching(), state, now=lambda: NOW).handle_message(message())
    assert seen == [('sending', None)]
    assert state.connection.execute('SELECT state, text FROM replies').fetchall() == [('sent', None)]
    state.close()


async def test_expired_reply_not_sent(tmp_path):
    service, sender = Service(), Sender()
    state = BotState(tmp_path / 'bot-state.db')
    await BotDispatcher(service, sender, state, now=lambda: NOW).handle_message(message(deadline=NOW-timedelta(seconds=1)))
    assert service.calls == 0 and sender.calls == []
    state.close()


async def test_query_finishes_after_deadline_not_sent(tmp_path):
    times = iter([NOW, NOW + timedelta(minutes=6)])
    service, sender = Service(), Sender()
    state = BotState(tmp_path / 'bot-state.db')
    await BotDispatcher(service, sender, state, now=lambda: next(times)).handle_message(message())
    assert service.calls == 1 and sender.calls == []
    state.close()


def event(group='group', sender='sender', content='/help'):
    return dict(id='msg', group_openid=group, content=content, timestamp=NOW.isoformat(),
                author={'member_openid': sender})


def test_only_allowed_app_group_at_events_preserve_identity():
    gate = EventGate('app', ['group'], now=lambda: NOW)
    msg = gate.parse('GROUP_AT_MESSAGE_CREATE', event())
    assert msg.identity == QqIdentity('app', 'group', 'group', 'sender')
    assert gate.parse('GROUP_AT_MESSAGE_CREATE', event(group='other')) is None
    assert gate.parse('GROUP_MESSAGE_CREATE', event()) is None
    assert gate.parse('C2C_MESSAGE_CREATE', event()) is None
    assert gate.parse('GROUP_AT_MESSAGE_CREATE', {**event(), 'author': {'bot': True, 'member_openid':'sender'}}) is None
    assert gate.parse('GROUP_AT_MESSAGE_CREATE', {**event(), 'timestamp': 'invalid'}) is None
    assert gate.parse('GROUP_AT_MESSAGE_CREATE', {**event(), 'timestamp':(NOW-timedelta(minutes=6)).isoformat()}) is None


def test_official_opaque_message_id_with_dots_is_preserved():
    gate = EventGate('app', ['group'], now=lambda: NOW)
    official_id = 'ROBOT1.0_00000000000000000000000000000000_000001'
    parsed = gate.parse('GROUP_AT_MESSAGE_CREATE', {**event(), 'id': official_id})
    assert parsed is not None and parsed.message_id == official_id
    for invalid_id in ('', 'x'*257, 'ROBOT1.0_\nforged', 'ROBOT1.0_\x00forged', 'ROBOT1.0_ forged'):
        assert gate.parse('GROUP_AT_MESSAGE_CREATE', {**event(), 'id': invalid_id}) is None
    assert gate.parse('GROUP_AT_MESSAGE_CREATE', event(sender='sender.with.dot')) is None


def test_same_message_id_in_different_identity_not_collision(tmp_path):
    state = BotState(tmp_path / 'bot-state.db')
    first = message()
    second = InboundMessage(QqIdentity('app', 'group', 'another', 'sender'), first.message_id,
                            first.content, first.received_at, first.reply_deadline)
    assert state.claim(first, NOW) and state.claim(second, NOW)
    assert not state.claim(first, NOW)
    state.close()


def test_state_cannot_use_existing_game_database(tmp_path):
    import sqlite3
    path=tmp_path/'game.db'
    db=sqlite3.connect(path)
    db.execute('CREATE TABLE accounts (user_id TEXT)')
    db.commit();db.close()
    with pytest.raises(ValueError,match='dedicated'):
        BotState(path)
    db=sqlite3.connect(path)
    assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()==[('accounts',)]
    db.close()


async def test_sdk_sender_uses_official_passive_message_sequence_and_sanitizes_error(caplog):
    from game_assistant.qq.client import OfficialQqClient,QqClientError
    requests=[]
    class API:
        def __init__(self,*a,**kw):pass
        def setup(self,http):pass
        async def request(self,method,path,body):
            requests.append((method,path,body))
            return {'id':'platform-message'}
    from types import SimpleNamespace
    client=OfficialQqClient('app','fake-secret',None,None,sdk=SimpleNamespace(QQApiClient=API))
    client.now=lambda:NOW
    assert await client.send_text(message(),'回复',1)=='platform-message'
    assert requests==[('POST','/v2/groups/group/messages',{'content':'回复','msg_type':0,'msg_id':'message','msg_seq':1})]
    async def fail(*args):raise RuntimeError('private-token')
    client.api.request=fail
    with pytest.raises(QqClientError) as error:await client.send_text(message(),'回复',1)
    assert 'private-token' not in str(error.value) and 'private-token' not in caplog.text
    await client.aclose()


def test_sdk_lock_and_current_endpoint_overrides_offline():
    from game_assistant.qq.client import load_sdk,API_BASE
    load_sdk()
    from qqbot_agent_sdk import api_client
    assert api_client.API_BASE==API_BASE=='https://api.bot.qq.com'
    assert api_client.TOKEN_URL=='https://api.bot.qq.com/app/getAppAccessToken'


async def test_real_sdk_identify_subscribes_only_group_and_c2c_events():
    from types import SimpleNamespace
    from game_assistant.qq.client import load_sdk
    sdk=load_sdk()
    socket=sdk.QQWebSocket(callbacks=SimpleNamespace(get_token=lambda:'fixture-token'))
    frames=[]
    async def capture(payload,label):
        frames.append(payload)
        return True
    socket._send_ws_json=capture
    await socket._send_identify()
    assert len(frames)==1 and frames[0]['op']==2
    assert frames[0]['d']['intents']==1 << 25
    assert frames[0]['d']['token']=='QQBot fixture-token'
    assert frames[0]['d']['shard']==[0,1]


async def test_uploads_and_text_share_one_paced_outbound_budget(monkeypatch):
    import asyncio
    from io import BytesIO
    from types import SimpleNamespace
    from PIL import Image
    import game_assistant.qq.client as qq_client
    from game_assistant.qq.client import OfficialQqClient,OUTBOUND_INTERVAL_SECONDS
    # The limiter's clock and sleep are simulated, so the check is exact: real
    # Windows timers may wake one ~16 ms clock tick early, which says nothing
    # about the limiter itself.
    clock,sleeps,real_sleep=[1000.0],[],asyncio.sleep
    async def sleep(delay,*args,**kwargs):
        # Let already-scheduled requests start at the current time first (3.11's
        # wait_for runs its coroutine as a separate task), then let the time pass.
        for _ in range(3):await real_sleep(0)
        sleeps.append(delay);clock[0]+=delay
    monkeypatch.setattr(qq_client,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    monkeypatch.setattr(qq_client.asyncio,'sleep',sleep)
    calls=[]
    class API:
        def __init__(self,*args,**kwargs):pass
        def setup(self,http):pass
        async def request(self,method,path,body,*,timeout=None):
            calls.append((clock[0],path))
            clock[0]+=0.001
            return {'file_info':'media'} if path.endswith('/files') else {'id':'message'}
    client=OfficialQqClient('app','fixture',None,None,sdk=SimpleNamespace(QQApiClient=API))
    client.now=lambda:NOW
    image=BytesIO()
    Image.new('RGB',(32,32)).save(image,'PNG')
    try:
        await asyncio.gather(client.send_image(message(),image.getvalue(),1),
                             client.send_text(message(),'文字',1),
                             client.send_image(message(),image.getvalue(),1))
        assert len(calls)==5
        assert sum(path.endswith('/files') for _,path in calls)==2
        # Actual outbound starts remain well below even the smaller 50/s upload limit.
        assert OUTBOUND_INTERVAL_SECONDS>=0.04 and len(sleeps)==4
        assert all(b[0]-a[0]>=OUTBOUND_INTERVAL_SECONDS-1e-9 for a,b in zip(calls,calls[1:]))
    finally:await client.aclose()


async def test_reply_expiring_during_rate_wait_is_not_sent():
    from types import SimpleNamespace
    from game_assistant.qq.client import OfficialQqClient,QqClientError
    calls=[]
    class API:
        def __init__(self,*args,**kwargs):pass
        def setup(self,http):pass
        async def request(self,method,path,body):
            calls.append(path)
            return {'id':'message'}
    client=OfficialQqClient('app','fixture',None,None,sdk=SimpleNamespace(QQApiClient=API))
    client.now=lambda:NOW
    try:
        await client.send_text(message(),'第一条',1)
        times=iter([NOW,NOW+timedelta(minutes=6)])
        client.now=lambda:next(times)
        with pytest.raises(QqClientError,match='qq_send_outcome_uncertain'):
            await client.send_text(message(),'已经过期',1)
        assert calls==['/v2/groups/group/messages']
    finally:await client.aclose()


async def test_image_upload_uses_forty_seconds_and_reserves_reply_time(monkeypatch):
    import asyncio
    from io import BytesIO
    from types import SimpleNamespace
    from PIL import Image
    from game_assistant.qq.client import OfficialQqClient
    calls=[];timeouts=[];wait=asyncio.wait_for
    class API:
        def __init__(self,*args,**kwargs):pass
        def setup(self,http):pass
        async def request(self,method,path,body,*,timeout=None):
            calls.append((path,body))
            return {'file_info':'fixture-media'} if path.endswith('/files') else {'id':'fixture-reply'}
    async def observed(awaitable,timeout):
        timeouts.append(timeout)
        return await wait(awaitable,timeout)
    monkeypatch.setattr(asyncio,'wait_for',observed)
    image=BytesIO();Image.new('RGB',(32,32)).save(image,'PNG')
    client=OfficialQqClient('fixture','fixture',None,None,sdk=SimpleNamespace(QQApiClient=API));client.now=lambda:NOW
    try:
        await client.send_image(message(),image.getvalue(),1)
        assert timeouts==[40,20]
        assert calls[0][1]['srv_send_msg'] is False
        calls.clear();timeouts.clear()
        await client.send_image(message(deadline=NOW+timedelta(seconds=12)),image.getvalue(),1)
        assert timeouts==[7,12]
        assert len(calls)==2 and calls[-1][1]['msg_seq']==1
    finally:await client.aclose()
