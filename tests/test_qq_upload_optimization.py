"""Transfer optimization must preserve image pixels and SDK deadline boundaries."""
from datetime import datetime,timedelta,timezone
from io import BytesIO
import logging

import httpx
from PIL import Image,ImageDraw

from game_assistant.qq.client import OfficialQqClient,load_sdk
from game_assistant.qq.long_image_encoding import encode
from game_assistant.qq.models import InboundMessage,QqIdentity


def sample(mode='RGB'):
    image=Image.new(mode,(180,1000),(255,255,255,0) if mode=='RGBA' else 'white')
    draw=ImageDraw.Draw(image)
    for y in range(20,980,28):draw.text((12,y),'Calendar 14 days / 153 medals',fill='black')
    stream=BytesIO();image.save(stream,'PNG',compress_level=0);return stream.getvalue()


def test_transfer_png_preserves_full_size_and_every_pixel():
    for mode in ['RGB','RGBA']:
        raw=sample(mode);baseline,old=encode(raw,True)
        optimized,metadata=encode(raw,True,optimize_transfer=True)
        with Image.open(BytesIO(baseline)) as before,Image.open(BytesIO(optimized)) as after:
            assert before.size==after.size==(180,1000)
            assert before.convert('RGBA').tobytes()==after.convert('RGBA').tobytes()
        assert len(optimized)<len(baseline)*.9
        assert metadata['format']=='png' and metadata['lossless_repacked'] is True
        assert metadata['saved_bytes']==len(baseline)-len(optimized)
        assert encode(raw,True)==(baseline,old)


def test_transfer_png_preserves_selected_palette_pixels():
    image=Image.new('RGB',(300,1200),'white')
    draw=ImageDraw.Draw(image)
    for y in range(10,1180,23):draw.text((12,y),'Full medal collection / unchanged text',fill='black')
    stream=BytesIO();image.save(stream,'PNG',compress_level=0);raw=stream.getvalue()
    assert len(raw)>850*1024
    baseline,old=encode(raw,True)
    optimized,metadata=encode(raw,True,optimize_transfer=True)
    with Image.open(BytesIO(baseline)) as before,Image.open(BytesIO(optimized)) as after:
        assert before.mode==after.mode=='P'
        assert before.size==after.size==(300,1200)
        assert before.convert('RGBA').tobytes()==after.convert('RGBA').tobytes()
    assert len(optimized)<=len(baseline)
    assert metadata['palette']==old['palette']


async def test_real_sdk_respects_upload_timeout_and_logs_only_safe_timings(caplog):
    now=datetime.now(timezone.utc);deadlines=[]
    async def handler(request):
        if request.url.path.endswith('/files'):
            deadlines.append(request.extensions['timeout'])
            trace=request.extensions.get('trace')
            if trace:
                for event in ['http11.send_request_body.started','http11.send_request_body.complete','http11.receive_response_headers.started','http11.receive_response_headers.complete']:
                    await trace(event,{'headers':{'Authorization':'private-token-never-log'}})
            return httpx.Response(200,json={'file_info':'private-media-never-log'})
        return httpx.Response(200,json={'id':'fixture-message'})
    client=OfficialQqClient('fixture-app','fixture-secret',None,None,sdk=load_sdk())
    client.max_image_bytes=1048576
    await client.http.aclose()
    from game_assistant.qq import client as module
    hooks={'response':[module._log_upload_response]}
    if hasattr(module,'_trace_upload_request'):hooks['request']=[module._trace_upload_request]
    client.http=httpx.AsyncClient(transport=httpx.MockTransport(handler),event_hooks=hooks)
    client.api.setup(client.http);client.api._access_token='private-token-never-log';client.api._token_expires_at=now.timestamp()+3600
    client.now=lambda:now;identity=QqIdentity('fixture-app','group','private-group-never-log','private-sender-never-log')
    caplog.set_level(logging.INFO,logger='game_assistant.qq.client')
    try:
        for seconds in [300,12,6]:
            message=InboundMessage(identity,'fixture-id','日历',now.isoformat(),(now+timedelta(seconds=seconds)).isoformat())
            await client.send_image(message,sample(),1)
        assert deadlines==[{'connect':5,'read':75,'write':75,'pool':5},{'connect':5,'read':7,'write':7,'pool':5},{'connect':1,'read':1,'write':1,'pool':1}]
        text=' '.join(record.getMessage() for record in caplog.records)
        assert 'send_body_ms=' in text and 'wait_headers_ms=' in text and 'wire_bytes=' in text
        assert 'private-' not in text
    finally:await client.aclose()


def test_renders_over_the_lossless_limit_take_a_palette_at_original_size():
    from random import Random
    from game_assistant.qq.long_image_encoding import LOSSLESS_BYTES
    rng=Random(7);image=Image.new('RGB',(1080,250))
    image.putdata([(rng.randrange(0,40),rng.randrange(0,40),rng.randrange(60,90)) for _ in range(1080*250)])
    stream=BytesIO();image.save(stream,'PNG');raw=stream.getvalue()
    assert LOSSLESS_BYTES<len(raw)<=850*1024
    data,metadata=encode(raw,True)
    assert metadata['palette']==256 and metadata['format']=='png'
    with Image.open(BytesIO(data)) as out:assert out.size==(1080,250)
    stream=BytesIO();Image.open(BytesIO(sample())).save(stream,'PNG');small=stream.getvalue()
    assert len(small)<=LOSSLESS_BYTES and encode(small,True)[0]==small
