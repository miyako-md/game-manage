"""Sequential parser -> internal API -> renderer -> official media regression."""
import base64
import os
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest

from game_assistant.cloud_app import create_cloud_app
from game_assistant.config import Settings
from game_assistant.identity.models import Principal
from game_assistant.qq.client import InternalQqClient, OfficialQqClient, QqReply
from game_assistant.qq.models import InboundMessage, QqIdentity
from game_assistant.qq.transport import BotDispatcher, BotState
from tests.test_qq_unified_queries import CachedQuery, no_external_network


async def test_help_then_own_overview_in_new_group_distinguishes_binding_from_help_cache(tmp_path,monkeypatch):
    executable=os.environ.get('QQ_RENDER_TEST_EXECUTABLE')
    font=os.environ.get('QQ_RENDER_TEST_FONT')
    if not executable or not font:pytest.skip('Sequential media regression requires explicit QQ_RENDER_TEST_EXECUTABLE and QQ_RENDER_TEST_FONT')
    app=create_cloud_app(Settings(cloud_db_path=str(tmp_path/'cloud.db'),cloud_allowed_origins=['https://cloud.example'],
        qq_app_id='app',qq_service_token='fixture-service',qq_images_enabled=True,qq_image_font_path=font,qq_browser_render_executable_path=executable,
        qq_image_max_bytes=1048576),start_scheduler=False)
    service=app.state.qq_query
    service.clock=lambda:datetime(2026,10,15,12,tzinfo=timezone.utc)
    # Successful shared images use a short caption. Assert the business/binding
    # instructions on their actual rendered DOM, including cached image reuse.
    from playwright.async_api import Page
    original_evaluate=Page.evaluate
    rendered_text=[];image_text={}
    async def evaluate(page,expression,*args,**kwargs):
        value=await original_evaluate(page,expression,*args,**kwargs)
        if expression=='window.__LONG_RENDER_STATE__':
            assert 0<value['width']<=1080 and 0<value['height']<=16000
            assert value['layout_issues']==0 and not value['overflow']
            rendered_text.append('\n'.join(await page.locator('.lab-sheet').all_inner_texts()))
        return value
    monkeypatch.setattr(Page,'evaluate',evaluate)
    original_render=service.render_queue.renderer.render_summary_async
    async def render(*args,**kwargs):
        image=await original_render(*args,**kwargs)
        image_text.setdefault(sha256(image).hexdigest(),rendered_text[-1])
        return image
    monkeypatch.setattr(service.render_queue.renderer,'render_summary_async',render)
    def displayed(reply):return image_text[sha256(reply.image).hexdigest()]
    bindings=service.bindings
    with bindings.store.connect(write=True) as db:
        db.execute("INSERT INTO users(user_id,username,password_hash) VALUES('u','fixture','fixture')")
    old=QqIdentity('app','group','old-group','sender')
    friend=QqIdentity('app','group','friends-group','sender')
    owner=Principal('u',False)
    bindings.redeem_link_code(old,bindings.create_link_code(owner)['code'],'old-binding')
    query=CachedQuery()
    query.add('nte','tajiduo','n',{'account':{'schema_version':1,'nickname':'Fixture account','level':17},'stamina':{'schema_version':1,'current':0,'maximum':100}})
    service.query_service=query
    query.accounts._listeners.append(service.invalidate)
    http=httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1234)))
    commands=[];replies=[];uploads=[];sends=[]
    class Client(InternalQqClient):
        async def post(self,path,body):
            commands.append(body['command'])
            return await super().post(path,body)
    internal=Client('http://127.0.0.1:8020','fixture-service',internal_host='cloud.example',http=http,
                    images_enabled=True,max_image_bytes=1048576)
    class Business:
        async def execute(self,message):
            reply=await internal.execute(message);replies.append(reply);return reply
    class API:
        def __init__(self,*args,**kwargs):pass
        def setup(self,http):pass
        async def request(self,method,path,body,**kwargs):
            if path.endswith('/files'):
                image=base64.b64decode(body['file_data'],validate=True)
                file_info='fixture-media-'+str(len(uploads))
                uploads.append((path,sha256(image).hexdigest(),file_info))
                assert body['srv_send_msg'] is False
                return {'file_info':file_info}
            sends.append((path,body))
            return {'id':'fixture-message-'+str(len(sends))}
    sender=OfficialQqClient('app','fixture',None,None,sdk=SimpleNamespace(QQApiClient=API))
    sender.max_image_bytes=1048576
    state=BotState(tmp_path/'bot.db')
    dispatcher=BotDispatcher(Business(),sender,state)
    now=datetime.now(timezone.utc)
    def message(identity,msg_id,content):
        return InboundMessage(identity,msg_id,content,now.isoformat(),(now+timedelta(minutes=5)).isoformat())
    try:
        # Warm both help and the old group's own-account PNG caches, then run the
        # real reported sequence for the same sender in the newly allowed group.
        await dispatcher.handle_message(message(old,'old-help','帮助'))
        await dispatcher.handle_message(message(old,'old-overview','我的总览'))
        await dispatcher.handle_message(message(friend,'friends-help','帮助'))
        await dispatcher.handle_message(message(friend,'friends-overview','我的总览'))
        assert commands==['help','overview','help','overview']
        assert all(isinstance(reply,QqReply) for reply in replies)
        assert 'Fixture account' in displayed(replies[1]) and 'Fixture account' not in displayed(replies[3])
        assert replies[0].text==replies[2].text and uploads[0][1]==uploads[2][1]
        assert uploads[0][1]!=uploads[1][1]  # bound overview is not the cached help PNG
        assert len({item[2] for item in uploads})==4  # media uploaded independently
        assert [body['media']['file_info'] for path,body in sends]==[item[2] for item in uploads]
        assert all(body['msg_seq']==1 for path,body in sends)
        # This is the user-visible defect: the parser accepted overview, but the
        # binding branch returned a help card whose small notice hid the cause.
        assert replies[3].text.startswith('当前群尚未绑定')
        assert '网站' in displayed(replies[3]) and '绑定码' in displayed(replies[3]) and '填回' not in displayed(replies[3])
        assert uploads[2][1]!=uploads[3][1]
        assert '帮助 · 游戏管家' not in replies[3].text
        # Site confirmation grants only this extra identity; the original group
        # remains bound and both scopes still resolve to the same owner.
        bindings.redeem_link_code(friend,bindings.create_link_code(owner)['code'],'friend-binding')
        await dispatcher.handle_message(message(friend,'friends-bound-overview','我的总览'))
        await dispatcher.handle_message(message(old,'old-still-bound-overview','我的总览'))
        assert commands[-2:]==['overview','overview']
        assert 'Fixture account' in displayed(replies[4]) and 'Fixture account' in displayed(replies[5])
        assert uploads[4][1]==uploads[1][1]==uploads[5][1]
        assert len({item[2] for item in uploads})==6
        assert bindings.resolve_qq_identity(old)==owner==bindings.resolve_qq_identity(friend)
    finally:
        state.close();await http.aclose();await sender.aclose();await service.aclose()
